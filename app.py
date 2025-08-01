import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

# 🧾 Google Sheets setup
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

# 🧮 Funktioner
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    try:
        data = skapa_koppling().get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

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
            df[kol] = "" if " (%)" not in kol and "Kurs" not in kol else 0.0
    return df

def konvertera_typer(df):
    for kol in ["Kurs", "52w High", "Utdelning", "Direktavkastning (%)", "Riktkurs", "Uppside (%)"]:
        df[kol] = pd.to_numeric(df[kol], errors="coerce").fillna(0.0)
    return df

def beräkna_rekommendationer(df):
    df["Direktavkastning (%)"] = (df["Utdelning"] / df["Kurs"]) * 100
    df["Uppside (%)"] = ((df["Riktkurs"] - df["Kurs"]) / df["Kurs"]) * 100

    def rekommendation(row):
        if row["Kurs"] == 0 or row["Riktkurs"] == 0:
            return ""
        diff = row["Uppside (%)"]
        if diff < -10:
            return "Sälj"
        elif -10 <= diff < 0:
            return "Pausa"
        elif 0 <= diff < 10:
            return "Behåll"
        elif 10 <= diff < 25:
            return "Öka"
        else:
            return "Köp mycket"

    df["Rekommendation"] = df.apply(rekommendation, axis=1)
    return df

def hamta_yahoo_data(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "Bolagsnamn": info.get("longName") or info.get("shortName") or "",
            "Kurs": round(info.get("regularMarketPrice", 0.0), 2),
            "52w High": round(info.get("fiftyTwoWeekHigh", 0.0), 2),
            "Utdelning": round(info.get("dividendRate", 0.0), 2),
            "Valuta": info.get("currency", "USD"),
            "Datakälla utdelning": "Yahoo Finance"
        }
    except Exception:
        return {}

# 🧾 Lägg till / uppdatera bolag
def lagg_till_bolag(df):
    st.subheader("➕ Lägg till / uppdatera bolag")
    befintliga_tickers = df["Ticker"].tolist()
    tickervalue = st.text_input("Ticker (obligatoriskt)").upper()

    with st.form("nytt_bolag_form"):
        knapp = st.form_submit_button("💾 Spara bolag")

        if knapp and tickervalue:
            yahoo_data = hamta_yahoo_data(tickervalue)
            if yahoo_data:
                st.success(f"Hämtad data: Kurs {yahoo_data['Kurs']} {yahoo_data['Valuta']}, "
                           f"Utdelning {yahoo_data['Utdelning']}, High {yahoo_data['52w High']}")
            else:
                st.warning("Kunde inte hämta data från Yahoo Finance – fyll i manuellt!")

            bolag = df[df["Ticker"] == tickervalue].copy()
            ny_rad = {
                "Ticker": tickervalue,
                "Bolagsnamn": yahoo_data.get("Bolagsnamn", bolag["Bolagsnamn"].values[0] if not bolag.empty else ""),
                "Utdelning": yahoo_data.get("Utdelning", bolag["Utdelning"].values[0] if not bolag.empty else 0.0),
                "Valuta": yahoo_data.get("Valuta", bolag["Valuta"].values[0] if not bolag.empty else "USD"),
                "Kurs": yahoo_data.get("Kurs", bolag["Kurs"].values[0] if not bolag.empty else 0.0),
                "52w High": yahoo_data.get("52w High", bolag["52w High"].values[0] if not bolag.empty else 0.0),
                "Datakälla utdelning": yahoo_data.get("Datakälla utdelning", "Manuell inmatning"),
                "Äger": bolag["Äger"].values[0] if not bolag.empty else "Nej"
            }

            ny_rad["Riktkurs"] = round(ny_rad["52w High"] * 0.95, 2)
            ny_rad["Direktavkastning (%)"] = (ny_rad["Utdelning"] / ny_rad["Kurs"]) * 100 if ny_rad["Kurs"] > 0 else 0
            ny_rad["Uppside (%)"] = ((ny_rad["Riktkurs"] - ny_rad["Kurs"]) / ny_rad["Kurs"]) * 100 if ny_rad["Kurs"] > 0 else 0
            ny_rad["Rekommendation"] = ""  # Fylls i separat funktion

            df = df[df["Ticker"] != tickervalue]
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            df = beräkna_rekommendationer(df)
            spara_data(df)
            st.success("Bolag sparat.")
    return df

