import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

# 📄 Konfiguration
st.set_page_config(page_title="Utdelningsaktier", layout="wide")
SHEET_URL = st.secrets["SHEET_URL"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

# 📊 Kolumnstruktur
REQUIRED_COLUMNS = [
    "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
    "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
]

def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet("Bolag")

def hamta_data():
    sheet = skapa_koppling()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[REQUIRED_COLUMNS]
    return df

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

def hamta_kurs_och_52w(ticker):
    try:
        info = yf.Ticker(ticker).info
        return info.get("regularMarketPrice", 0), info.get("fiftyTwoWeekHigh", 0)
    except:
        return 0, 0

def beräkna_kolumner(df):
    for i, rad in df.iterrows():
        try:
            kurs = float(rad["Kurs"])
            utd = float(rad["Utdelning"])
            high = float(rad["52w High"])
            rikt = float(rad["Riktkurs"])
        except:
            kurs, utd, high, rikt = 0, 0, 0, 0

        df.at[i, "Direktavkastning (%)"] = round((utd / kurs) * 100, 2) if kurs > 0 else 0
        df.at[i, "Uppside (%)"] = round((rikt - kurs) / kurs * 100, 2) if kurs > 0 else 0

        uppsida = df.at[i, "Uppside (%)"]
        if uppsida >= 50:
            df.at[i, "Rekommendation"] = "Köp kraftigt"
        elif uppsida >= 10:
            df.at[i, "Rekommendation"] = "Öka"
        elif uppsida >= 3:
            df.at[i, "Rekommendation"] = "Behåll"
        elif uppsida >= 0:
            df.at[i, "Rekommendation"] = "Pausa"
        else:
            df.at[i, "Rekommendation"] = "Sälj"
    return df

def analysvy(df):
    st.header("📈 Analysläge")

    # 🎯 Filtrering
    kol1, kol2, kol3 = st.columns(3)
    with kol1:
        valda_rekommendationer = st.multiselect(
            "Filtrera på rekommendation",
            options=["Köp kraftigt", "Öka", "Behåll", "Pausa", "Sälj"],
            default=["Köp kraftigt", "Öka", "Behåll", "Pausa", "Sälj"]
        )
    with kol2:
        avkastningsfilter = st.selectbox("Direktavkastning över", [0, 3, 5, 7, 10], index=0)
    with kol3:
        visa_ägda = st.checkbox("Visa endast ägda bolag", value=False)

    df = beräkna_kolumner(df)
    filtrerad = df.copy()
    filtrerad = filtrerad[filtrerad["Rekommendation"].isin(valda_rekommendationer)]
    filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= avkastningsfilter]
    if visa_ägda:
        filtrerad = filtrerad[filtrerad["Äger"].str.lower() == "ja"]

    st.markdown(f"### Visar {len(filtrerad)} bolag")

    st.dataframe(filtrerad.sort_values("Uppside (%)", ascending=False), use_container_width=True)

def investeringsforslag(df):
    st.header("💡 Investeringsförslag")
    df = beräkna_kolumner(df)
    df = df[df["Uppside (%)"] > 0].sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    if df.empty:
        st.info("Inga investeringsförslag att visa just nu.")
        return

    if "förslag_index" not in st.session_state:
        st.session_state.förslag_index = 0

    index = st.session_state.förslag_index
    totalt = len(df)
    rad = df.iloc[index]

    st.markdown(f"""
        ### 💰 Förslag {index + 1} av {totalt}
        - **Bolag:** {rad['Bolagsnamn']} ({rad['Ticker']})
        - **Kurs:** {rad['Kurs']} {rad['Valuta']}
        - **Riktkurs:** {rad['Riktkurs']} {rad['Valuta']}
        - **Uppside:** {rad['Uppside (%)']}%
        - **Direktavkastning:** {rad['Direktavkastning (%)']}%
        - **Rekommendation:** {rad['Rekommendation']}
    """)

    if st.button("➡️ Nästa förslag"):
        st.session_state.förslag_index = (index + 1) % totalt

def uppdatera_kurser(df):
    st.header("🔄 Uppdatera kurser")
    tickers = df["Ticker"].dropna().unique().tolist()
    enskild = st.selectbox("Välj enskilt bolag att uppdatera (eller lämna tom för alla)", [""] + tickers)

    if st.button("Starta uppdatering"):
        misslyckade = []
        uppdaterade = 0

        if enskild:
            tickers_att_kolla = [enskild]
        else:
            tickers_att_kolla = tickers

        status = st.empty()
        bar = st.progress(0)
        total = len(tickers_att_kolla)

        for i, ticker in enumerate(tickers_att_kolla):
            status.text(f"Uppdaterar {i+1} av {total} – {ticker}")
            pris, high = hamta_kurs_och_52w(ticker)
            if pris == 0:
                misslyckade.append(ticker)
            else:
                df.loc[df["Ticker"] == ticker, "Kurs"] = round(pris, 2)
                df.loc[df["Ticker"] == ticker, "52w High"] = round(high, 2)
                uppdaterade += 1
            bar.progress((i + 1) / total)
            time.sleep(1)

        spara_data(df)
        status.text("✅ Alla bolag är uppdaterade!")
        st.success(f"{uppdaterade} uppdaterade.")
        if misslyckade:
            st.warning("Kunde inte uppdatera följande tickers:\n" + ", ".join(misslyckade))

def main():
    st.title("📊 Utdelningsaktier")
    df = hamta_data()

    meny = st.radio("Välj vy", ["Analys", "Investeringsförslag", "Uppdatera kurser"], horizontal=True)

    if meny == "Analys":
        analysvy(df)
    elif meny == "Investeringsförslag":
        investeringsforslag(df)
    elif meny == "Uppdatera kurser":
        uppdatera_kurser(df)

if __name__ == "__main__":
    main()
