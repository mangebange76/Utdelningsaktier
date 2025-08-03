import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

# --- Google Sheets-koppling ---
def skapa_koppling():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
    client = gspread.authorize(credentials)
    sheet = client.open_by_url(st.secrets["SHEET_URL"]).worksheet("Bolag")
    return sheet

def hamta_data():
    sheet = skapa_koppling()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.append_row(list(df.columns))
    for _, row in df.iterrows():
        sheet.append_row([str(x) for x in row.tolist()])

# Hämta data från Yahoo Finance
def hämta_data_från_yahoo(ticker):
    try:
        aktie = yf.Ticker(ticker)
        info = aktie.info
        hist = aktie.history(period="1y")

        kurs = info.get("currentPrice")
        high_52w = hist["High"].max() if not hist.empty else None
        utdelning = info.get("dividendRate")
        valuta = info.get("financialCurrency")
        bolagsnamn = info.get("shortName")
        eps_ttm = info.get("trailingEps")
        eps_2y = info.get("forwardEps")

        return {
            "Kurs": kurs,
            "52w High": high_52w,
            "Utdelning": utdelning,
            "Valuta": valuta,
            "Bolagsnamn": bolagsnamn,
            "EPS TTM": eps_ttm,
            "EPS om 2 år": eps_2y,
            "Datakälla utdelning": "Yahoo Finance"
        }
    except:
        return {}

# Säkerställ att alla kolumner finns
def säkerställ_kolumner(df):
    nödvändiga_kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
        "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation",
        "Datakälla utdelning", "EPS TTM", "EPS om 2 år", "Payout ratio TTM (%)", "Payout ratio 2 år (%)"
    ]
    for kolumn in nödvändiga_kolumner:
        if kolumn not in df.columns:
            df[kolumn] = ""
    return df[nödvändiga_kolumner]

# Beräkna värden
def beräkna_och_uppdatera_rad(rad):
    try:
        kurs = float(rad["Kurs"])
        utdelning = float(rad["Utdelning"])
        high = float(rad["52w High"])
        eps_ttm = float(rad["EPS TTM"])
        eps_2y = float(rad["EPS om 2 år"])
    except:
        kurs = utdelning = high = eps_ttm = eps_2y = None

    if kurs and utdelning:
        rad["Direktavkastning (%)"] = round((utdelning / kurs) * 100, 2)
    else:
        rad["Direktavkastning (%)"] = ""

    if high:
        rad["Riktkurs"] = round(high * 0.95, 2)
    else:
        rad["Riktkurs"] = ""

    if kurs and rad["Riktkurs"]:
        rad["Uppside (%)"] = round((rad["Riktkurs"] - kurs) / kurs * 100, 2)
    else:
        rad["Uppside (%)"] = ""

    if kurs and rad["Riktkurs"]:
        uppsida = rad["Uppside (%)"]
        if uppsida >= 50:
            rad["Rekommendation"] = "Köp mycket"
        elif uppsida >= 20:
            rad["Rekommendation"] = "Öka"
        elif uppsida >= 5:
            rad["Rekommendation"] = "Behåll"
        elif uppsida > 0:
            rad["Rekommendation"] = "Pausa"
        else:
            rad["Rekommendation"] = "Sälj"
    else:
        rad["Rekommendation"] = ""

    if utdelning and eps_ttm:
        rad["Payout ratio TTM (%)"] = round((utdelning / eps_ttm) * 100, 2) if eps_ttm > 0 else ""
    else:
        rad["Payout ratio TTM (%)"] = ""

    if utdelning and eps_2y:
        rad["Payout ratio 2 år (%)"] = round((utdelning / eps_2y) * 100, 2) if eps_2y > 0 else ""
    else:
        rad["Payout ratio 2 år (%)"] = ""

    return rad

def lägg_till_eller_uppdatera(df):
    st.subheader("Lägg till eller uppdatera bolag")

    befintliga_tickers = df["Ticker"].tolist()
    val = st.selectbox("Välj bolag att uppdatera eller lämna tomt för nytt", [""] + befintliga_tickers)

    with st.form("lägg_till_formulär"):
        ticker = st.text_input("Ticker", value=val if val else "")
        bolagsnamn = st.text_input("Bolagsnamn")
        utdelning = st.text_input("Utdelning")
        valuta = st.selectbox("Valuta", ["USD", "SEK", "NOK", "EUR", "CAD"])
        äger = st.checkbox("Äger", value=False)
        kurs = st.text_input("Aktuell kurs")
        high = st.text_input("52w High")
        eps_ttm = st.text_input("EPS TTM")
        eps_2y = st.text_input("EPS om 2 år")

        if st.form_submit_button("Spara"):
            hämtad_data = hämta_data_från_yahoo(ticker)
            if hämtad_data:
                kurs = hämtad_data.get("Kurs", kurs)
                high = hämtad_data.get("52w High", high)
                utdelning = hämtad_data.get("Utdelning", utdelning)
                valuta = hämtad_data.get("Valuta", valuta)
                bolagsnamn = hämtad_data.get("Bolagsnamn", bolagsnamn)
                eps_ttm = hämtad_data.get("EPS TTM", eps_ttm)
                eps_2y = hämtad_data.get("EPS om 2 år", eps_2y)
                källa = hämtad_data.get("Datakälla utdelning", "Yahoo Finance")

                st.success(f"Hämtade data från Yahoo Finance för {ticker}: {kurs} {valuta}")
            else:
                st.warning("Kunde inte hämta data från Yahoo Finance. Fyll i manuellt.")
                källa = "Manuell inmatning"

            ny_rad = {
                "Ticker": ticker,
                "Bolagsnamn": bolagsnamn,
                "Utdelning": utdelning,
                "Valuta": valuta,
                "Äger": "Ja" if äger else "Nej",
                "Kurs": kurs,
                "52w High": high,
                "EPS TTM": eps_ttm,
                "EPS om 2 år": eps_2y,
                "Datakälla utdelning": källa
            }

            ny_rad = beräkna_och_uppdatera_rad(ny_rad)
            ny_rad_df = pd.DataFrame([ny_rad])
            df = df[df["Ticker"] != ticker]
            df = pd.concat([df, ny_rad_df], ignore_index=True)
            spara_data(df)
            st.success(f"Bolaget {ticker} har sparats/uppdaterats.")

    return df

