import streamlit as st
import pandas as pd
import yfinance as yf
import time
import datetime
import gspread
from google.oauth2.service_account import Credentials

# Inställningar
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"

# Behörigheter och koppling
def skapa_koppling():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

# Läs in data från Google Sheets
def hamta_data():
    sheet = skapa_koppling()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# Spara data till Google Sheets
def spara_data(df):
    sheet = skapa_koppling()
    header = sheet.row_values(1)
    if len(df.columns) != len(header):
        st.error("Antalet kolumner i data matchar inte arket. Ingen data sparades.")
        return
    sheet.clear()
    sheet.append_row(header)
    rows = df.astype(str).values.tolist()
    sheet.append_rows(rows)

# Säkerställ att alla kolumner finns
def säkerställ_kolumner(df):
    önskade_kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
        "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning",
        "EPS TTM", "EPS om 2 år", "Payout ratio TTM (%)", "Payout ratio 2 år (%)"
    ]
    for kolumn in önskade_kolumner:
        if kolumn not in df.columns:
            df[kolumn] = ""
    return df[önskade_kolumner]

# Funktion för att hämta bolagsdata från Yahoo Finance
def hämta_yahoo_data(ticker):
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info

        kurs = info.get("currentPrice")
        high_52w = info.get("fiftyTwoWeekHigh")
        utdelning = info.get("dividendRate")
        valuta = info.get("currency")
        namn = info.get("shortName")
        eps_ttm = info.get("trailingEps")
        eps_2y = info.get("forwardEps")

        return {
            "Kurs": kurs,
            "52w High": high_52w,
            "Utdelning": utdelning,
            "Valuta": valuta,
            "Bolagsnamn": namn,
            "EPS TTM": eps_ttm,
            "EPS om 2 år": eps_2y,
        }
    except Exception:
        return {}

# Beräkna bolagsdata automatiskt
def beräkna_och_komplettera(row):
    try:
        kurs = float(row.get("Kurs", 0))
        high = float(row.get("52w High", 0))
        utdelning = float(row.get("Utdelning", 0))
        eps_ttm = float(row.get("EPS TTM", 0))
        eps_2y = float(row.get("EPS om 2 år", 0))

        riktkurs = high * 0.95 if high else 0
        direktavkastning = round((utdelning / kurs) * 100, 2) if kurs else 0
        uppside = round(((riktkurs - kurs) / kurs) * 100, 2) if kurs else 0
        payout_ttm = round((utdelning / eps_ttm) * 100, 2) if eps_ttm else ""
        payout_2y = round((utdelning / eps_2y) * 100, 2) if eps_2y else ""

        if kurs <= 0 or riktkurs == 0:
            rekommendation = "Behåll"
        elif uppside >= 50:
            rekommendation = "Köp kraftigt"
        elif uppside >= 10:
            rekommendation = "Öka"
        elif uppside >= 0:
            rekommendation = "Behåll"
        elif uppside >= -10:
            rekommendation = "Pausa"
        else:
            rekommendation = "Sälj"

        row["Riktkurs"] = riktkurs
        row["Direktavkastning (%)"] = direktavkastning
        row["Uppside (%)"] = uppside
        row["Rekommendation"] = rekommendation
        row["Payout ratio TTM (%)"] = payout_ttm
        row["Payout ratio 2 år (%)"] = payout_2y

        return row
    except Exception:
        return row

def lägg_till_eller_uppdatera(df):
    st.subheader("Lägg till eller uppdatera bolag")

    alla_tickers = df["Ticker"].dropna().unique().tolist()
    val = st.selectbox("Välj bolag att uppdatera eller lämna tomt för nytt:", [""] + alla_tickers)

    if val:
        bolagsdata = df[df["Ticker"] == val].iloc[0].to_dict()
    else:
        bolagsdata = {}

    with st.form("lägg_till_formulär"):
        ticker = st.text_input("Ticker", value=bolagsdata.get("Ticker", ""))
        bolagsnamn = st.text_input("Bolagsnamn", value=bolagsdata.get("Bolagsnamn", ""))
        utdelning = st.number_input("Utdelning", min_value=0.0, value=float(bolagsdata.get("Utdelning", 0)), step=0.01)
        valuta = st.selectbox("Valuta", ["USD", "SEK", "NOK", "EUR", "CAD"], index=0 if not bolagsdata.get("Valuta") else ["USD", "SEK", "NOK", "EUR", "CAD"].index(bolagsdata.get("Valuta")))
        äger = st.checkbox("Jag äger detta bolag", value=bolagsdata.get("Äger", "") == "Ja")

        sparaknapp = st.form_submit_button("Spara bolag")

    if sparaknapp and ticker:
        ny_data = hämta_yahoo_data(ticker.upper())

        st.write("📊 **Data hämtad från Yahoo Finance:**")
        for nyckel, värde in ny_data.items():
            if värde not in [None, ""]:
                st.write(f"{nyckel}: {värde}")

        data = {
            "Ticker": ticker.upper(),
            "Bolagsnamn": ny_data.get("Bolagsnamn") or bolagsnamn,
            "Utdelning": ny_data.get("Utdelning") or utdelning,
            "Valuta": ny_data.get("Valuta") or valuta,
            "Äger": "Ja" if äger else "Nej",
            "Kurs": ny_data.get("Kurs") or 0,
            "52w High": ny_data.get("52w High") or 0,
            "EPS TTM": ny_data.get("EPS TTM") or "",
            "EPS om 2 år": ny_data.get("EPS om 2 år") or "",
            "Datakälla utdelning": "Yahoo Finance" if ny_data else "Manuell inmatning",
        }

        data = beräkna_och_komplettera(data)

        df = df[df["Ticker"] != ticker.upper()]
        df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)

        if st.checkbox("Bekräfta spara ändringar i databasen"):
            spara_data(df)
            st.success("Bolag sparat!")
        else:
            st.info("Kryssa i för att spara till databasen.")

    return df

