import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📈 Utdelningsaktier", layout="wide")

SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    sheet = skapa_koppling()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

def konvertera_typer(df):
    for kol in ["Kurs", "52w High", "Utdelning"]:
        if kol in df.columns:
            df[kol] = pd.to_numeric(df[kol], errors="coerce").fillna(0.0)
    return df

def berakna_riktkurs(df, procent):
    df["Riktkurs"] = df["52w High"] * (1 - procent / 100)
    return df

def berakna_uppsida(df):
    df["Uppside (%)"] = ((df["Riktkurs"] - df["Kurs"]) / df["Kurs"]) * 100
    return df

def berakna_direktavkastning(df):
    df["Direktavkastning (%)"] = (df["Utdelning"] / df["Kurs"]) * 100
    return df

def berakna_rekommendation(df):
    def rek(row):
        if row["Kurs"] <= row["Riktkurs"] * 0.7:
            return "Köp kraftigt"
        elif row["Kurs"] <= row["Riktkurs"] * 0.9:
            return "Öka"
        elif row["Kurs"] <= row["Riktkurs"]:
            return "Behåll"
        elif row["Kurs"] <= row["Riktkurs"] * 1.1:
            return "Pausa"
        else:
            return "Sälj"
    df["Rekommendation"] = df.apply(rek, axis=1)
    return df

def uppdatera_yahoo_data(df, valt_ticker=None):
    misslyckade = []
    lyckade = 0
    total = len(df) if not valt_ticker else 1
    status = st.empty()
    bar = st.progress(0)

    for i, row in df.iterrows():
        ticker = row["Ticker"]
        if valt_ticker and ticker != valt_ticker:
            continue

        status.text(f"🔄 Uppdaterar {lyckade + 1} av {total} – {ticker}")
        try:
            info = yf.Ticker(ticker).info
            kurs = info.get("regularMarketPrice", None)
            high = info.get("fiftyTwoWeekHigh", None)
            utdelning = info.get("dividendRate", 0.0)
            källa = "Yahoo Finance" if utdelning else "Manuell"

            if kurs is None or high is None:
                misslyckade.append(ticker)
                continue

            df.at[i, "Kurs"] = round(kurs, 2)
            df.at[i, "52w High"] = round(high, 2)
            df.at[i, "Utdelning"] = round(utdelning or 0.0, 2)
            df.at[i, "Datakälla utdelning"] = källa
            lyckade += 1

        except Exception:
            misslyckade.append(ticker)

        bar.progress((lyckade + len(misslyckade)) / total)
        time.sleep(1)

    status.text("✅ Alla bolag är uppdaterade!")
    st.success(f"{lyckade} av {total} bolag uppdaterade.")
    if misslyckade:
        st.warning("Kunde inte uppdatera följande tickers:
" + ", ".join(misslyckade))
    return df

def bladdra_forslag(df):
    df = df[df["Rekommendation"].isin(["Köp kraftigt", "Öka", "Behåll"])].copy()
    df = df.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)

    st.markdown(f"**Antal förslag:** {len(df)} st")

    if df.empty:
        st.info("Inga investeringsförslag just nu.")
        return

    if "forslags_index" not in st.session_state:
        st.session_state.forslags_index = 0

    index = st.session_state.forslags_index
    if index >= len(df):
        st.session_state.forslags_index = 0
        index = 0

    rad = df.iloc[index]
    st.subheader(f"📌 Förslag {index+1} av {len(df)}")
    st.markdown(f"""
**Ticker:** {rad['Ticker']}  
**Bolagsnamn:** {rad['Bolagsnamn']}  
**Aktuell kurs:** {round(rad['Kurs'], 2)}  
**Riktkurs:** {round(rad['Riktkurs'], 2)}  
**Uppside:** {round(rad['Uppside (%)'], 2)}%  
**Direktavkastning:** {round(rad['Direktavkastning (%)'], 2)}%  
**Rekommendation:** {rad['Rekommendation']}
""")

    if st.button("➡️ Nästa förslag"):
        st.session_state.forslags_index += 1

def main():
    st.title("📈 Utdelningsaktier – investeringsanalys")

    df = hamta_data()
    df = konvertera_typer(df)

    procent = st.sidebar.selectbox("📉 Riktkurs % under 52w high", list(range(1, 11)), index=4)
    df = berakna_riktkurs(df, procent)
    df = berakna_uppsida(df)
    df = berakna_direktavkastning(df)
    df = berakna_rekommendation(df)

    meny = st.sidebar.radio("📌 Välj vy", ["Förslag", "Uppdatera kurser", "Tabell"])

    if meny == "Förslag":
        bladdra_forslag(df)
    elif meny == "Uppdatera kurser":
        st.subheader("🔄 Uppdatera data från Yahoo Finance")
        alla = st.checkbox("Uppdatera alla bolag")
        if alla:
            if st.button("Starta uppdatering"):
                df = uppdatera_yahoo_data(df)
                spara_data(df)
        else:
            tickers = df["Ticker"].tolist()
            valt = st.selectbox("Välj bolag", tickers)
            if st.button(f"Uppdatera {valt}"):
                df = uppdatera_yahoo_data(df, valt_ticker=valt)
                spara_data(df)
    else:
        st.subheader("📊 Fullständig tabell")
        st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()
