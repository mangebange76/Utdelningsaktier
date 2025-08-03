import streamlit as st
import pandas as pd
import yfinance as yf
import time
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"

def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    sheet = skapa_koppling()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return säkerställ_kolumner(df)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.append_row(df.columns.tolist())
    for row in df.itertuples(index=False):
        sheet.append_row([str(x) for x in row])

def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
        "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning",
        "EPS TTM", "EPS om 2 år", "Payout ratio TTM (%)", "Payout ratio 2 år (%)"
    ]
    for kol in kolumner:
        if kol not in df.columns:
            df[kol] = ""
    return df

def hämta_info_från_yahoo(ticker):
    try:
        aktie = yf.Ticker(ticker)
        info = aktie.info
        kurs = info.get("currentPrice")
        high_52w = info.get("fiftyTwoWeekHigh")
        utdelning = info.get("dividendRate")
        valuta = info.get("currency")
        namn = info.get("shortName")
        eps_ttm = info.get("trailingEps")
        eps_2y = info.get("forwardEps")
        datakälla = "Yahoo Finance"
        return kurs, high_52w, utdelning, valuta, namn, eps_ttm, eps_2y, datakälla
    except Exception:
        return None, None, None, None, None, None, None, "Manuell inmatning"

def beräkna_och_uppdatera_rad(rad):
    try:
        kurs = float(rad["Kurs"])
        high = float(rad["52w High"])
        utd = float(rad["Utdelning"])
        eps_ttm = float(rad["EPS TTM"])
        eps_2y = float(rad["EPS om 2 år"])
    except:
        kurs, high, utd, eps_ttm, eps_2y = 0, 0, 0, 0, 0

    riktkurs = high * 0.95 if high else 0
    uppsida = ((riktkurs - kurs) / kurs) * 100 if kurs else 0
    direktavkastning = (utd / kurs) * 100 if kurs and utd else 0
    payout_ttm = (utd / eps_ttm) * 100 if utd and eps_ttm else 0
    payout_2y = (utd / eps_2y) * 100 if utd and eps_2y else 0

    if kurs == 0:
        rekommendation = "Okänd"
    elif kurs < riktkurs * 0.7:
        rekommendation = "Köp kraftigt"
    elif kurs < riktkurs * 0.9:
        rekommendation = "Öka"
    elif kurs <= riktkurs:
        rekommendation = "Behåll"
    elif kurs <= riktkurs * 1.1:
        rekommendation = "Pausa"
    else:
        rekommendation = "Sälj"

    rad["Riktkurs"] = round(riktkurs, 2)
    rad["Uppside (%)"] = round(uppsida, 2)
    rad["Direktavkastning (%)"] = round(direktavkastning, 2)
    rad["Payout ratio TTM (%)"] = round(payout_ttm, 2)
    rad["Payout ratio 2 år (%)"] = round(payout_2y, 2)
    rad["Rekommendation"] = rekommendation
    return rad

def lägg_till_eller_uppdatera(df):
    st.header("Lägg till eller uppdatera bolag")
    tickers = df["Ticker"].tolist()
    val = st.selectbox("Välj bolag att uppdatera eller lämna tomt för nytt", [""] + tickers)
    nytt = val == ""
    
    with st.form("bolagsformulär"):
        ticker = st.text_input("Ticker", value=val)
        namn = st.text_input("Bolagsnamn")
        utd = st.text_input("Utdelning")
        valuta = st.selectbox("Valuta", ["USD", "SEK", "NOK", "EUR", "CAD"])
        äger = st.checkbox("Jag äger detta bolag", value=True)
        kurs = st.text_input("Kurs")
        high = st.text_input("52w High")
        eps_ttm = st.text_input("EPS TTM")
        eps_2y = st.text_input("EPS om 2 år")
        sparaknapp = st.form_submit_button("Spara")

    if sparaknapp and ticker:
        kurs_y, high_y, utd_y, valuta_y, namn_y, eps_ttm_y, eps_2y_y, källa = hämta_info_från_yahoo(ticker)

        kurs = kurs_y or kurs
        high = high_y or high
        utd = utd_y or utd
        valuta = valuta_y or valuta
        namn = namn_y or namn
        eps_ttm = eps_ttm_y or eps_ttm
        eps_2y = eps_2y_y or eps_2y

        st.info(f"Hämtad data: {namn} | {kurs} {valuta} | Utd: {utd} | 52w High: {high} | EPS TTM: {eps_ttm} | EPS 2 år: {eps_2y}")

        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": namn,
            "Utdelning": utd,
            "Valuta": valuta,
            "Äger": "Ja" if äger else "Nej",
            "Kurs": kurs,
            "52w High": high,
            "EPS TTM": eps_ttm,
            "EPS om 2 år": eps_2y,
            "Datakälla utdelning": källa
        }

        ny_rad = beräkna_och_uppdatera_rad(ny_rad)

        if nytt:
            df = df.append(ny_rad, ignore_index=True)
        else:
            df.loc[df["Ticker"] == ticker] = pd.DataFrame([ny_rad])

        spara_data(df)
        st.success("Bolaget har sparats.")

