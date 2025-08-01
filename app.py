import streamlit as st
import pandas as pd
import numpy as np
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
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.astype(str).values.tolist())

def filtrera_data(df):
    st.subheader("📊 Filtrera bolag")
    rekom_val = st.multiselect("📌 Filtrera på rekommendation", options=df["Rekommendation"].unique())
    direkt_val = st.multiselect("📈 Filtrera på direktavkastning över (%)", options=[3, 5, 7, 10])
    bara_ager = st.checkbox("✅ Visa endast bolag jag äger")

    if rekom_val:
        df = df[df["Rekommendation"].isin(rekom_val)]
    if direkt_val:
        min_da = max(direkt_val)
        df = df[pd.to_numeric(df["Direktavkastning (%)"], errors="coerce").fillna(0) > min_da]
    if bara_ager:
        df = df[df["Äger"].str.lower() == "ja"]

    return df.reset_index(drop=True)

def beräkna_kolumner(df):
    df["Kurs"] = pd.to_numeric(df["Kurs"], errors="coerce").fillna(0)
    df["52w High"] = pd.to_numeric(df["52w High"], errors="coerce").fillna(0)
    df["Utdelning"] = pd.to_numeric(df["Utdelning"], errors="coerce").fillna(0)

    df["Direktavkastning (%)"] = round(df["Utdelning"] / df["Kurs"] * 100, 2)
    df["Riktkurs"] = round(df["52w High"] * 0.95, 2)
    df["Uppside (%)"] = round((df["Riktkurs"] - df["Kurs"]) / df["Kurs"] * 100, 2)

    def rekommendation(rad):
        if rad["Kurs"] <= rad["Riktkurs"] * 0.6:
            return "Köp kraftigt"
        elif rad["Kurs"] <= rad["Riktkurs"] * 0.85:
            return "Öka"
        elif rad["Kurs"] <= rad["Riktkurs"]:
            return "Behåll"
        elif rad["Kurs"] <= rad["Riktkurs"] * 1.1:
            return "Pausa"
        else:
            return "Sälj"

    df["Rekommendation"] = df.apply(rekommendation, axis=1)
    return df

def bläddra_förslag(df):
    if df.empty:
        st.info("Inga bolag matchar de valda filtren.")
        return

    df = df.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)
    total = len(df)

    if "förslags_index" not in st.session_state:
        st.session_state.förslags_index = 0

    index = st.session_state.förslags_index
    index = max(0, min(index, total - 1))
    rad = df.iloc[index]

    st.markdown(f"### 📌 Förslag {index + 1} av {total}")
    st.markdown(f"""
    **Bolag:** {rad['Bolagsnamn']} ({rad['Ticker']})  
    **Aktuell kurs:** {rad['Kurs']} {rad['Valuta']}  
    **Riktkurs:** {rad['Riktkurs']} {rad['Valuta']}  
    **Uppside:** {rad['Uppside (%)']}%  
    **Direktavkastning:** {rad['Direktavkastning (%)']}%  
    **Rekommendation:** {rad['Rekommendation']}  
    """)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Föregående"):
            st.session_state.förslags_index = max(0, index - 1)
    with col2:
        if st.button("➡️ Nästa"):
            st.session_state.förslags_index = min(total - 1, index + 1)

def lägg_till_eller_uppdatera(df):
    st.subheader("➕ Lägg till / uppdatera bolag")
    tickers = [""] + sorted(df["Ticker"].unique())
    valt_ticker = st.selectbox("Välj bolag att uppdatera", tickers)

    befintlig = df[df["Ticker"] == valt_ticker].iloc[0] if valt_ticker else pd.Series(dtype=object)

    with st.form("lägg_till_form"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", ""))
        namn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        utdelning = st.number_input("Utdelning", value=float(befintlig.get("Utdelning", 0.0)))
        valuta = st.selectbox("Valuta", ["USD", "SEK", "NOK", "EUR", "CAD"], index=0)
        ager = st.selectbox("Äger", ["Ja", "Nej"], index=0 if befintlig.get("Äger", "").lower() == "ja" else 1)
        kurs = st.number_input("Kurs", value=float(befintlig.get("Kurs", 0.0)))
        high = st.number_input("52w High", value=float(befintlig.get("52w High", 0.0)))
        källa = st.text_input("Datakälla utdelning", value=befintlig.get("Datakälla utdelning", ""))

        sparaknapp = st.form_submit_button("💾 Spara")

    if sparaknapp and ticker:
        ny = {
            "Ticker": ticker, "Bolagsnamn": namn, "Utdelning": utdelning, "Valuta": valuta,
            "Äger": ager, "Kurs": kurs, "52w High": high, "Datakälla utdelning": källa
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny.keys()] = ny.values()
            st.success(f"{ticker} uppdaterat.")
        else:
            df = pd.concat([df, pd.DataFrame([ny])], ignore_index=True)
            st.success(f"{ticker} tillagt.")
    return df

def uppdatera_alla_kurser(df):
    st.subheader("🔄 Uppdatera kurser")
    if st.button("🔃 Uppdatera alla bolag från Yahoo Finance"):
        misslyckade = []
        lyckade = 0
        total = len(df)
        status = st.empty()
        bar = st.progress(0)

        for i, row in df.iterrows():
            ticker = row["Ticker"]
            status.text(f"Uppdaterar {i+1} av {total} – {ticker}")
            try:
                info = yf.Ticker(ticker).info
                pris = info.get("regularMarketPrice")
                utdelning = info.get("dividendRate")
                valuta = info.get("currency", "USD")

                if pris:
                    df.at[i, "Kurs"] = round(pris, 2)
                if utdelning is not None:
                    df.at[i, "Utdelning"] = round(utdelning, 2)
                    df.at[i, "Datakälla utdelning"] = "Yahoo Finance"
                if valuta:
                    df.at[i, "Valuta"] = valuta

                lyckade += 1
            except Exception:
                misslyckade.append(ticker)
            bar.progress((i + 1) / total)
            time.sleep(1)

        spara_data(df)
        st.success(f"✅ Alla bolag är uppdaterade! {lyckade} lyckades.")
        if misslyckade:
            st.warning("Kunde inte uppdatera följande tickers:\n" + ", ".join(misslyckade))

def main():
    st.title("📈 Utdelningsaktier – analys och förslag")

    df = hamta_data()
    df = beräkna_kolumner(df)

    meny = st.radio("🧭 Välj vy", ["Analys / förslag", "Lägg till / uppdatera", "Uppdatera från Yahoo"])

    if meny == "Analys / förslag":
        filtrerad_df = filtrera_data(df)
        bläddra_förslag(filtrerad_df)
        st.divider()
        st.subheader("📄 Tabell över filtrerade bolag")
        st.dataframe(filtrerad_df, use_container_width=True)

    elif meny == "Lägg till / uppdatera":
        df = lägg_till_eller_uppdatera(df)
        df = beräkna_kolumner(df)
        spara_data(df)

    elif meny == "Uppdatera från Yahoo":
        uppdatera_alla_kurser(df)

if __name__ == "__main__":
    main()
