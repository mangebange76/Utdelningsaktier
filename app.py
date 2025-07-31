import streamlit as st
import pandas as pd
import numpy as np
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Aktieanalys och investeringsförslag", layout="wide")

SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Blad1"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

STANDARD_VALUTAKURSER = {
    "USD": 9.75,
    "NOK": 0.95,
    "CAD": 7.05,
    "EUR": 11.18,
    "SEK": 1.0
}

def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

def konvertera_typer(df):
    numeriska = [
        "Omsättning idag", "Omsättning nästa år", "Omsättning om 2 år", "Omsättning om 3 år",
        "Utestående aktier", "P/S", "P/S Q1", "P/S Q2", "P/S Q3", "P/S Q4",
        "Aktuell kurs", "Antal aktier", "Årlig utdelning", "52w high", "Riktkurs %", "Riktkurs", "Potential (%)"
    ]
    for kol in numeriska:
        if kol in df.columns:
            df[kol] = pd.to_numeric(df[kol], errors="coerce").fillna(0.0)
    return df

def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Aktuell kurs", "Utestående aktier", "P/S", "P/S Q1", "P/S Q2", "P/S Q3", "P/S Q4",
        "Omsättning idag", "Omsättning nästa år", "Omsättning om 2 år", "Omsättning om 3 år",
        "P/S-snitt", "Riktkurs idag", "Riktkurs 2026", "Riktkurs 2027", "Riktkurs 2028",
        "Antal aktier", "Valuta", "Årlig utdelning", "52w high", "Riktkurs %", "Riktkurs", "Potential (%)", "Rekommendation"
    ]
    for kol in kolumner:
        if kol not in df.columns:
            df[kol] = 0.0 if "kurs" in kol.lower() or "omsättning" in kol.lower() or "%" in kol else ""
    return df

def uppdatera_berakningar(df, riktkurs_procent=5):
    for i, rad in df.iterrows():
        ps = [rad["P/S Q1"], rad["P/S Q2"], rad["P/S Q3"], rad["P/S Q4"]]
        ps = [x for x in ps if x > 0]
        ps_snitt = round(np.mean(ps), 2) if ps else 0
        df.at[i, "P/S-snitt"] = ps_snitt

        if rad["Utestående aktier"] > 0:
            df.at[i, "Riktkurs idag"] = round((rad["Omsättning idag"] * ps_snitt) / rad["Utestående aktier"], 2)
            df.at[i, "Riktkurs 2026"] = round((rad["Omsättning nästa år"] * ps_snitt) / rad["Utestående aktier"], 2)
            df.at[i, "Riktkurs 2027"] = round((rad["Omsättning om 2 år"] * ps_snitt) / rad["Utestående aktier"], 2)
            df.at[i, "Riktkurs 2028"] = round((rad["Omsättning om 3 år"] * ps_snitt) / rad["Utestående aktier"], 2)

        # Riktkurs baserat på 52w high
        high = rad.get("52w high", 0)
        riktkurs = high * (1 - riktkurs_procent / 100)
        df.at[i, "Riktkurs %"] = riktkurs
        df.at[i, "Riktkurs"] = round(riktkurs, 2)

        kurs = rad.get("Aktuell kurs", 0)
        if kurs > 0:
            potential = (riktkurs - kurs) / kurs * 100
            df.at[i, "Potential (%)"] = round(potential, 2)

            if potential >= 20:
                rek = "Köp kraftigt"
            elif potential >= 10:
                rek = "Köp"
            elif 0 <= potential < 10:
                rek = "Behåll"
            elif -10 < potential < 0:
                rek = "Pausa"
            else:
                rek = "Sälj"
            df.at[i, "Rekommendation"] = rek
    return df

def hamta_kurs_och_valuta(ticker):
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        pris = info.get("regularMarketPrice", None)
        valuta = info.get("currency", "USD")
        high_52w = info.get("fiftyTwoWeekHigh", 0.0)
        return pris, valuta, high_52w
    except Exception:
        return None, "USD", 0.0

def analysvy(df, valutakurser):
    st.subheader("📈 Analysläge")

    riktkurs_val = st.selectbox("Välj riktkursnivå (% under 52w high)", list(range(1, 11)), index=4)
    df = uppdatera_berakningar(df, riktkurs_val)

    if st.button("🔄 Uppdatera kurser och 52w high från Yahoo"):
        misslyckade = []
        uppdaterade = 0
        total = len(df)
        status = st.empty()
        bar = st.progress(0)

        with st.spinner("Uppdaterar..."):
            for i, row in df.iterrows():
                ticker = str(row["Ticker"]).strip().upper()
                status.text(f"🔄 {i + 1}/{total}: {ticker}")
                try:
                    pris, valuta, high = hamta_kurs_och_valuta(ticker)
                    if pris is None:
                        misslyckade.append(ticker)
                        continue

                    df.at[i, "Aktuell kurs"] = round(pris, 2)
                    df.at[i, "Valuta"] = valuta
                    df.at[i, "52w high"] = round(high, 2)
                    uppdaterade += 1
                except:
                    misslyckade.append(ticker)
                bar.progress((i + 1) / total)
                time.sleep(1.5)

        spara_data(df)
        status.text("✅ Klar.")
        st.success(f"{uppdaterade} uppdaterade.")
        if misslyckade:
            st.warning("Misslyckades: " + ", ".join(misslyckade))

    st.dataframe(df, use_container_width=True)

def main():
    st.title("📊 Aktieanalys och investeringsförslag")

    df = hamta_data()
    df = säkerställ_kolumner(df)
    df = konvertera_typer(df)

    st.sidebar.header("💱 Valutakurser till SEK")
    valutakurser = {
        "USD": st.sidebar.number_input("USD → SEK", value=9.75, step=0.01),
        "NOK": st.sidebar.number_input("NOK → SEK", value=0.95, step=0.01),
        "CAD": st.sidebar.number_input("CAD → SEK", value=7.05, step=0.01),
        "EUR": st.sidebar.number_input("EUR → SEK", value=11.18, step=0.01),
    }

    meny = st.sidebar.radio("📌 Välj vy", ["Analys"])

    if meny == "Analys":
        analysvy(df, valutakurser)

if __name__ == "__main__":
    main()
