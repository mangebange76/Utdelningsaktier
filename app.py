import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

# 🔐 Google Sheets-anslutning
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    try:
        data = skapa_koppling().get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame(columns=[
            "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger",
            "Kurs", "52w High", "Direktavkastning (%)",
            "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
        ])

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

# 🧠 Yahoo Finance-funktion
def hamta_yahoo_data(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "Bolagsnamn": info.get("longName", ""),
            "Kurs": round(info.get("regularMarketPrice", 0.0), 2),
            "52w High": round(info.get("fiftyTwoWeekHigh", 0.0), 2),
            "Utdelning": round(info.get("dividendRate", 0.0), 2),
            "Valuta": info.get("currency", "USD"),
            "Datakälla utdelning": "Yahoo Finance"
        }
    except Exception:
        return {
            "Bolagsnamn": "", "Kurs": 0.0, "52w High": 0.0,
            "Utdelning": 0.0, "Valuta": "USD", "Datakälla utdelning": "Manuell inmatning"
        }

def lagg_till_eller_uppdatera_bolag(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    namn_map = {f"{row['Bolagsnamn']} ({row['Ticker']})": row['Ticker'] for _, row in df.iterrows()}
    valt = st.selectbox("Välj bolag att uppdatera (eller lämna tom för nytt)", [""] + list(namn_map.keys()))

    if valt:
        ticker_vald = namn_map[valt]
        befintlig = df[df["Ticker"] == ticker_vald].iloc[0]
    else:
        befintlig = pd.Series(dtype=object)

    with st.form("bolagsform"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "") if not befintlig.empty else "").upper()
        namn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        kurs = st.number_input("Aktuell kurs", value=float(befintlig.get("Kurs", 0.0)))
        high = st.number_input("52w High", value=float(befintlig.get("52w High", 0.0)))
        utd = st.number_input("Årlig utdelning", value=float(befintlig.get("Utdelning", 0.0)))
        valuta = st.selectbox("Valuta", ["USD", "SEK", "NOK", "EUR", "CAD"], index=0 if befintlig.empty else ["USD", "SEK", "NOK", "EUR", "CAD"].index(befintlig.get("Valuta", "USD")))
        ager = st.checkbox("Jag äger detta bolag", value=(befintlig.get("Äger", "").strip().lower() == "ja"))

        sparaknapp = st.form_submit_button("💾 Spara bolag")

    if sparaknapp and ticker:
        yahoo_data = hamta_yahoo_data(ticker)
        if yahoo_data["Kurs"] > 0:
            namn = yahoo_data["Bolagsnamn"]
            kurs = yahoo_data["Kurs"]
            high = yahoo_data["52w High"]
            utd = yahoo_data["Utdelning"]
            valuta = yahoo_data["Valuta"]
            datakalla = "Yahoo Finance"
            st.success(f"Hämtade data: Kurs {kurs} {valuta}, Utdelning {utd}, 52w High {high}")
        else:
            datakalla = "Manuell inmatning"
            st.warning("Kunde inte hämta data – fyll i manuellt.")

        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": namn,
            "Utdelning": utd,
            "Valuta": valuta,
            "Äger": "Ja" if ager else "Nej",
            "Kurs": kurs,
            "52w High": high,
            "Direktavkastning (%)": round((utd / kurs) * 100, 2) if kurs > 0 else 0,
            "Datakälla utdelning": datakalla
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
            st.success(f"{ticker} uppdaterades.")
        else:
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            st.success(f"{ticker} lades till.")
    return df

