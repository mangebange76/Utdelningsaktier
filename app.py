import streamlit as st
import pandas as pd
import time
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# Autentisering
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(creds)

# Konstanter
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
KOLUMNER = [
    "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
    "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning",
    "EPS TTM", "EPS om 2 år", "Payout ratio TTM (%)", "Payout ratio 2 år (%)"
]

# Funktion för att koppla till arket
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

# Funktion för att hämta data
def hamta_data():
    sheet = skapa_koppling()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df = säkerställ_kolumner(df)
    return df

# Funktion för att säkerställa alla kolumner finns
def säkerställ_kolumner(df):
    for kolumn in KOLUMNER:
        if kolumn not in df.columns:
            df[kolumn] = ""
    return df[KOLUMNER]

# Funktion för att spara data till Google Sheets
def spara_data(df):
    sheet = skapa_koppling()
    befintliga_data = sheet.get_all_values()
    if len(df) < len(befintliga_data) - 1:
        st.error("Antalet rader har minskat. Ingen data har sparats.")
        return
    sheet.clear()
    sheet.append_row(KOLUMNER)
    for _, row in df.iterrows():
        sheet.append_row([str(x) for x in row.tolist()])
    st.success("Data sparad!")

# Funktion för att hämta data från Yahoo Finance
def hämta_data_yahoo(ticker):
    try:
        info = yf.Ticker(ticker).info
        namn = info.get("longName", "")
        kurs = info.get("currentPrice", None)
        high_52w = info.get("fiftyTwoWeekHigh", None)
        utdelning = info.get("dividendRate", None)
        valuta = info.get("currency", "")
        eps_ttm = info.get("trailingEps", None)
        eps_forward = info.get("forwardEps", None)

        return {
            "Bolagsnamn": namn,
            "Kurs": kurs,
            "52w High": high_52w,
            "Utdelning": utdelning,
            "Valuta": valuta,
            "EPS TTM": eps_ttm,
            "EPS om 2 år": eps_forward,
            "Datakälla utdelning": "Yahoo Finance"
        }
    except:
        return None

# Funktion för att beräkna kompletterande värden
def beräkna_värden(row):
    try:
        kurs = float(row["Kurs"])
        high = float(row["52w High"])
        utd = float(row["Utdelning"])
        eps_ttm = float(row["EPS TTM"])
        eps_2år = float(row["EPS om 2 år"])
    except:
        return row

    if kurs > 0:
        row["Direktavkastning (%)"] = round(100 * utd / kurs, 2) if utd else ""
        row["Riktkurs"] = round(0.95 * high, 2) if high else ""
        row["Uppside (%)"] = round(100 * (row["Riktkurs"] - kurs) / kurs, 2) if row["Riktkurs"] else ""
    if eps_ttm:
        row["Payout ratio TTM (%)"] = round(100 * utd / eps_ttm, 2) if utd else ""
    if eps_2år:
        row["Payout ratio 2 år (%)"] = round(100 * utd / eps_2år, 2) if utd else ""

    # Rekommendation
    uppsida = row.get("Uppside (%)", 0)
    if isinstance(uppsida, (int, float)):
        if uppsida >= 50:
            row["Rekommendation"] = "Köp kraftigt"
        elif uppsida >= 10:
            row["Rekommendation"] = "Öka"
        elif uppsida >= 3:
            row["Rekommendation"] = "Behåll"
        elif uppsida >= 0:
            row["Rekommendation"] = "Pausa"
        else:
            row["Rekommendation"] = "Sälj"
    return row

# Lägg till eller uppdatera bolag
def lägg_till_eller_uppdatera(df):
    st.subheader("Lägg till eller uppdatera bolag")
    val = st.selectbox("Välj bolag att uppdatera eller välj 'Nytt bolag'", ["Nytt bolag"] + sorted(df["Ticker"].unique()))
    with st.form("lägg_till_formulär"):
        ticker = st.text_input("Ticker", "" if val == "Nytt bolag" else val)
        bolagsnamn = st.text_input("Bolagsnamn")
        utdelning = st.number_input("Utdelning", min_value=0.0, value=0.0)
        valuta = st.selectbox("Valuta", ["USD", "SEK", "EUR", "NOK", "CAD"])
        äger = st.checkbox("Jag äger detta bolag")
        knapp = st.form_submit_button("Spara")

    if knapp and ticker:
        data = hämta_data_yahoo(ticker)
        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": bolagsnamn,
            "Utdelning": utdelning,
            "Valuta": valuta,
            "Äger": "Ja" if äger else "Nej",
            "Kurs": "",
            "52w High": "",
            "Direktavkastning (%)": "",
            "Riktkurs": "",
            "Uppside (%)": "",
            "Rekommendation": "",
            "Datakälla utdelning": "Manuell inmatning",
            "EPS TTM": "",
            "EPS om 2 år": "",
            "Payout ratio TTM (%)": "",
            "Payout ratio 2 år (%)": ""
        }

        if data:
            for k in data:
                if k in ny_rad and data[k] is not None:
                    ny_rad[k] = data[k]

            st.success(f"Hämtade data från Yahoo Finance: Kurs={data['Kurs']}, High={data['52w High']}, Utdelning={data['Utdelning']}")

        ny_rad = beräkna_värden(ny_rad)

        df = df[df["Ticker"] != ticker]
        df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
        spara_data(df)
        st.experimental_rerun()

