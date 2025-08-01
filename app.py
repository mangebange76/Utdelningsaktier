import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

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

def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
        "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
    ]
    for kol in kolumner:
        if kol not in df.columns:
            df[kol] = ""
    return df

def beräkna_och_uppdatera(df):
    df["Utdelning"] = pd.to_numeric(df["Utdelning"], errors="coerce").fillna(0)
    df["Kurs"] = pd.to_numeric(df["Kurs"], errors="coerce").fillna(0)
    df["52w High"] = pd.to_numeric(df["52w High"], errors="coerce").fillna(0)

    df["Direktavkastning (%)"] = round((df["Utdelning"] / df["Kurs"]) * 100, 2)
    df["Riktkurs"] = round(df["52w High"] * 0.95, 2)
    df["Uppside (%)"] = round((df["Riktkurs"] - df["Kurs"]) / df["Kurs"] * 100, 2)

    def rekommendation(row):
        if row["Uppside (%)"] >= 50:
            return "Köp mycket"
        elif row["Uppside (%)"] >= 10:
            return "Öka"
        elif row["Uppside (%)"] >= 3:
            return "Behåll"
        elif row["Uppside (%)"] >= 0:
            return "Pausa"
        else:
            return "Sälj"

    df["Rekommendation"] = df.apply(rekommendation, axis=1)
    return df

def hamta_data_yahoo(ticker):
    try:
        aktie = yf.Ticker(ticker)
        info = aktie.info
        kurs = info.get("currentPrice", None)
        high = info.get("fiftyTwoWeekHigh", None)
        utd = info.get("dividendRate", None)
        valuta = info.get("currency", "USD")
        namn = info.get("shortName", "")
        return kurs, high, utd, valuta, namn
    except:
        return None, None, None, None, None

def lägg_till_eller_uppdatera(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    namn_map = {f"{rad['Bolagsnamn']} ({rad['Ticker']})": rad['Ticker'] for _, rad in df.iterrows()}
    valt = st.selectbox("Välj bolag att uppdatera (eller lämna tomt för nytt)", [""] + sorted(namn_map.keys()))
    befintlig = df[df["Ticker"] == namn_map[valt]].iloc[0] if valt else pd.Series(dtype=object)

    with st.form("form_lagg_till"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "")).upper()
        bolagsnamn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        utd = st.number_input("Årlig utdelning", value=float(befintlig.get("Utdelning", 0)))
        valuta = st.selectbox("Valuta", ["USD", "SEK", "NOK", "EUR", "CAD"], index=0 if befintlig.empty else ["USD", "SEK", "NOK", "EUR", "CAD"].index(befintlig.get("Valuta", "USD")))
        kurs = st.number_input("Aktuell kurs", value=float(befintlig.get("Kurs", 0)))
        high = st.number_input("52w High", value=float(befintlig.get("52w High", 0)))
        äger = st.selectbox("Äger", ["Ja", "Nej"], index=0 if befintlig.get("Äger", "") == "Ja" else 1)
        spara = st.form_submit_button("💾 Spara")

    if spara and ticker:
        yahoo_kurs, yahoo_high, yahoo_utd, yahoo_valuta, yahoo_namn = hamta_data_yahoo(ticker)
        datakälla = "Yahoo Finance" if yahoo_kurs else "Manuell inmatning"

        ny = {
            "Ticker": ticker,
            "Bolagsnamn": yahoo_namn or bolagsnamn,
            "Utdelning": yahoo_utd if yahoo_utd is not None else utd,
            "Valuta": yahoo_valuta if yahoo_valuta else valuta,
            "Kurs": yahoo_kurs if yahoo_kurs is not None else kurs,
            "52w High": yahoo_high if yahoo_high is not None else high,
            "Äger": äger,
            "Datakälla utdelning": datakälla
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny.keys()] = ny.values()
            st.success(f"{ticker} uppdaterat.")
        else:
            df = pd.concat([df, pd.DataFrame([ny])], ignore_index=True)
            st.success(f"{ticker} tillagt.")

        st.info(f"✅ Hämtad data: Kurs={yahoo_kurs}, 52w High={yahoo_high}, Utdelning={yahoo_utd}, Valuta={yahoo_valuta}, Namn={yahoo_namn}")
    return df