def analys_och_investeringsvy(df):
    st.subheader("📈 Analys & investeringsförslag")

    if df.empty:
        st.info("Inga bolag i databasen.")
        return

    alla_rek = sorted(df["Rekommendation"].dropna().unique().tolist())
    alla_diravk = [3, 5, 7, 10]
    filter_rek = st.selectbox("Filtrera på rekommendation", ["Alla"] + alla_rek)
    filter_diravk = st.selectbox("Filtrera på direktavkastning över (%)", ["Alla"] + alla_diravk)
    endast_ager = st.checkbox("Visa endast bolag jag äger")

    filtrerad = df.copy()
    if filter_rek != "Alla":
        filtrerad = filtrerad[filtrerad["Rekommendation"] == filter_rek]

    if filter_diravk != "Alla":
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= float(filter_diravk)]

    if endast_ager:
        filtrerad = filtrerad[filtrerad["Äger"].str.lower() == "ja"]

    filtrerad = filtrerad.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    antal = len(filtrerad)
    if antal == 0:
        st.warning("Inga bolag matchar filtren.")
        return

    if "bläddra_index" not in st.session_state:
        st.session_state.bläddra_index = 0

    index = st.session_state.bläddra_index
    if index >= antal:
        index = 0
        st.session_state.bläddra_index = 0

    bolag = filtrerad.iloc[index]
    st.markdown(f"### 📌 Förslag {index + 1} av {antal}")
    st.markdown(f"""
    - **Bolag:** {bolag['Bolagsnamn']} ({bolag['Ticker']})
    - **Kurs:** {bolag['Kurs']} {bolag['Valuta']}
    - **52w High:** {bolag['52w High']}
    - **Riktkurs:** {bolag['Riktkurs']}
    - **Uppside:** {round(bolag['Uppside (%)'], 2)} %
    - **Direktavkastning:** {round(bolag['Direktavkastning (%)'], 2)} %
    - **Rekommendation:** {bolag['Rekommendation']}
    """)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Föregående"):
            st.session_state.bläddra_index = (index - 1) % antal
    with col2:
        if st.button("➡️ Nästa"):
            st.session_state.bläddra_index = (index + 1) % antal

def beräkna_uppdatera_rekommendationer(df):
    for i, row in df.iterrows():
        try:
            kurs = float(row["Kurs"])
            riktkurs = float(row["Riktkurs"])
            utdelning = float(row["Utdelning"])

            if kurs > 0 and riktkurs > 0:
                uppsida = ((riktkurs - kurs) / kurs) * 100
                df.at[i, "Uppside (%)"] = round(uppsida, 2)
            else:
                df.at[i, "Uppside (%)"] = 0.0

            if kurs > 0 and utdelning > 0:
                direktavkastning = (utdelning / kurs) * 100
                df.at[i, "Direktavkastning (%)"] = round(direktavkastning, 2)
            else:
                df.at[i, "Direktavkastning (%)"] = 0.0

            if uppsida >= 50:
                df.at[i, "Rekommendation"] = "Köp kraftigt"
            elif uppsida >= 20:
                df.at[i, "Rekommendation"] = "Öka"
            elif uppsida >= 5:
                df.at[i, "Rekommendation"] = "Behåll"
            elif uppsida >= -5:
                df.at[i, "Rekommendation"] = "Pausa"
            else:
                df.at[i, "Rekommendation"] = "Sälj"
        except Exception:
            continue
    return df


def visa_tabell(df):
    st.subheader("📋 Samtliga bolag i databasen")
    if df.empty:
        st.info("Databasen är tom.")
    else:
        st.dataframe(df, use_container_width=True)


def main():
    st.title("📈 Utdelningsaktier – analys och förslag")

    df = hamta_data()
    df = säkerställ_kolumner(df)
    df = beräkna_uppdatera_rekommendationer(df)

    meny = st.radio("Välj vy", ["Lägg till / uppdatera bolag", "Analys & investeringsförslag", "Visa tabell", "Uppdatera från Yahoo"])

    if meny == "Lägg till / uppdatera bolag":
        df = lagg_till_eller_uppdatera(df)
        df = beräkna_uppdatera_rekommendationer(df)
        spara_data(df)

    elif meny == "Analys & investeringsförslag":
        analys_och_investeringsvy(df)

    elif meny == "Visa tabell":
        visa_tabell(df)

    elif meny == "Uppdatera från Yahoo":
        df = uppdatera_alla_fran_yahoo(df)
        spara_data(df)


if __name__ == "__main__":
    main()
