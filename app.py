import streamlit as st
import pandas as pd
import gspread
import time
import yfinance as yf
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

# Google Sheets setup
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
    sheet.update([df.columns.tolist()] + df.astype(str).values.tolist())

def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs",
        "52w High", "Direktavkastning (%)", "Riktkurs", "Uppside (%)",
        "Rekommendation", "Datakälla utdelning"
    ]
    for kol in kolumner:
        if kol not in df.columns:
            df[kol] = ""
    return df

def beräkna_kolumner(df, procentsats):
    df["Kurs"] = pd.to_numeric(df["Kurs"], errors="coerce").fillna(0)
    df["52w High"] = pd.to_numeric(df["52w High"], errors="coerce").fillna(0)
    df["Utdelning"] = pd.to_numeric(df["Utdelning"], errors="coerce").fillna(0)
    df["Riktkurs"] = df["52w High"] * (1 - procentsats / 100)
    df["Direktavkastning (%)"] = (df["Utdelning"] / df["Kurs"]) * 100
    df["Uppside (%)"] = ((df["Riktkurs"] - df["Kurs"]) / df["Kurs"]) * 100
    df["Rekommendation"] = df["Uppside (%)"].apply(lambda x: (
        "Sälj" if x < 0 else
        "Pausa" if x < 3 else
        "Behåll" if x < 10 else
        "Öka" if x < 50 else
        "Köp kraftigt"
    ))
    return df

def färg_rekommendation(val):
    return (
        "background-color: red" if val == "Sälj" or val == "Pausa" else
        "background-color: lightgreen" if val == "Öka" else
        "background-color: green" if val == "Köp kraftigt" else
        "background-color: lightblue" if val == "Behåll" else ""
    )

def uppdatera_data(df):
    st.subheader("🔄 Uppdatera kurser och utdelning")

    val = st.radio("Vad vill du uppdatera?", ["Alla bolag", "Endast ett bolag"])
    if val == "Endast ett bolag":
        ticker = st.selectbox("Välj bolag", sorted(df["Ticker"].unique()))
        tickers = [ticker]
    else:
        tickers = df["Ticker"].unique()

    if st.button("Uppdatera"):
        misslyckade = []
        lyckade = 0
        total = len(tickers)
        status = st.empty()
        bar = st.progress(0)

        for i, ticker in enumerate(tickers, start=1):
            status.text(f"🔄 Uppdaterar {i} av {total} – {ticker}")
            try:
                aktie = yf.Ticker(ticker)
                info = aktie.info
                kurs = info.get("regularMarketPrice", None)
                high = info.get("fiftyTwoWeekHigh", None)
                utd = info.get("dividendRate", None)
                if kurs:
                    df.loc[df["Ticker"] == ticker, "Kurs"] = kurs
                if high:
                    df.loc[df["Ticker"] == ticker, "52w High"] = high
                if utd:
                    df.loc[df["Ticker"] == ticker, "Utdelning"] = utd
                    df.loc[df["Ticker"] == ticker, "Datakälla utdelning"] = "Yahoo Finance"
                lyckade += 1
            except:
                misslyckade.append(ticker)
            bar.progress(i / total)
            time.sleep(1)

        st.success(f"✅ Uppdatering klar. {lyckade} bolag uppdaterade.")
        if misslyckade:
            st.warning("Kunde inte uppdatera:
" + ", ".join(misslyckade))
        spara_data(df)

def visa_tabell(df, procentsats):
    st.subheader("📋 Alla bolag")
    äger = st.checkbox("Visa endast ägda bolag")
    if äger:
        df = df[df["Äger"].astype(str).str.lower().isin(["ja", "yes", "1"])]

    antal = len(df)
    st.caption(f"Totalt antal bolag att bläddra mellan: {antal}")

    df = beräkna_kolumner(df, procentsats)
    df = df.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    if "visnings_index" not in st.session_state:
        st.session_state.visnings_index = 0

    if st.session_state.visnings_index >= len(df):
        st.session_state.visnings_index = 0

    rad = df.iloc[st.session_state.visnings_index]
    st.markdown(f"### 📈 Förslag {st.session_state.visnings_index + 1} av {antal}")
    st.write(f"**{rad['Bolagsnamn']} ({rad['Ticker']})**")
    st.write(f"Kurs: {rad['Kurs']}, Riktkurs: {rad['Riktkurs']}, Uppside: {round(rad['Uppside (%)'], 2)}%")
    st.write(f"Utdelning: {rad['Utdelning']}, Direktavkastning: {round(rad['Direktavkastning (%)'], 2)}%")
    st.write(f"Rekommendation: **{rad['Rekommendation']}**")

    if st.button("➡️ Nästa"):
        st.session_state.visnings_index += 1

    styled_df = df.style.applymap(färg_rekommendation, subset=["Rekommendation"])
    st.dataframe(styled_df, use_container_width=True)

def main():
    st.title("💸 Utdelningsaktier – analys")

    df = hamta_data()
    df = säkerställ_kolumner(df)

    procentsats = st.sidebar.selectbox("Procent under 52w high för riktkurs", list(range(1, 11)), index=4)

    meny = st.sidebar.radio("Meny", ["Visa bolag", "Uppdatera data"])
    if meny == "Visa bolag":
        visa_tabell(df, procentsats)
    elif meny == "Uppdatera data":
        uppdatera_data(df)

if __name__ == "__main__":
    main()