# Enskild uppdatering
def uppdatera_enskilt_bolag(df):
    st.subheader("Uppdatera ett enskilt bolag från Yahoo Finance")
    ticker = st.selectbox("Välj bolag", sorted(df["Ticker"].unique()))
    if st.button("Uppdatera bolag"):
        data = hämta_data_yahoo(ticker)
        if data:
            for k in data:
                if k in df.columns and data[k] is not None:
                    df.loc[df["Ticker"] == ticker, k] = data[k]
            rad = df[df["Ticker"] == ticker].iloc[0].to_dict()
            rad = beräkna_värden(rad)
            for k in rad:
                if k in df.columns:
                    df.loc[df["Ticker"] == ticker, k] = rad[k]
            spara_data(df)
            st.success(f"{ticker} har uppdaterats.")
        else:
            st.warning("Kunde inte hämta data från Yahoo Finance.")

# Massuppdatering
def massuppdatera_alla(df):
    st.subheader("Massuppdatera alla bolag från Yahoo Finance")
    if st.button("Starta massuppdatering"):
        for i, ticker in enumerate(df["Ticker"]):
            st.write(f"Uppdaterar bolag {i+1} av {len(df)}: {ticker}")
            data = hämta_data_yahoo(ticker)
            if data:
                for k in data:
                    if k in df.columns and data[k] is not None:
                        df.loc[df["Ticker"] == ticker, k] = data[k]
                rad = df[df["Ticker"] == ticker].iloc[0].to_dict()
                rad = beräkna_värden(rad)
                for k in rad:
                    if k in df.columns:
                        df.loc[df["Ticker"] == ticker, k] = rad[k]
            time.sleep(1)
        spara_data(df)
        st.success("Massuppdatering klar.")

# Analys- och investeringsvy
def analysvy(df):
    st.subheader("Analys och investeringsförslag")

    rekommendationer = sorted(df["Rekommendation"].dropna().unique())
    valda_rek = st.multiselect("Filtrera på rekommendation", options=rekommendationer, default=rekommendationer)

    direktavkastning_filter = st.selectbox("Filtrera på direktavkastning", options=["Alla", "> 3%", "> 5%", "> 7%", "> 10%"])
    äger_filter = st.checkbox("Visa endast bolag jag äger")

    payout_filter = st.selectbox("Filtrera payout ratio om 2 år", options=["Alla", "< 80%", "< 60%", "< 40%", "< 20%"])
    eps_tillväxt_filter = st.checkbox("Visa endast bolag med växande vinst (EPS om 2 år > EPS TTM)")

    filtrerat_df = df.copy()

    if valda_rek:
        filtrerat_df = filtrerat_df[filtrerat_df["Rekommendation"].isin(valda_rek)]

    if direktavkastning_filter != "Alla":
        gräns = float(direktavkastning_filter.replace("> ", "").replace("%", ""))
        filtrerat_df = filtrerat_df[pd.to_numeric(filtrerat_df["Direktavkastning (%)"], errors="coerce").fillna(0) > gräns]

    if äger_filter:
        filtrerat_df = filtrerat_df[filtrerat_df["Äger"].str.lower() == "ja"]

    if payout_filter != "Alla":
        gräns = float(payout_filter.replace("< ", "").replace("%", ""))
        filtrerat_df = filtrerat_df[pd.to_numeric(filtrerat_df["Payout ratio 2 år (%)"], errors="coerce").fillna(1000) < gräns]

    if eps_tillväxt_filter:
        filtrerat_df = filtrerat_df[
            pd.to_numeric(filtrerat_df["EPS om 2 år"], errors="coerce").fillna(0)
            > pd.to_numeric(filtrerat_df["EPS TTM"], errors="coerce").fillna(0)
        ]

    filtrerat_df = filtrerat_df.copy()
    filtrerat_df["Uppside (%)"] = pd.to_numeric(filtrerat_df["Uppside (%)"], errors="coerce").fillna(0)
    filtrerat_df = filtrerat_df.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)

    st.markdown(f"**Antal bolag som matchar filtren:** {len(filtrerat_df)}")

    if len(filtrerat_df) > 0:
        index = st.number_input("Visa förslag", min_value=1, max_value=len(filtrerat_df), step=1, value=1)
        rad = filtrerat_df.iloc[index - 1]
        st.markdown(f"**Förslag {index} av {len(filtrerat_df)}**")
        st.write(rad)

    st.subheader("Alla bolag i databasen")
    st.dataframe(df)

# Huvudfunktion
def main():
    st.title("Utdelningsaktier – analys och uppdatering")
    df = hamta_data()

    menyval = st.sidebar.radio("Meny", ["Analys & investeringsförslag", "Lägg till / uppdatera bolag", "Massuppdatera alla bolag"])

    if menyval == "Analys & investeringsförslag":
        analysvy(df)

    elif menyval == "Lägg till / uppdatera bolag":
        df = lägg_till_eller_uppdatera(df)
        analysvy(df)

    elif menyval == "Massuppdatera alla bolag":
        df = massuppdatera_alla(df)
        analysvy(df)


if __name__ == "__main__":
    main()
