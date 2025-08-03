import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
import time
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# Konstanter
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
VALUTOR = ["USD", "NOK", "SEK", "EUR", "CAD"]

# Skapa koppling till Google Sheets
def skapa_koppling():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["GOOGLE_CREDENTIALS"], scope)
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

# Läs data från Google Sheets
def hamta_data():
    sheet = skapa_koppling()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Spara tillbaka till Google Sheets
def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.append_row(df.columns.tolist())
    for _, row in df.iterrows():
        sheet.append_row([str(x) for x in row.tolist()])

# Säkerställ att alla kolumner finns
def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
        "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation",
        "Datakälla utdelning", "EPS TTM", "EPS om 2 år", "Payout ratio TTM (%)", "Payout ratio 2 år (%)"
    ]
    for kolumn in kolumner:
        if kolumn not in df.columns:
            df[kolumn] = ""
    return df

# Beräkna nyckeltal för ett bolag
def beräkna_och_uppdatera_rad(row):
    try:
        kurs = float(row["Kurs"])
        high = float(row["52w High"])
        utdelning = float(row["Utdelning"])
        eps_ttm = float(row["EPS TTM"]) if row["EPS TTM"] else None
        eps_2y = float(row["EPS om 2 år"]) if row["EPS om 2 år"] else None

        row["Direktavkastning (%)"] = round(100 * utdelning / kurs, 2) if kurs else ""
        row["Riktkurs"] = round(0.95 * high, 2) if high else ""
        row["Uppside (%)"] = round(100 * (row["Riktkurs"] - kurs) / kurs, 2) if kurs and row["Riktkurs"] else ""
        row["Rekommendation"] = ge_rekommendation(row)

        # Payout ratios
        if eps_ttm:
            row["Payout ratio TTM (%)"] = round(100 * utdelning / eps_ttm, 2)
        if eps_2y:
            row["Payout ratio 2 år (%)"] = round(100 * utdelning / eps_2y, 2)

    except Exception:
        pass
    return row

# Ge rekommendation baserat på uppsida
def ge_rekommendation(row):
    try:
        uppsida = float(row["Uppside (%)"])
        if uppsida >= 50:
            return "Köp mycket"
        elif uppsida >= 10:
            return "Öka"
        elif uppsida >= 3:
            return "Behåll"
        elif uppsida > -5:
            return "Pausa"
        else:
            return "Sälj"
    except:
        return ""

def hämta_data_från_yahoo(ticker):
    try:
        aktie = yf.Ticker(ticker)
        info = aktie.info
        data = {
            "Ticker": ticker.upper(),
            "Bolagsnamn": info.get("longName", ""),
            "Utdelning": info.get("dividendRate", ""),
            "Valuta": info.get("currency", ""),
            "Kurs": info.get("currentPrice", ""),
            "52w High": info.get("fiftyTwoWeekHigh", ""),
            "EPS TTM": info.get("trailingEps", ""),
            "EPS om 2 år": info.get("earningsForecast", {}).get("avg", ""),  # försök till framtida EPS
            "Datakälla utdelning": "Yahoo Finance"
        }
        return data
    except Exception:
        return {}

