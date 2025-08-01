import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

# 🗂️ Google Sheets
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs",
        "52w High", "Direktavkastning (%)", "Riktkurs", "Uppside (%)",
        "Rekommendation", "Datakälla utdelning"
    ]
    for kol in kolumner:
        if kol not in df.columns:
            df[kol] = "" if kol in ["Ticker", "Bolagsnamn", "Valuta", "Rekommendation", "Datakälla utdelning"] else 0.0
    return df[kolumner]

def beräkna_rekommendationer(df, riktkurs_procent=5):
    df["Kurs"] = pd.to_numeric(df["Kurs"], errors="coerce").fillna(0)
    df["Utdelning"] = pd.to_numeric(df["Utdelning"], errors="coerce").fillna(0)
    df["52w High"] = pd.to_numeric(df["52w High"], errors="coerce").fillna(0)
    df["Direktavkastning (%)"] = round((df["Utdelning"] / df["Kurs"]) * 100, 2)
    df["Riktkurs"] = df["52w High"] * (1 - riktkurs_procent / 100)
    df["Uppside (%)"] = round((df["Riktkurs"] - df["Kurs"]) / df["Kurs"] * 100, 2)

    def ge_rek(row):
        if row["Kurs"] <= row["Riktkurs"] * 0.75:
            return "Köp kraftigt"
        elif row["Kurs"] <= row["Riktkurs"] * 0.90:
            return "Öka"
        elif row["Kurs"] <= row["Riktkurs"]:
            return "Behåll"
        elif row["Kurs"] <= row["Riktkurs"] * 1.1:
            return "Pausa"
        else:
            return "Sälj"

    df["Rekommendation"] = df.apply(ge_rek, axis=1)
    return df

def bläddra_förslag(df, filter_ägda=False):
    df = df.copy()
    df = df[df["Kurs"] > 0]
    if filter_ägda:
        df = df[df["Äger"].astype(str).str.lower().isin(["ja", "x", "1", "true"])]

    df = df.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)
    antal = len(df)

    if antal == 0:
        st.info("Inga bolag matchar filtret.")
        return

    if "index" not in st.session_state:
        st.session_state.index = 0

    index = st.session_state.index
    index = min(index, antal - 1)
    rad = df.iloc[index]

    st.markdown(f"### 📈 Förslag {index+1} av {antal}")
    st.markdown(f"""
    **Bolag:** {rad['Bolagsnamn']} ({rad['Ticker']})  
    **Kurs:** {rad['Kurs']} {rad['Valuta']}  
    **Utdelning:** {rad['Utdelning']}  
    **Direktavkastning:** {rad['Direktavkastning (%)']} %  
    **52w High:** {rad['52w High']}  
    **Riktkurs:** {round(rad['Riktkurs'], 2)}  
    **Uppside:** {rad['Uppside (%)']} %  
    **Rekommendation:** {rad['Rekommendation']}  
    **Datakälla utdelning:** {rad['Datakälla utdelning']}
    """)

    if st.button("➡️ Nästa förslag"):
        st.session_state.index = (index + 1) % antal

def uppdatera_kurs_och_utdelning(ticker):
    try:
        yfdata = yf.Ticker(ticker)
        info = yfdata.info
        kurs = info.get("regularMarketPrice", 0)
        high = info.get("fiftyTwoWeekHigh", 0)
        utd = info.get("dividendRate", 0)
        källa = "Yahoo Finance" if utd else "Manuell"
        return kurs, high, utd, källa
    except Exception:
        return 0, 0, 0, "Fel vid hämtning"

def vy_uppdatera(df):
    st.subheader("🔄 Uppdatera data från Yahoo Finance")

    val = st.radio("Välj alternativ", ["Uppdatera alla bolag", "Uppdatera enskilt bolag"])
    if val == "Uppdatera enskilt bolag":
        tickers = df["Ticker"].dropna().unique().tolist()
        valt = st.selectbox("Välj ticker", tickers)

        if st.button("Uppdatera detta bolag"):
            kurs, high, utd, källa = uppdatera_kurs_och_utdelning(valt)
            df.loc[df["Ticker"] == valt, "Kurs"] = kurs
            df.loc[df["Ticker"] == valt, "52w High"] = high
            df.loc[df["Ticker"] == valt, "Utdelning"] = utd
            df.loc[df["Ticker"] == valt, "Datakälla utdelning"] = källa
            st.success(f"✅ {valt} uppdaterad!")
            spara_data(df)

    else:
        omgång = df.copy()
        misslyckade = []
        status = st.empty()
        bar = st.progress(0)

        if st.button("Uppdatera alla bolag"):
            with st.spinner("Uppdaterar..."):
                totalt = len(omgång)
                for i, rad in omgång.iterrows():
                    ticker = rad["Ticker"]
                    status.text(f"Uppdaterar {i + 1} av {totalt} – {ticker}")
                    kurs, high, utd, källa = uppdatera_kurs_och_utdelning(ticker)

                    if kurs == 0:
                        misslyckade.append(ticker)
                    df.loc[df["Ticker"] == ticker, "Kurs"] = kurs
                    df.loc[df["Ticker"] == ticker, "52w High"] = high
                    df.loc[df["Ticker"] == ticker, "Utdelning"] = utd
                    df.loc[df["Ticker"] == ticker, "Datakälla utdelning"] = källa

                    bar.progress((i + 1) / totalt)
                    time.sleep(1)

            spara_data(df)
            status.text("✅ Alla bolag är uppdaterade!")
            st.success("✅ Alla bolag är uppdaterade!")
            if misslyckade:
                st.warning("Kunde inte uppdatera följande tickers:\n" + ", ".join(misslyckade))

def main():
    st.title("📊 Utdelningsaktier med analys")

    df = hamta_data()
    df = säkerställ_kolumner(df)

    meny = st.sidebar.radio("Meny", ["🔍 Bläddra förslag", "🔁 Uppdatera data"])
    filter_ägda = st.sidebar.checkbox("Visa endast ägda bolag", value=False)
    riktkurs_procent = st.sidebar.selectbox("Riktkurs (% under 52w High)", list(range(1, 11)), index=4)

    df = beräkna_rekommendationer(df, riktkurs_procent)

    if meny == "🔍 Bläddra förslag":
        bläddra_förslag(df, filter_ägda)
    elif meny == "🔁 Uppdatera data":
        vy_uppdatera(df)

if __name__ == "__main__":
    main()
