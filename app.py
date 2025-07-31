import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📈 Utdelningsaktier", layout="wide")

# --- Autentisering ---
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

# --- Koppling till Google Sheets ---
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

# --- Rekommendationslogik ---
def beräkna_rekommendation(kurs, riktkurs):
    try:
        skillnad = (riktkurs - kurs) / kurs * 100
        if skillnad >= 20:
            return "Köp kraftigt"
        elif skillnad >= 10:
            return "Öka"
        elif -5 <= skillnad < 10:
            return "Behåll"
        elif -15 <= skillnad < -5:
            return "Pausa"
        else:
            return "Sälj"
    except:
        return "?"

# --- Huvudvy ---
st.title("📈 Utdelningsaktier")

# --- Riktkurs-avdrag i % ---
procent_val = st.selectbox("Dra av % från 52w High för riktkurs", list(range(1, 11)), index=4)
avdrag_procent = procent_val / 100

# --- Ladda data ---
df = hamta_data() if SHEET_NAME else pd.DataFrame()
alla_kolumner = [
    "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger",
    "Kurs", "52w High", "Direktavkastning (%)",
    "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
]
for kol in alla_kolumner:
    if kol not in df.columns:
        df[kol] = ""

# --- Formulär ---
st.subheader("➕ Lägg till eller uppdatera bolag")

with st.form("form"):
    ticker = st.text_input("Ticker (t.ex. AAPL)").upper()
    bolagsnamn = st.text_input("Bolagsnamn (hämtas om tomt)")
    valuta = st.selectbox("Valuta", ["USD", "SEK", "EUR", "NOK", "CAD"])
    äger = st.selectbox("Äger aktien?", ["Ja", "Nej"])
    kurs, high_52w, auto_utdelning = None, None, None
    källa = "Manuell"

    if ticker:
        try:
            info = yf.Ticker(ticker).info
            kurs = info.get("currentPrice")
            high_52w = info.get("fiftyTwoWeekHigh")
            auto_utdelning = info.get("dividendRate")
            if not bolagsnamn:
                bolagsnamn = info.get("longName", "")
            if auto_utdelning is not None:
                källa = "Yahoo"
        except Exception as e:
            st.warning(f"Kunde inte hämta från Yahoo: {e}")

    utdelning = st.number_input("Årsutdelning", value=auto_utdelning or 0.0, min_value=0.0, step=0.01)
    st.write(f"Kurs: {kurs}" if kurs else "❌ Ingen kurs")
    st.write(f"52w High: {high_52w}" if high_52w else "❌ Ingen 52w high")

    spara = st.form_submit_button("💾 Spara bolag")

if spara and ticker and kurs and high_52w:
    riktkurs = round(high_52w * (1 - avdrag_procent), 2)
    da = round((utdelning / kurs) * 100, 2) if utdelning else 0.0
    uppsida = round((riktkurs - kurs) / kurs * 100, 2)
    rek = beräkna_rekommendation(kurs, riktkurs)

    ny_rad = {
        "Ticker": ticker,
        "Bolagsnamn": bolagsnamn,
        "Utdelning": utdelning,
        "Valuta": valuta,
        "Äger": äger,
        "Kurs": kurs,
        "52w High": high_52w,
        "Direktavkastning (%)": da,
        "Riktkurs": riktkurs,
        "Uppside (%)": uppsida,
        "Rekommendation": rek,
        "Datakälla utdelning": källa
    }

    df = df[df["Ticker"] != ticker]
    df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
    spara_data(df)
    st.success(f"{ticker} sparades!")

# --- Filtrering & presentation ---
st.subheader("📋 Databas")

if df.empty:
    st.info("Inga bolag i databasen.")
else:
    col1, col2, col3 = st.columns(3)
    med_rek = df["Rekommendation"].unique().tolist()

    with col1:
        valda_rek = st.multiselect("Rekommendation", med_rek, default=med_rek)
    with col2:
        min_da = st.selectbox("Min DA (%)", [0, 2, 3, 4, 5])
    with col3:
        endast_ägda = st.checkbox("Visa endast bolag jag äger")

    filtrerad = df.copy()
    if valda_rek:
        filtrerad = filtrerad[filtrerad["Rekommendation"].isin(valda_rek)]
    if min_da:
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"].astype(float) >= min_da]
    if endast_ägda:
        filtrerad = filtrerad[filtrerad["Äger"] == "Ja"]

    sidstorlek = 5
    total = len(filtrerad)
    sidtotal = max((total - 1) // sidstorlek + 1, 1)
    sida = st.number_input("Sidnummer", min_value=1, max_value=sidtotal, value=1, step=1)
    start, end = (sida - 1) * sidstorlek, sida * sidstorlek
    df_sida = filtrerad.iloc[start:end].copy()

    def färgkodning(row):
        färg = ""
        match row["Rekommendation"]:
            case "Köp kraftigt": färg = "background-color: lightgreen"
            case "Öka": färg = "background-color: palegreen"
            case "Behåll": färg = "background-color: lightyellow"
            case "Pausa": färg = "background-color: lightsalmon"
            case "Sälj": färg = "background-color: lightcoral"
        return [färg] * len(row)

    st.dataframe(df_sida.style.apply(färgkodning, axis=1), use_container_width=True)