# --- Analysvy ---
def analysvy(df):
    st.header("📊 Analys och investeringsförslag")

    rekommendationer = df["Rekommendation"].dropna().unique().tolist()
    rekommendation_val = st.selectbox("Välj rekommendation att filtrera på", ["Alla"] + rekommendationer)

    direktavkastning_filter = st.selectbox("Direktavkastning över", [0, 3, 5, 7, 10])
    visa_endast_ager = st.checkbox("Visa endast bolag jag äger")

    eps_tillvaxt = st.checkbox("Visa endast bolag med växande vinst (EPS om 2 år > EPS TTM)")

    payout_min = st.slider("Filtrera payout ratio 2 år (%)", 0, 200, (0, 100))

    filtrerat_df = df.copy()
    if rekommendation_val != "Alla":
        filtrerat_df = filtrerat_df[filtrerat_df["Rekommendation"] == rekommendation_val]

    filtrerat_df["Direktavkastning (%)"] = pd.to_numeric(filtrerat_df["Direktavkastning (%)"], errors="coerce")
    filtrerat_df = filtrerat_df[filtrerat_df["Direktavkastning (%)"] > direktavkastning_filter]

    if visa_endast_ager:
        filtrerat_df = filtrerat_df[filtrerat_df["Äger"].str.lower() == "ja"]

    filtrerat_df["EPS TTM"] = pd.to_numeric(filtrerat_df["EPS TTM"], errors="coerce")
    filtrerat_df["EPS om 2 år"] = pd.to_numeric(filtrerat_df["EPS om 2 år"], errors="coerce")
    if eps_tillvaxt:
        filtrerat_df = filtrerat_df[filtrerat_df["EPS om 2 år"] > filtrerat_df["EPS TTM"]]

    filtrerat_df["Payout ratio 2 år (%)"] = pd.to_numeric(filtrerat_df["Payout ratio 2 år (%)"], errors="coerce")
    filtrerat_df = filtrerat_df[
        (filtrerat_df["Payout ratio 2 år (%)"] >= payout_min[0]) &
        (filtrerat_df["Payout ratio 2 år (%)"] <= payout_min[1])
    ]

    st.subheader(f"Antal bolag som matchar filtren: {len(filtrerat_df)}")

    if len(filtrerat_df) > 0:
        filtrerat_df = filtrerat_df.sort_values(by="Uppside (%)", ascending=False)
        index = st.number_input("Visa förslag", min_value=1, max_value=len(filtrerat_df), value=1, step=1)
        valt_bolag = filtrerat_df.iloc[index - 1]

        st.markdown(f"### Förslag {index} av {len(filtrerat_df)}")
        for kolumn in filtrerat_df.columns:
            st.write(f"**{kolumn}:** {valt_bolag[kolumn]}")

        col1, col2 = st.columns(2)
        with col1:
            if index > 1:
                st.button("⬅️ Föregående", on_click=lambda: st.session_state.update(index=index-1), key="föregående")
        with col2:
            if index < len(filtrerat_df):
                st.button("➡️ Nästa", on_click=lambda: st.session_state.update(index=index+1), key="nästa")

    st.markdown("---")
    st.subheader("📋 Samtliga bolag i databasen")
    st.dataframe(df)

# --- Main ---
def main():
    st.title("📈 Utdelningsaktier – analys och hantering")

    df = hamta_data()
    df = säkerställ_kolumner(df)

    menyval = st.sidebar.radio("Meny", [
        "Lägg till eller uppdatera bolag",
        "Analys och investeringsförslag",
        "Uppdatera ett bolag från Yahoo Finance",
        "Massuppdatera alla bolag"
    ])

    if menyval == "Lägg till eller uppdatera bolag":
        lägg_till_eller_uppdatera(df)
    elif menyval == "Analys och investeringsförslag":
        analysvy(df)
    elif menyval == "Uppdatera ett bolag från Yahoo Finance":
        uppdatera_enskilt_bolag(df)
    elif menyval == "Massuppdatera alla bolag":
        massuppdatera_alla(df)


# --- Kör appen ---
if __name__ == "__main__":
    main()
