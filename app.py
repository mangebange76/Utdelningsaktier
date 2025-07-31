import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📈 Utdelningsaktier", layout="wide")

# 🔐 Google Sheets-koppling
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)
sheet = client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

# 📥 Hämta och spara data
def hamta_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

# 🧮 Beräkningar
def beräkna_fält(df, riktkurs_procent):
    df["Direktavkastning (%)"] = round(df["Utdelning"] / df["Aktuell kurs"] * 100, 2)
    df["Riktkurs"] = round(df["52w High"] * (1 - riktkurs_prosent / 100), 2)
    df["Rekommendation"] = df.apply(lambda row: rekommendation(row["Aktuell kurs"], row["Riktkurs"]), axis=1)
    return df

def rekommendation(kurs, riktkurs):
    diff = kurs - riktkurs
    if kurs < riktkurs * 0.8:
        return "Köp kraftigt"
    elif kurs < riktkurs * 0.95:
        return "Öka"
    elif abs(diff) < riktkurs * 0.05:
        return "Behåll"
    elif kurs < riktkurs * 1.1:
        return "Pausa"
    else:
        return "Sälj"

# 🔍 Formulär
def formulär(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")

    tickers = df["Ticker"].tolist()
    valt_bolag = st.selectbox("Välj bolag att uppdatera", [""] + tickers)

    if valt_bolag:
        befintlig = df[df["Ticker"] == valt_bolag].iloc[0]
    else:
        befintlig = pd.Series()

    with st.form("bolagsform"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "")).upper()
        namn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        kurs = st.number_input("Aktuell kurs", value=float(befintlig.get("Aktuell kurs", 0.0)))
        utdelning = st.number_input("Årlig utdelning per aktie", value=float(befintlig.get("Utdelning", 0.0)))
        äger = st.selectbox("Äger du aktien?", ["Nej", "Ja"], index=1 if befintlig.get("Äger", "Nej") == "Ja" else 0)

        # Automatiskt hämta 52w high från Yahoo
        if ticker:
            try:
                info = yf.Ticker(ticker).info
                high52 = round(info.get("fiftyTwoWeekHigh", 0.0), 2)
            except:
                high52 = 0.0
        else:
            high52 = 0.0

        st.markdown(f"52-week high: **{high52}**")

        sparaknapp = st.form_submit_button("💾 Spara")

    if sparaknapp and ticker:
        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": namn,
            "Aktuell kurs": kurs,
            "Utdelning": utdelning,
            "52w High": high52,
            "Äger": äger
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
            st.success(f"{ticker} uppdaterat.")
        else:
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            st.success(f"{ticker} tillagt.")
        spara_data(df)
    return df

# 🔎 Bläddra och filtrera
def bläddra(df):
    st.subheader("📋 Bolagsöversikt")

    filt_rek = st.multiselect("Filtrera på rekommendation", df["Rekommendation"].unique())
    filt_äger = st.selectbox("Visa endast innehav?", ["Alla", "Endast äger"])

    visning = df.copy()
    if filt_rek:
        visning = visning[visning["Rekommendation"].isin(filt_rek)]
    if filt_äger == "Endast äger":
        visning = visning[visning["Äger"] == "Ja"]

    if visning.empty:
        st.warning("Inga bolag matchar filtren.")
        return

    if "index" not in st.session_state:
        st.session_state.index = 0

    if st.button("⬅️ Föregående") and st.session_state.index > 0:
        st.session_state.index -= 1
    if st.button("➡️ Nästa") and st.session_state.index < len(visning) - 1:
        st.session_state.index += 1

    rad = visning.iloc[st.session_state.index]
    st.markdown(f"""
    ### 📈 {rad['Bolagsnamn']} ({rad['Ticker']})
    - **Aktuell kurs:** {rad['Aktuell kurs']}
    - **Utdelning:** {rad['Utdelning']}
    - **Direktavkastning:** {rad['Direktavkastning (%)']}%
    - **52w High:** {rad['52w High']}
    - **Riktkurs:** {rad['Riktkurs']}
    - **Rekommendation:** **{rad['Rekommendation']}**
    - **Äger:** {rad['Äger']}
    """)

# 🚀 Huvudfunktion
def main():
    st.title("📊 Utdelningsaktier – Analys & Rekommendation")

    df = hamta_data()
    if "Riktkurs" not in df.columns:
        df["Riktkurs"] = 0.0
    if "Direktavkastning (%)" not in df.columns:
        df["Direktavkastning (%)"] = 0.0
    if "Rekommendation" not in df.columns:
        df["Rekommendation"] = ""
    if "52w High" not in df.columns:
        df["52w High"] = 0.0
    if "Äger" not in df.columns:
        df["Äger"] = "Nej"

    df["Aktuell kurs"] = pd.to_numeric(df["Aktuell kurs"], errors="coerce").fillna(0)
    df["Utdelning"] = pd.to_numeric(df["Utdelning"], errors="coerce").fillna(0)
    df["52w High"] = pd.to_numeric(df["52w High"], errors="coerce").fillna(0)

    procent = st.sidebar.selectbox("Justering från 52w High för riktkurs", list(range(1, 11)), index=4)
    df = beräkna_fält(df, riktkurs_procent=procent)

    meny = st.sidebar.radio("Välj vy", ["📋 Bläddra", "➕ Lägg till / ändra bolag"])

    if meny == "➕ Lägg till / ändra bolag":
        df = formulär(df)
    else:
        bläddra(df)

if __name__ == "__main__":
    main()