def analysvy(df):
    st.subheader("📊 Analys & investeringsförslag")

    rekommendationer = sorted(df["Rekommendation"].unique())
    val = st.selectbox("Filtrera på rekommendation", ["Alla"] + rekommendationer)
    direktval = st.selectbox("Filtrera på direktavkastning över", ["Alla", "3", "5", "7", "10"])
    visa_ager = st.checkbox("Visa endast bolag jag äger")

    filtrerat = df.copy()
    if val != "Alla":
        filtrerat = filtrerat[filtrerat["Rekommendation"] == val]
    if direktval != "Alla":
        filtrerat = filtrerat[filtrerat["Direktavkastning (%)"] >= float(direktval)]
    if visa_ager:
        filtrerat = filtrerat[filtrerat["Äger"] == "Ja"]

    st.markdown(f"🔍 **{len(filtrerat)} bolag matchar filtren.**")
    filtrerat = filtrerat.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    if "bläddra_index" not in st.session_state:
        st.session_state.bläddra_index = 0

    if len(filtrerat) == 0:
        st.warning("Inga bolag matchar filtren.")
    else:
        i = st.session_state.bläddra_index
        if i >= len(filtrerat): i = 0
        rad = filtrerat.iloc[i]

        st.markdown(f"""
        ### 📈 Förslag {i+1} av {len(filtrerat)}
        - **{rad['Bolagsnamn']} ({rad['Ticker']})**
        - Kurs: {rad['Kurs']} {rad['Valuta']}
        - 52w High: {rad['52w High']}
        - Utdelning: {rad['Utdelning']}
        - Direktavkastning: {rad['Direktavkastning (%)']}%
        - Riktkurs: {rad['Riktkurs']}
        - Uppside: {rad['Uppside (%)']}%
        - Rekommendation: {rad['Rekommendation']}
        """)

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("⬅️ Föregående"):
                st.session_state.bläddra_index = max(0, i - 1)
        with col2:
            if st.button("➡️ Nästa"):
                st.session_state.bläddra_index = min(len(filtrerat) - 1, i + 1)

    st.markdown("---")
    st.subheader("📋 Alla bolag")
    st.dataframe(df, use_container_width=True)

def uppdatera_allt(df):
    st.subheader("🔁 Massuppdatering")
    if st.button("Uppdatera alla bolag från Yahoo"):
        misslyckade, uppdaterade = [], 0
        status = st.empty()
        for i, row in df.iterrows():
            status.text(f"🔄 Uppdaterar {i+1} av {len(df)}: {row['Ticker']}")
            kurs, high, utd, valuta, namn = hamta_data_yahoo(row["Ticker"])
            if kurs is not None:
                df.at[i, "Kurs"] = kurs
                df.at[i, "52w High"] = high
                df.at[i, "Utdelning"] = utd
                df.at[i, "Valuta"] = valuta
                df.at[i, "Bolagsnamn"] = namn
                df.at[i, "Datakälla utdelning"] = "Yahoo Finance"
                uppdaterade += 1
            else:
                misslyckade.append(row["Ticker"])
            time.sleep(1)

        st.success(f"{uppdaterade} bolag uppdaterade.")
        if misslyckade:
            st.warning("Misslyckades för:\n" + ", ".join(misslyckade))
        spara_data(df)

def main():
    st.title("📊 Utdelningsaktier – analys & investeringar")
    df = hamta_data()
    df = säkerställ_kolumner(df)
    df = beräkna_och_uppdatera(df)

    meny = st.sidebar.radio("Meny", ["Analys", "Lägg till / uppdatera bolag", "Massuppdatering"])
    if meny == "Analys":
        analysvy(df)
    elif meny == "Lägg till / uppdatera bolag":
        df = lägg_till_eller_uppdatera(df)
        df = beräkna_och_uppdatera(df)
        spara_data(df)
    elif meny == "Massuppdatering":
        uppdatera_allt(df)

if __name__ == "__main__":
    main()