def analysvy(df):
    st.subheader("Analys och investeringsförslag")

    # FILTER: Rekommendationer
    tillgängliga_rek = df["Rekommendation"].dropna().unique().tolist()
    rek_filter = st.selectbox("Filtrera på rekommendation:", ["Alla"] + tillgängliga_rek)

    # FILTER: Direktavkastning
    da_filter = st.selectbox("Minsta direktavkastning:", ["Ingen", "3%", "5%", "7%", "10%"])
    da_gräns = {"Ingen": 0, "3%": 3, "5%": 5, "7%": 7, "10%": 10}[da_filter]
    df["Direktavkastning (%)"] = pd.to_numeric(df["Direktavkastning (%)"], errors="coerce").fillna(0)

    # FILTER: Endast ägda bolag
    endast_ägda = st.checkbox("Visa endast bolag jag äger")

    # FILTER: Framtida EPS-vinsttillväxt
    visa_eps_filter = st.checkbox("Visa endast bolag med växande vinst (EPS om 2 år > EPS TTM)")
    df["EPS TTM"] = pd.to_numeric(df["EPS TTM"], errors="coerce").fillna(0)
    df["EPS om 2 år"] = pd.to_numeric(df["EPS om 2 år"], errors="coerce").fillna(0)

    # Tillämpa filter
    filtrerat_df = df.copy()
    if rek_filter != "Alla":
        filtrerat_df = filtrerat_df[filtrerat_df["Rekommendation"] == rek_filter]
    filtrerat_df = filtrerat_df[filtrerat_df["Direktavkastning (%)"] >= da_gräns]
    if endast_ägda:
        filtrerat_df = filtrerat_df[filtrerat_df["Äger"] == "Ja"]
    if visa_eps_filter:
        filtrerat_df = filtrerat_df[filtrerat_df["EPS om 2 år"] > filtrerat_df["EPS TTM"]]

    filtrerat_df["Uppside (%)"] = pd.to_numeric(filtrerat_df["Uppside (%)"], errors="coerce").fillna(0)
    filtrerat_df = filtrerat_df.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)

    st.write(f"📈 **{len(filtrerat_df)} bolag matchar dina filter.**")

    if not filtrerat_df.empty:
        index = st.number_input("Visa förslag:", min_value=1, max_value=len(filtrerat_df), step=1, format="%d") - 1
        rad = filtrerat_df.iloc[index]
        st.markdown(f"### Förslag {index+1} av {len(filtrerat_df)}")
        st.write(rad.to_frame().T)

    st.markdown("---")
    st.subheader("📋 Alla bolag i databasen")
    st.dataframe(df)

def massuppdatera_alla(df):
    st.subheader("🔄 Massuppdatering från Yahoo Finance")

    if st.button("Starta massuppdatering"):
        total = len(df)
        uppdaterade = 0
        kunde_inte = []

        for i, rad in df.iterrows():
            st.write(f"⏳ Uppdaterar bolag {i+1} av {total}: {rad['Ticker']}")
            nytt_data = hämta_data_yahoo(rad["Ticker"])
            time.sleep(1)

            if nytt_data:
                for kolumn, värde in nytt_data.items():
                    if kolumn in df.columns:
                        df.at[i, kolumn] = värde
                uppdaterade += 1
            else:
                kunde_inte.append(rad["Ticker"])

        if kunde_inte:
            st.warning(f"Kunde inte uppdatera följande tickers: {', '.join(kunde_inte)}")
        else:
            st.success(f"✅ Uppdatering klar! {uppdaterade} av {total} bolag uppdaterades.")

        if st.checkbox("Bekräfta att du vill spara ändringarna"):
            spara_data(df)
        else:
            st.warning("❗ Ändringar sparas inte förrän du bekräftar ovan.")

def säkerställ_kolumner(df):
    nödvändiga_kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger",
        "Kurs", "52w High", "Direktavkastning (%)", "Riktkurs", "Uppside (%)",
        "Rekommendation", "Datakälla utdelning", "EPS TTM", "EPS om 2 år",
        "Payout ratio TTM (%)", "Payout ratio 2 år (%)"
    ]
    for kolumn in nödvändiga_kolumner:
        if kolumn not in df.columns:
            df[kolumn] = ""
    return df

def main():
    st.set_page_config(page_title="📊 Utdelningsaktier", layout="wide")
    st.title("📈 Utdelningsaktie-analys")

    df = hamta_data()
    df = säkerställ_kolumner(df)

    menyval = st.sidebar.selectbox(
        "Välj vy",
        ("Analys och investeringsförslag", "Lägg till/uppdatera bolag", "Massuppdatera alla bolag")
    )

    if menyval == "Analys och investeringsförslag":
        analysvy(df)
    elif menyval == "Lägg till/uppdatera bolag":
        lägg_till_eller_uppdatera(df)
    elif menyval == "Massuppdatera alla bolag":
        massuppdatera_alla(df)

if __name__ == "__main__":
    main()