def lägg_till_eller_uppdatera(df):
    st.header("Lägg till eller uppdatera bolag")
    tickers = df["Ticker"].tolist()
    valt_bolag = st.selectbox("Välj bolag att uppdatera (eller lämna tomt för nytt):", [""] + tickers)

    if valt_bolag:
        row = df[df["Ticker"] == valt_bolag].iloc[0].to_dict()
    else:
        row = {k: "" for k in df.columns}

    with st.form("lägg_till_formulär", clear_on_submit=False):
        ticker = st.text_input("Ticker", value=row["Ticker"])
        bolagsnamn = st.text_input("Bolagsnamn", value=row["Bolagsnamn"])
        utdelning = st.text_input("Utdelning", value=row["Utdelning"])
        valuta = st.selectbox("Valuta", ["", "SEK", "USD", "EUR", "NOK", "CAD"], index=0 if row["Valuta"] == "" else ["", "SEK", "USD", "EUR", "NOK", "CAD"].index(row["Valuta"]))
        kurs = st.text_input("Kurs", value=row["Kurs"])
        high = st.text_input("52w High", value=row["52w High"])
        eps_ttm = st.text_input("EPS TTM", value=row.get("EPS TTM", ""))
        eps_2y = st.text_input("EPS om 2 år", value=row.get("EPS om 2 år", ""))
        äger = st.selectbox("Äger", ["", "Ja", "Nej"], index=["", "Ja", "Nej"].index(row["Äger"] if row["Äger"] in ["Ja", "Nej"] else ""))

        if st.form_submit_button("Spara bolag"):
            yahoo_data = hämta_data_från_yahoo(ticker)
            if yahoo_data:
                bolagsnamn = yahoo_data.get("Bolagsnamn", bolagsnamn)
                utdelning = yahoo_data.get("Utdelning", utdelning)
                valuta = yahoo_data.get("Valuta", valuta)
                kurs = yahoo_data.get("Kurs", kurs)
                high = yahoo_data.get("52w High", high)
                eps_ttm = yahoo_data.get("EPS TTM", eps_ttm)
                eps_2y = yahoo_data.get("EPS om 2 år", eps_2y)
                källa = "Yahoo Finance"
                st.success(f"Data hämtad från Yahoo Finance:\n\nKurs: {kurs}, Utdelning: {utdelning}, Valuta: {valuta}")
            else:
                källa = "Manuell inmatning"
                st.warning("Ingen data kunde hämtas från Yahoo Finance. Vänligen fyll i manuellt.")

            ny_rad = {
                "Ticker": ticker.upper(),
                "Bolagsnamn": bolagsnamn,
                "Utdelning": utdelning,
                "Valuta": valuta,
                "Äger": äger,
                "Kurs": kurs,
                "52w High": high,
                "EPS TTM": eps_ttm,
                "EPS om 2 år": eps_2y,
                "Datakälla utdelning": källa
            }

            ny_rad = beräkna_och_uppdatera_rad(ny_rad)
            df = df[df["Ticker"] != ny_rad["Ticker"]]
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            spara_data(df)
            st.success(f"{ticker.upper()} sparat!")

def visa_investeringsanalys(df):
    st.header("Analys och investeringsförslag")

    alla_rekommendationer = sorted(df["Rekommendation"].dropna().unique().tolist())
    valda_rek = st.multiselect("Filtrera på rekommendation(er):", alla_rekommendationer, default=alla_rekommendationer)

    direktavkastning_val = st.selectbox("Filtrera på direktavkastning över:", ["Ingen", "3%", "5%", "7%", "10%"])
    direktgräns = {"Ingen": 0, "3%": 3, "5%": 5, "7%": 7, "10%": 10}[direktavkastning_val]

    endast_ägda = st.checkbox("Visa endast bolag jag äger")

    payout_max = st.slider("Maximal payout ratio om 2 år (%)", 0, 100, 100)
    växande_vinst = st.checkbox("Visa endast bolag med växande EPS")

    filtrerad = df.copy()
    filtrerad["Direktavkastning (%)"] = pd.to_numeric(filtrerad["Direktavkastning (%)"], errors="coerce")
    filtrerad["Payout ratio 2 år (%)"] = pd.to_numeric(filtrerad.get("Payout ratio 2 år (%)", 0), errors="coerce")
    filtrerad["EPS TTM"] = pd.to_numeric(filtrerad.get("EPS TTM", 0), errors="coerce")
    filtrerad["EPS om 2 år"] = pd.to_numeric(filtrerad.get("EPS om 2 år", 0), errors="coerce")

    filtrerad = filtrerad[filtrerad["Rekommendation"].isin(valda_rek)]
    filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= direktgräns]
    filtrerad = filtrerad[filtrerad["Payout ratio 2 år (%)"] <= payout_max]

    if växande_vinst:
        filtrerad = filtrerad[filtrerad["EPS om 2 år"] > filtrerad["EPS TTM"]]

    if endast_ägda:
        filtrerad = filtrerad[filtrerad["Äger"] == "Ja"]

    filtrerad = filtrerad.sort_values(by="Uppside (%)", ascending=False, na_position="last").reset_index(drop=True)

    antal = len(filtrerad)
    st.write(f"{antal} bolag matchar filtren.")

    if antal > 0:
        index = st.number_input("Bläddra mellan förslag:", min_value=1, max_value=antal, value=1, step=1)
        bolag = filtrerad.iloc[index - 1]
        st.subheader(f"Förslag {index} av {antal}")
        for k, v in bolag.items():
            st.write(f"**{k}**: {v}")

    with st.expander("Visa hela tabellen"):
        st.dataframe(df)

