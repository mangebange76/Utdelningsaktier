import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📈 Utdelningsaktier", layout="wide")

# 🧾 Autentisering & Google Sheets
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

def uppdatera_kurser(df, endast_ticker=None):
    total = len(df) if endast_ticker is None else 1
    lyckade, misslyckade = 0, 0

    status = st.empty()
    bar = st.progress(0)

    if endast_ticker:
        tickers = [endast_ticker]
    else:
        tickers = df["Ticker"].tolist()

    for i, ticker in enumerate(tickers):
        status.text(f"🔄 Uppdaterar {i+1} av {total} – {ticker}")
        try:
            info = yf.Ticker(ticker).info
            pris = info.get("regularMarketPrice")
            high = info.get("fiftyTwoWeekHigh")
            utdelning = info.get("dividendRate")

            idx = df[df["Ticker"] == ticker].index[0]
            if pris:
                df.at[idx, "Kurs"] = round(pris, 2)
            if high:
                df.at[idx, "52w High"] = round(high, 2)
            if utdelning is not None:
                df.at[idx, "Utdelning"] = round(utdelning, 2)
                df.at[idx, "Datakälla utdelning"] = "Yahoo"
            lyckade += 1
        except Exception:
            misslyckade += 1
        if endast_ticker is None:
            time.sleep(1)
            bar.progress((i + 1) / total)

    status.text("✅ Alla bolag är uppdaterade!" if endast_ticker is None else f"✅ {tickers[0]} uppdaterad!")
    if endast_ticker is None:
        st.success(f"Uppdaterade: {lyckade} | Misslyckade: {misslyckade}")
    return df

def beräkna_analyskolumner(df, procent=5):
    df["Direktavkastning (%)"] = (pd.to_numeric(df["Utdelning"], errors="coerce") / pd.to_numeric(df["Kurs"], errors="coerce") * 100).round(2)
    df["Riktkurs"] = (pd.to_numeric(df["52w High"], errors="coerce") * (1 - procent / 100)).round(2)
    df["Uppside (%)"] = ((df["Riktkurs"] - pd.to_numeric(df["Kurs"], errors="coerce")) / df["Kurs"] * 100).round(2)

    def rekommendation(row):
        if row["Uppside (%)"] >= 50:
            return "Köp kraftigt"
        elif row["Uppside (%)"] >= 20:
            return "Öka"
        elif row["Uppside (%)"] >= 0:
            return "Behåll"
        elif row["Uppside (%)"] > -10:
            return "Pausa"
        else:
            return "Sälj"

    df["Rekommendation"] = df.apply(rekommendation, axis=1)
    return df

def bläddra(df):
    st.subheader("📊 Investeringsvy")
    da_filter = st.selectbox("Filtrera på direktavkastning", ["Alla", "≥ 2%", "≥ 3%", "≥ 4%", "≥ 5%"])
    if da_filter != "Alla":
        gräns = int(da_filter.split("≥ ")[1].replace("%", ""))
        df = df[df["Direktavkastning (%)"] >= gräns]

    df = df.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)

    total = len(df)
    if total == 0:
        st.warning("Inga bolag matchar filtret.")
        return

    if "bolags_index" not in st.session_state:
        st.session_state.bolags_index = 0
    index = st.session_state.bolags_index
    index = min(index, total - 1)

    rad = df.iloc[index]
    st.markdown(f"### 📈 Förslag {index + 1} av {total}")
    st.markdown(f"""
        - **{rad['Bolagsnamn']}** ({rad['Ticker']})
        - Kurs: {rad['Kurs']} {rad['Valuta']}
        - Utdelning: {rad['Utdelning']} ({rad['Direktavkastning (%)']} %)
        - Riktkurs: {rad['Riktkurs']}
        - Uppside: {rad['Uppside (%)']} %
        - Rekommendation: **{rad['Rekommendation']}**
        - Datakälla utdelning: {rad['Datakälla utdelning']}
    """)

    if st.button("➡️ Nästa bolag"):
        st.session_state.bolags_index += 1
        if st.session_state.bolags_index >= total:
            st.session_state.bolags_index = 0

def main():
    st.title("📈 Utdelningsaktier – Analys och Förslag")

    df = hamta_data()

    meny = st.sidebar.radio("Välj vy", ["Investeringsvy", "Uppdatera data"])

    if meny == "Investeringsvy":
        riktkurs_procent = st.sidebar.selectbox("Riktkurs = 52w High minus", [1,2,3,4,5,6,7,8,9,10], index=4)
        df = beräkna_analyskolumner(df, procent=riktkurs_procent)
        bläddra(df)

    elif meny == "Uppdatera data":
        st.subheader("🔄 Uppdatera aktiekurser och utdelning")
        tickerlista = ["Alla bolag"] + sorted(df["Ticker"].unique())
        valt = st.selectbox("Välj ticker att uppdatera", tickerlista)

        if st.button("Uppdatera"):
            if valt == "Alla bolag":
                df = uppdatera_kurser(df)
            else:
                df = uppdatera_kurser(df, endast_ticker=valt)
            spara_data(df)

if __name__ == "__main__":
    main()
