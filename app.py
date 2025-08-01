import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import time

st.set_page_config("Utdelningsaktier", layout="wide")

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

def hamta_yahoo_info(ticker):
    try:
        info = yf.Ticker(ticker).info
        pris = info.get("regularMarketPrice", None)
        valuta = info.get("currency", None)
        return pris, valuta
    except Exception:
        return None, None

def lagg_till_eller_uppdatera(df):
    st.subheader("➕ Lägg till / uppdatera bolag")
    tickers = df["Ticker"].tolist()
    valt_ticker = st.selectbox("Välj bolag att uppdatera (eller lämna tom för nytt)", [""] + tickers)

    if valt_ticker:
        befintlig = df[df["Ticker"] == valt_ticker].iloc[0]
    else:
        befintlig = pd.Series(dtype=object)

    with st.form("form"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "")).upper()
        namn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        utdelning = st.number_input("Årlig utdelning", value=float(befintlig.get("Utdelning", 0.0)))
        valuta = st.selectbox("Valuta", ["USD", "NOK", "CAD", "SEK", "EUR"], 
                              index=["USD", "NOK", "CAD", "SEK", "EUR"].index(befintlig.get("Valuta", "USD")) if not befintlig.empty else 0)
        ager = st.checkbox("Äger du aktien?", value=befintlig.get("Äger", "").lower() == "ja")
        kurs = st.number_input("Aktuell kurs", value=float(befintlig.get("Kurs", 0.0)))
        high = st.number_input("52w High", value=float(befintlig.get("52w High", 0.0)))
        datakalla = st.text_input("Datakälla utdelning", value=befintlig.get("Datakälla utdelning", "Manuell"))

        spara = st.form_submit_button("💾 Spara")

    if spara and ticker:
        pris, auto_valuta = hamta_yahoo_info(ticker)
        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": namn,
            "Utdelning": utdelning,
            "Valuta": auto_valuta if pris else valuta,
            "Äger": "Ja" if ager else "Nej",
            "Kurs": round(pris, 2) if pris else kurs,
            "52w High": high,
            "Datakälla utdelning": "Yahoo" if pris else datakalla
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
            st.success(f"{ticker} uppdaterat!")
        else:
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            st.success(f"{ticker} tillagt!")
        spara_data(df)
    return df

def berakna_och_filtrera(df):
    df["Kurs"] = pd.to_numeric(df["Kurs"], errors="coerce").fillna(0)
    df["52w High"] = pd.to_numeric(df["52w High"], errors="coerce").fillna(0)
    df["Utdelning"] = pd.to_numeric(df["Utdelning"], errors="coerce").fillna(0)

    df["Direktavkastning (%)"] = round((df["Utdelning"] / df["Kurs"]) * 100, 2)
    df["Riktkurs"] = round(df["52w High"] * 0.95, 2)
    df["Uppside (%)"] = round((df["Riktkurs"] - df["Kurs"]) / df["Kurs"] * 100, 2)
    
    def rekommendation(rad):
        if rad["Uppside (%)"] > 50:
            return "Köp kraftigt"
        elif rad["Uppside (%)"] > 20:
            return "Öka"
        elif rad["Uppside (%)"] > 5:
            return "Behåll"
        elif rad["Uppside (%)"] > -10:
            return "Pausa"
        else:
            return "Sälj"

    df["Rekommendation"] = df.apply(rekommendation, axis=1)
    return df

def analysvy(df):
    st.subheader("📊 Analys och investeringsförslag")

    df = berakna_och_filtrera(df)

    # Filtermeny
    rekommendationer = df["Rekommendation"].unique().tolist()
    val_rek = st.selectbox("📌 Välj rekommendation att filtrera på", ["Alla"] + rekommendationer)

    utdelningsval = st.selectbox("📈 Visa endast med DA över:", ["Alla", "3%", "5%", "7%", "10%"])
    visa_ager = st.checkbox("✅ Visa bara ägda bolag")

    filtrerat = df.copy()
    if val_rek != "Alla":
        filtrerat = filtrerat[filtrerat["Rekommendation"] == val_rek]
    if utdelningsval != "Alla":
        gräns = float(utdelningsval.replace("%", ""))
        filtrerat = filtrerat[filtrerat["Direktavkastning (%)"] > gräns]
    if visa_ager:
        filtrerat = filtrerat[filtrerat["Äger"].str.lower() == "ja"]

    filtrerat = filtrerat.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    if len(filtrerat) == 0:
        st.warning("Inga bolag matchar dina filter.")
        return

    if "index" not in st.session_state:
        st.session_state.index = 0

    if st.session_state.index >= len(filtrerat):
        st.session_state.index = 0

    rad = filtrerat.iloc[st.session_state.index]
    st.markdown(f"""
    ### 📌 Förslag {st.session_state.index + 1} av {len(filtrerat)}
    - **Bolag:** {rad['Bolagsnamn']} ({rad['Ticker']})
    - **Rekommendation:** {rad['Rekommendation']}
    - **Aktuell kurs:** {rad['Kurs']} {rad['Valuta']}
    - **Riktkurs (95% av 52w High):** {rad['Riktkurs']} {rad['Valuta']}
    - **Uppside:** {rad['Uppside (%)']}%
    - **Direktavkastning:** {rad['Direktavkastning (%)']}%
    """)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Föregående") and st.session_state.index > 0:
            st.session_state.index -= 1
    with col2:
        if st.button("➡️ Nästa") and st.session_state.index < len(filtrerat) - 1:
            st.session_state.index += 1

    with st.expander("📋 Visa tabell"):
        st.dataframe(filtrerat, use_container_width=True)

def uppdatera_yahoo(df):
    st.subheader("🔄 Uppdatera kurser från Yahoo Finance")
    tickers = df["Ticker"].tolist()
    enskild = st.selectbox("Välj bolag att uppdatera (eller lämna tom för alla)", [""] + tickers)

    if st.button("🔁 Uppdatera"):
        if enskild:
            tickers = [enskild]
        total = len(tickers)
        lyckade = 0
        misslyckade = []
        for i, t in enumerate(tickers):
            st.write(f"Uppdaterar {i+1} av {total}: {t}")
            pris, valuta = hamta_yahoo_info(t)
            if pris:
                df.loc[df["Ticker"] == t, "Kurs"] = round(pris, 2)
                df.loc[df["Ticker"] == t, "Valuta"] = valuta
                lyckade += 1
            else:
                misslyckade.append(t)
            time.sleep(1)
        spara_data(df)
        st.success(f"✅ Klart! {lyckade} bolag uppdaterade.")
        if misslyckade:
            st.warning("Kunde inte uppdatera: " + ", ".join(misslyckade))

def main():
    df = hamta_data()

    meny = st.sidebar.radio("Välj vy", ["Analys", "Lägg till / uppdatera", "Uppdatera Yahoo"])

    if meny == "Analys":
        analysvy(df)
    elif meny == "Lägg till / uppdatera":
        df = lagg_till_eller_uppdatera(df)
    elif meny == "Uppdatera Yahoo":
        uppdatera_yahoo(df)

if __name__ == "__main__":
    main()
