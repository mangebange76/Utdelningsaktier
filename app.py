import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import time

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

@st.cache_data
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

def säkerställ_kolumner(df):
    kolumner = ["Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
                "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"]
    for kol in kolumner:
        if kol not in df.columns:
            df[kol] = ""
    return df[kolumner]

def beräkna_uppdateringar(df):
    for i, rad in df.iterrows():
        try:
            kurs = float(rad["Kurs"])
            utdelning = float(rad["Utdelning"])
            high = float(rad["52w High"])
            riktkurs = float(rad["Riktkurs"])

            df.at[i, "Direktavkastning (%)"] = round((utdelning / kurs) * 100, 2) if kurs > 0 else 0
            df.at[i, "Uppside (%)"] = round((riktkurs - kurs) / kurs * 100, 2) if kurs > 0 else 0

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
        except:
            continue
    return df

def hämta_yahoo_data(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "Kurs": info.get("currentPrice"),
            "52w High": info.get("fiftyTwoWeekHigh"),
            "Utdelning": info.get("dividendRate"),
            "Valuta": info.get("currency"),
            "Bolagsnamn": info.get("shortName"),
            "Datakälla utdelning": "Yahoo Finance"
        }
    except:
        return {}

def lägg_till_eller_uppdatera(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    namn_map = {f"{rad['Bolagsnamn']} ({rad['Ticker']})": rad['Ticker'] for _, rad in df.iterrows()}
    valt = st.selectbox("Välj bolag att uppdatera (eller lämna tom för nytt)", [""] + sorted(namn_map.keys()))
    befintlig = pd.Series(dtype=object)
    if valt:
        ticker_vald = namn_map[valt]
        befintlig = df[df["Ticker"] == ticker_vald].iloc[0]

    with st.form("form"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "")).upper()
        riktkurs = st.number_input("Riktkurs", value=float(befintlig.get("Riktkurs", 0)) if not befintlig.empty else 0.0)
        äger = st.selectbox("Äger?", ["Ja", "Nej"], index=0 if befintlig.get("Äger", "Nej") == "Ja" else 1)

        sparaknapp = st.form_submit_button("💾 Spara bolag")

    if sparaknapp and ticker:
        yahoo_data = hämta_yahoo_data(ticker)
        if yahoo_data:
            st.success(f"""✅ Data hämtad:
- Kurs: {yahoo_data.get("Kurs")}
- 52w High: {yahoo_data.get("52w High")}
- Utdelning: {yahoo_data.get("Utdelning")}
- Valuta: {yahoo_data.get("Valuta")}
- Namn: {yahoo_data.get("Bolagsnamn")}
""")
        else:
            st.warning("❗️Ingen data kunde hämtas från Yahoo Finance, fyll i manuellt.")

        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": yahoo_data.get("Bolagsnamn", befintlig.get("Bolagsnamn", "")),
            "Utdelning": yahoo_data.get("Utdelning", befintlig.get("Utdelning", 0)),
            "Valuta": yahoo_data.get("Valuta", befintlig.get("Valuta", "USD")),
            "Äger": äger,
            "Kurs": yahoo_data.get("Kurs", befintlig.get("Kurs", 0)),
            "52w High": yahoo_data.get("52w High", befintlig.get("52w High", 0)),
            "Riktkurs": riktkurs,
            "Datakälla utdelning": yahoo_data.get("Datakälla utdelning", "Manuell inmatning")
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
            st.success(f"{ticker} uppdaterat.")
        else:
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            st.success(f"{ticker} tillagt.")

        df = beräkna_uppdateringar(df)
        spara_data(df)
    return df

def analysvy(df):
    st.subheader("📈 Analys och investeringsförslag")
    filter_rek = st.selectbox("Filtrera på rekommendation", ["Alla"] + sorted(df["Rekommendation"].dropna().unique()))
    da_val = st.selectbox("Minsta direktavkastning (%)", [0, 3, 5, 7, 10])
    visa_ägda = st.checkbox("Visa endast bolag jag äger")

    df_filt = df.copy()
    if filter_rek != "Alla":
        df_filt = df_filt[df_filt["Rekommendation"] == filter_rek]
    df_filt["Direktavkastning (%)"] = pd.to_numeric(df_filt["Direktavkastning (%)"], errors="coerce").fillna(0)
    df_filt = df_filt[df_filt["Direktavkastning (%)"] >= da_val]
    if visa_ägda:
        df_filt = df_filt[df_filt["Äger"] == "Ja"]

    df_filt = df_filt.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    if not df_filt.empty:
        st.write(f"Hittade {len(df_filt)} bolag som matchar filtren.")
        if "visnings_index" not in st.session_state:
            st.session_state.visnings_index = 0

        index = st.session_state.visnings_index
        if index >= len(df_filt):
            index = 0

        rad = df_filt.iloc[index]
        st.markdown(f"""
        ### 💡 Förslag {index+1} av {len(df_filt)}
        - **{rad['Bolagsnamn']} ({rad['Ticker']})**
        - Kurs: {rad['Kurs']} {rad['Valuta']}
        - Riktkurs: {rad['Riktkurs']} {rad['Valuta']}
        - Utdelning: {rad['Utdelning']} {rad['Valuta']}
        - Direktavkastning: {rad['Direktavkastning (%)']}%
        - Uppside: {rad['Uppside (%)']}%
        - Rekommendation: {rad['Rekommendation']}
        """)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Föregående"):
                st.session_state.visnings_index = max(index - 1, 0)
        with col2:
            if st.button("➡️ Nästa"):
                st.session_state.visnings_index = min(index + 1, len(df_filt) - 1)
    else:
        st.info("Inga bolag matchar dina filter.")

    st.markdown("### 📋 Alla bolag i databasen")
    st.dataframe(df, use_container_width=True)

def uppdatera_enskilt(df):
    st.subheader("🔄 Uppdatera enskilt bolag")
    tickers = df["Ticker"].dropna().unique().tolist()
    vald = st.selectbox("Välj bolag att uppdatera från Yahoo", tickers)
    if st.button("🔁 Hämta data"):
        data = hämta_yahoo_data(vald)
        if data:
            for nyckel, värde in data.items():
                if nyckel in df.columns:
                    df.loc[df["Ticker"] == vald, nyckel] = värde
            st.success(f"{vald} uppdaterat.")
            df = beräkna_uppdateringar(df)
            spara_data(df)
        else:
            st.warning("Kunde inte hämta data.")

def main():
    st.title("📊 Utdelningsaktier")
    df = hamta_data()
    df = säkerställ_kolumner(df)
    df = beräkna_uppdateringar(df)

    meny = st.sidebar.radio("Meny", ["Analys & Förslag", "Lägg till / uppdatera bolag", "Uppdatera enskilt bolag"])
    if meny == "Analys & Förslag":
        analysvy(df)
    elif meny == "Lägg till / uppdatera bolag":
        df = lägg_till_eller_uppdatera(df)
    elif meny == "Uppdatera enskilt bolag":
        uppdatera_enskilt(df)

if __name__ == "__main__":
    main()