# 🔁 Uppdatera alla bolag från Yahoo
def uppdatera_alla(df):
    st.subheader("🔄 Uppdatera alla bolag från Yahoo Finance")
    if st.button("Starta uppdatering"):
        misslyckade = []
        totalt = len(df)
        bar = st.progress(0)
        for i, (ix, row) in enumerate(df.iterrows()):
            data = hamta_yahoo_data(row["Ticker"])
            if data:
                for key in data:
                    df.at[ix, key] = data[key]
                df.at[ix, "Riktkurs"] = round(df.at[ix, "52w High"] * 0.95, 2)
            else:
                misslyckade.append(row["Ticker"])
            bar.progress((i + 1) / totalt)
            time.sleep(1)

        df = beräkna_rekommendationer(df)
        spara_data(df)
        st.success("✅ Uppdatering klar.")
        if misslyckade:
            st.warning("Kunde inte uppdatera:\n" + ", ".join(misslyckade))

# 📊 Analys och bläddring
def analysvy(df):
    st.subheader("📈 Analys och investeringsförslag")

    # Filter
    unika_rek = sorted(df["Rekommendation"].dropna().unique())
    val_rek = st.selectbox("Filtrera på rekommendation", ["Alla"] + unika_rek)

    utdel_filter = st.selectbox("Direktavkastning minst", [0, 3, 5, 7, 10])
    visa_ager = st.checkbox("Visa endast bolag jag äger")

    filtrerad = df.copy()
    if val_rek != "Alla":
        filtrerad = filtrerad[filtrerad["Rekommendation"] == val_rek]
    if utdel_filter > 0:
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= utdel_filter]
    if visa_ager:
        filtrerad = filtrerad[filtrerad["Äger"].str.lower() == "ja"]

    if filtrerad.empty:
        st.info("Inga bolag matchar filtren.")
        return

    filtrerad = filtrerad.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    st.write(f"Visar {len(filtrerad)} bolag")

    if "index" not in st.session_state:
        st.session_state.index = 0
    index = st.session_state.index

    if index >= len(filtrerad):
        index = 0

    bolag = filtrerad.iloc[index]
    st.markdown(f"""
    ### 📌 Förslag {index+1} av {len(filtrerad)}
    - **Ticker:** {bolag['Ticker']}
    - **Bolagsnamn:** {bolag['Bolagsnamn']}
    - **Kurs:** {bolag['Kurs']} {bolag['Valuta']}
    - **52w High:** {bolag['52w High']}
    - **Riktkurs:** {bolag['Riktkurs']}
    - **Uppside:** {round(bolag['Uppside (%)'], 2)}%
    - **Direktavkastning:** {round(bolag['Direktavkastning (%)'], 2)}%
    - **Rekommendation:** {bolag['Rekommendation']}
    - **Äger:** {bolag['Äger']}
    """)

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("⬅️ Föregående"):
            st.session_state.index = max(0, index - 1)
    with col2:
        if st.button("➡️ Nästa"):
            st.session_state.index = min(len(filtrerad) - 1, index + 1)

# 🚀 Main
def main():
    st.title("📊 Utdelningsaktier – analys och förslag")
    df = hamta_data()
    df = säkerställ_kolumner(df)
    df = konvertera_typer(df)
    df = beräkna_rekommendationer(df)

    meny = st.sidebar.radio("Välj vy", ["Analys & förslag", "Lägg till bolag", "Uppdatera alla"])

    if meny == "Analys & förslag":
        analysvy(df)
    elif meny == "Lägg till bolag":
        df = lagg_till_bolag(df)
    elif meny == "Uppdatera alla":
        uppdatera_alla(df)

if __name__ == "__main__":
    main()