def uppdatera_alla_bolag(df):
    st.header("Uppdatera alla bolag från Yahoo Finance")

    om_start = st.button("Starta uppdatering")

    if om_start:
        misslyckade = []
        for i, row in df.iterrows():
            ticker = row["Ticker"]
            st.write(f"Uppdaterar bolag {i+1} av {len(df)}: {ticker}")
            ny_data = hämta_yahoo_data(ticker)

            if ny_data:
                for kolumn, värde in ny_data.items():
                    if värde is not None:
                        df.at[i, kolumn] = värde
                df.at[i, "Datakälla utdelning"] = "Yahoo Finance"
            else:
                misslyckade.append(ticker)

            time.sleep(1)

        spara_data(df)
        if misslyckade:
            st.warning("Kunde inte uppdatera följande tickers:\n" + ", ".join(misslyckade))
        else:
            st.success("Alla bolag har uppdaterats.")

def uppdatera_enskilt_bolag(df):
    st.header("Uppdatera enskilt bolag")

    tickers = df["Ticker"].dropna().unique().tolist()
    valt_ticker = st.selectbox("Välj bolag att uppdatera", tickers)

    if st.button("Uppdatera valt bolag"):
        index = df[df["Ticker"] == valt_ticker].index[0]
        ny_data = hämta_yahoo_data(valt_ticker)

        if ny_data:
            for kolumn, värde in ny_data.items():
                if värde is not None:
                    df.at[index, kolumn] = värde
            df.at[index, "Datakälla utdelning"] = "Yahoo Finance"
            spara_data(df)
            st.success(f"{valt_ticker} uppdaterat.")
        else:
            st.warning("Ingen data kunde hämtas från Yahoo Finance.")

def main():
    st.set_page_config(page_title="Utdelningsaktier", layout="wide")
    st.title("📈 Utdelningsaktier – Analys och uppdatering")

    df = hamta_data()
    df = säkerställ_kolumner(df)

    menyval = st.sidebar.radio("Välj vy", [
        "Analys och investeringsförslag",
        "Lägg till eller uppdatera bolag",
        "Uppdatera enskilt bolag",
        "Uppdatera alla bolag"
    ])

    if menyval == "Analys och investeringsförslag":
        visa_investeringsförslag(df)

    elif menyval == "Lägg till eller uppdatera bolag":
        lägg_till_eller_uppdatera(df)

    elif menyval == "Uppdatera enskilt bolag":
        uppdatera_enskilt_bolag(df)

    elif menyval == "Uppdatera alla bolag":
        uppdatera_alla_bolag(df)

if __name__ == "__main__":
    main()

def säkerställ_kolumner(df):
    förväntade_kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs",
        "52w High", "Direktavkastning (%)", "Riktkurs", "Uppside (%)",
        "Rekommendation", "Datakälla utdelning", "EPS TTM", "EPS om 2 år",
        "Payout ratio TTM (%)", "Payout ratio 2 år (%)"
    ]
    for kolumn in förväntade_kolumner:
        if kolumn not in df.columns:
            df[kolumn] = ""
    return df
