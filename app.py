import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
from google.oauth2.service_account import Credentials

# 🛠️ Konfiguration
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

# 🧠 Funktioner för Google Sheets
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

# 📈 Funktioner för beräkningar
def hamta_kurser(ticker):
    try:
        aktie = yf.Ticker(ticker)
        info = aktie.info
        kurs = info.get("regularMarketPrice")
        high_52w = info.get("fiftyTwoWeekHigh")
        return kurs, high_52w
    except Exception:
        return None, None

def beräkna_och_uppdatera(df, riktkurs_procent):
    for i, rad in df.iterrows():
        try:
            kurs = float(rad["Kurs"])
            utdelning = float(rad["Utdelning"])
            high = float(rad["52w High"])
            riktkurs = round(high * (1 - riktkurs_procent / 100), 2)
            direktavkastning = round((utdelning / kurs) * 100, 2) if kurs > 0 else 0
            uppsida = round(((riktkurs - kurs) / kurs) * 100, 2) if kurs > 0 else 0

            if uppsida >= 50:
                rek = "Köp kraftigt"
            elif uppsida >= 20:
                rek = "Öka"
            elif uppsida >= 0:
                rek = "Behåll"
            elif uppsida >= -10:
                rek = "Pausa"
            else:
                rek = "Sälj"

            df.at[i, "Riktkurs"] = riktkurs
            df.at[i, "Direktavkastning (%)"] = direktavkastning
            df.at[i, "Uppside (%)"] = uppsida
            df.at[i, "Rekommendation"] = rek
        except:
            continue
    return df

# 🔧 Säkerställ kolumner
def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
        "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
    ]
    for kol in kolumner:
        if kol not in df.columns:
            df[kol] = ""
    return df[kolumner]

# 📝 Formulär
def lägg_till_bolag(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    tickers = df["Ticker"].tolist()
    valt = st.selectbox("Välj bolag att redigera", [""] + tickers)
    befintlig = df[df["Ticker"] == valt].iloc[0] if valt else pd.Series(dtype=object)

    with st.form("form"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "")).upper()
        namn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        utd = st.number_input("Utdelning", value=float(befintlig.get("Utdelning", 0)), step=0.01)
        valuta = st.selectbox("Valuta", ["USD", "SEK", "EUR", "NOK", "CAD"], index=0)
        äger = st.radio("Äger du aktien?", ["Ja", "Nej"], index=0 if befintlig.get("Äger") == "Ja" else 1)

        hämta = st.checkbox("Hämta kurs och 52w High automatiskt", value=True)
        kurs = high = 0
        if hämta and ticker:
            k, h = hamta_kurser(ticker)
            kurs = k if k else 0
            high = h if h else 0
            st.info(f"Kurs: {kurs}, 52w High: {high}")
        else:
            kurs = st.number_input("Kurs", value=float(befintlig.get("Kurs", 0)), step=0.01)
            high = st.number_input("52w High", value=float(befintlig.get("52w High", 0)), step=0.01)

        datakälla = "Yahoo Finance" if hämta else "Manuell"
        spara = st.form_submit_button("💾 Spara")

    if spara and ticker:
        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": namn,
            "Utdelning": utd,
            "Valuta": valuta,
            "Äger": äger,
            "Kurs": kurs,
            "52w High": high,
            "Datakälla utdelning": datakälla
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
            st.success("Bolag uppdaterat.")
        else:
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            st.success("Bolag tillagt.")

    return df

# 📊 Visa bläddringsfunktion
def visa_bolag(df):
    st.subheader("📋 Bolagsöversikt")
    filter_rek = st.multiselect("Filtrera på rekommendation", sorted(df["Rekommendation"].dropna().unique()))
    filter_äger = st.checkbox("Visa endast bolag jag äger")
    min_da = st.slider("Minsta direktavkastning (%)", 0.0, 15.0, 0.0)

    visning = df.copy()
    if filter_rek:
        visning = visning[visning["Rekommendation"].isin(filter_rek)]
    if filter_äger:
        visning = visning[visning["Äger"] == "Ja"]
    visning = visning[pd.to_numeric(visning["Direktavkastning (%)"], errors="coerce").fillna(0) >= min_da]

    if visning.empty:
        st.info("Inga bolag matchar filtren.")
        return

    if "index" not in st.session_state:
        st.session_state.index = 0

    rad = visning.iloc[st.session_state.index]
    st.markdown(f"""
    ### {rad['Bolagsnamn']} ({rad['Ticker']})
    - **Kurs:** {rad['Kurs']} {rad['Valuta']}
    - **Utdelning:** {rad['Utdelning']} ({rad['Direktavkastning (%)']}%)
    - **52w High:** {rad['52w High']}
    - **Riktkurs:** {rad['Riktkurs']}
    - **Uppside:** {rad['Uppside (%)']}%
    - **Rekommendation:** {rad['Rekommendation']}
    - **Äger:** {rad['Äger']}
    - **Datakälla utdelning:** {rad['Datakälla utdelning']}
    """)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Föregående") and st.session_state.index > 0:
            st.session_state.index -= 1
    with col2:
        if st.button("➡️ Nästa") and st.session_state.index < len(visning) - 1:
            st.session_state.index += 1

# 🚀 Huvudprogram
def main():
    st.title("📊 Utdelningsaktier – Översikt & Analys")
    df = hamta_data()
    df = säkerställ_kolumner(df)

    procent = st.sidebar.selectbox("Riktkurs: % under 52w High", [i for i in range(1, 11)], index=4)
    df = beräkna_och_uppdatera(df, procent)
    meny = st.sidebar.radio("Välj vy", ["Bolag", "Lägg till / uppdatera"])

    if meny == "Bolag":
        visa_bolag(df)
    else:
        df = lägg_till_bolag(df)
        spara_data(df)

if __name__ == "__main__":
    main()