def uppdatera_enskilt(df):
    st.header("Uppdatera enskilt bolag från Yahoo Finance")
    tickers = df["Ticker"].tolist()
    val = st.selectbox("Välj bolag att uppdatera", tickers)

    if st.button("Uppdatera"):
        index = df[df["Ticker"] == val].index[0]
        kurs, high, utd, valuta, namn, eps_ttm, eps_2y, källa = hämta_info_från_yahoo(val)

        if kurs:
            if namn: df.at[index, "Bolagsnamn"] = namn
            if kurs: df.at[index, "Kurs"] = kurs
            if high: df.at[index, "52w High"] = high
            if utd: df.at[index, "Utdelning"] = utd
            if valuta: df.at[index, "Valuta"] = valuta
            if eps_ttm: df.at[index, "EPS TTM"] = eps_ttm
            if eps_2y: df.at[index, "EPS om 2 år"] = eps_2y
            df.at[index, "Datakälla utdelning"] = källa

            df.loc[index] = beräkna_och_uppdatera_rad(df.loc[index])
            spara_data(df)
            st.success("Uppdatering klar.")
        else:
            st.warning("Kunde inte hämta data från Yahoo Finance.")

def massuppdatera_alla(df):
    st.header("Massuppdatera alla bolag")
    if st.button("Starta massuppdatering"):
        totalt = len(df)
        for i, ticker in enumerate(df["Ticker"]):
            st.write(f"Uppdaterar bolag {i+1}/{totalt} – {ticker}")
            kurs, high, utd, valuta, namn, eps_ttm, eps_2y, källa = hämta_info_från_yahoo(ticker)

            index = df[df["Ticker"] == ticker].index[0]
            if kurs:
                if namn: df.at[index, "Bolagsnamn"] = namn
                if kurs: df.at[index, "Kurs"] = kurs
                if high: df.at[index, "52w High"] = high
                if utd: df.at[index, "Utdelning"] = utd
                if valuta: df.at[index, "Valuta"] = valuta
                if eps_ttm: df.at[index, "EPS TTM"] = eps_ttm
                if eps_2y: df.at[index, "EPS om 2 år"] = eps_2y
                df.at[index, "Datakälla utdelning"] = källa
                df.loc[index] = beräkna_och_uppdatera_rad(df.loc[index])
            time.sleep(1)
        spara_data(df)
        st.success("Massuppdatering klar.")

def analysvy(df):
    st.header("Analys och investeringsförslag")
    unika_rek = sorted(df["Rekommendation"].dropna().unique().tolist())
    valda_rek = st.multiselect("Filtrera på rekommendation", options=unika_rek, default=unika_rek)
    direktfilter = st.selectbox("Filtrera på direktavkastning över:", [0, 3, 5, 7, 10], index=0)
    visa_ägda = st.checkbox("Visa endast bolag jag äger", value=False)
    endast_vinstökning = st.checkbox("Visa endast bolag med växande vinst (EPS om 2 år > EPS TTM)", value=False)
    payout_gräns = st.slider("Max Payout ratio om 2 år (%)", min_value=0, max_value=100, value=100)

    filtrerad = df.copy()
    if valda_rek:
        filtrerad = filtrerad[filtrerad["Rekommendation"].isin(valda_rek)]
    filtrerad = filtrerad[pd.to_numeric(filtrerad["Direktavkastning (%)"], errors="coerce") >= direktfilter]
    if visa_ägda:
        filtrerad = filtrerad[filtrerad["Äger"] == "Ja"]
    if endast_vinstökning:
        filtrerad = filtrerad[
            pd.to_numeric(filtrerad["EPS om 2 år"], errors="coerce") >
            pd.to_numeric(filtrerad["EPS TTM"], errors="coerce")
        ]
    filtrerad = filtrerad[
        pd.to_numeric(filtrerad["Payout ratio 2 år (%)"], errors="coerce") <= payout_gräns
    ]

    filtrerad = filtrerad.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)
    antal = len(filtrerad)
    if antal > 0:
        index = st.number_input(f"Visa förslag", min_value=1, max_value=antal, value=1)
        rad = filtrerad.iloc[index - 1]
        st.subheader(f"Förslag {index} av {antal}")
        st.write(rad.to_frame().T)
    else:
        st.info("Inga bolag matchar filtret.")

    st.subheader("Samtliga bolag i databasen")
    st.dataframe(df)

def main():
    df = hamta_data()
    meny = st.sidebar.radio("Meny", ["Analys", "Lägg till/Uppdatera", "Uppdatera ett bolag", "Massuppdatera alla"])
    if meny == "Analys":
        analysvy(df)
    elif meny == "Lägg till/Uppdatera":
        lägg_till_eller_uppdatera(df)
    elif meny == "Uppdatera ett bolag":
        uppdatera_enskilt(df)
    elif meny == "Massuppdatera alla":
        massuppdatera_alla(df)

if __name__ == "__main__":
    main()
