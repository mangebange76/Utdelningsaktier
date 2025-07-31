import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials

# --- Google Sheets Setup ---
scope = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["GOOGLE_CREDENTIALS"], scopes=scope
)
client = gspread.authorize(credentials)
sheet = client.open_by_url(st.secrets["SHEET_URL"]).worksheet("Bolag")

# --- Ladda in data från arket ---
def load_data():
    try:
        df = pd.DataFrame(sheet.get_all_records())
        return df
    except Exception:
        return pd.DataFrame(columns=[
            "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger",
            "Kurs", "52w High", "Direktavkastning (%)",
            "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
        ])

df = load_data()

st.title("📈 Utdelningsaktier – analys och filtrering")

# --- Val för riktkursavdrag ---
procent_val = st.selectbox("Dra av % från 52w High för att beräkna riktkurs", [i for i in range(1, 11)], index=4)
avdrag_procent = procent_val / 100

st.subheader("➕ Lägg till eller uppdatera bolag")

with st.form("bolagsformulär"):
    ticker = st.text_input("Ticker (t.ex. AAPL)").upper()
    bolagsnamn = st.text_input("Bolagsnamn (kan hämtas automatiskt)")
    valuta = st.selectbox("Valuta", ["USD", "SEK", "EUR", "NOK", "CAD"])
    äger = st.selectbox("Äger aktien?", ["Ja", "Nej"])

    kurs = None
    high_52w = None
    utdelning = None
    utdelningskälla = "Manuell"

    if ticker:
        try:
            info = yf.Ticker(ticker).info
            kurs = info.get("currentPrice")
            high_52w = info.get("fiftyTwoWeekHigh")
            auto_utdelning = info.get("dividendRate")

            if auto_utdelning is not None:
                utdelning = auto_utdelning
                utdelningskälla = "Yahoo"

            if not bolagsnamn and "longName" in info:
                bolagsnamn = info["longName"]

        except Exception as e:
            st.warning(f"Fel vid hämtning från Yahoo Finance: {e}")

    utdelning = st.number_input(
        "Årsutdelning (" + valuta + ")", min_value=0.0, step=0.01,
        value=utdelning if utdelning is not None else 0.0
    )

    st.markdown("📌 **Automatiskt hämtat:**")
    st.write(f"Aktuell kurs: {kurs}" if kurs else "Ingen kurs hämtad")
    st.write(f"52-week high: {high_52w}" if high_52w else "Ingen 52w high hämtad")

    submitted = st.form_submit_button("Spara bolag")

def beräkna_rekommendation(kurs, riktkurs):
    if kurs is None or riktkurs is None:
        return "?"
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

if submitted and ticker and kurs and high_52w:
    try:
        da = round((utdelning / kurs) * 100, 2) if utdelning else 0.0
        riktkurs = round(high_52w * (1 - avdrag_procent), 2)
        uppsida = round((riktkurs - kurs) / kurs * 100, 2)
        rekommendation = beräkna_rekommendation(kurs, riktkurs)

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
            "Rekommendation": rekommendation,
            "Datakälla utdelning": utdelningskälla
        }

        # Kolla om bolaget redan finns, uppdatera annars lägg till
        df = df[df["Ticker"] != ticker]
        df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)

        # Skriv tillbaka till Google Sheets
        sheet.clear()
        sheet.append_row(list(ny_rad.keys()))  # kolumnrubriker
        for row in df.to_dict(orient="records"):
            sheet.append_row(list(row.values()))

        st.success(f"{ticker} sparades till databasen.")
    except Exception as e:
        st.error(f"Något gick fel vid sparandet: {e}")

st.subheader("📋 Databas – filtrering & bläddring")

if not df.empty:
    # --- Filtrering ---
    st.markdown("### 🔎 Filtrera:")
    kol1, kol2, kol3 = st.columns(3)

    with kol1:
        valda_rek = st.multiselect(
            "Rekommendation",
            options=df["Rekommendation"].unique().tolist(),
            default=df["Rekommendation"].unique().tolist()
        )

    with kol2:
        min_da = st.selectbox("Direktavkastning minst (%)", [0, 2, 3, 4, 5], index=0)

    with kol3:
        endast_ägda = st.checkbox("Visa endast aktier jag äger")

    # --- Tillämpa filter ---
    filtrerad = df.copy()
    if valda_rek:
        filtrerad = filtrerad[filtrerad["Rekommendation"].isin(valda_rek)]
    if min_da:
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= min_da]
    if endast_ägda:
        filtrerad = filtrerad[filtrerad["Äger"] == "Ja"]

    # --- Färgkodning ---
    def färgkod(row):
        färg = ""
        match row["Rekommendation"]:
            case "Köp kraftigt": färg = "background-color: lightgreen"
            case "Öka": färg = "background-color: palegreen"
            case "Behåll": färg = "background-color: lightyellow"
            case "Pausa": färg = "background-color: lightsalmon"
            case "Sälj": färg = "background-color: lightcoral"
        return [färg] * len(row)

    # --- Bläddringsbar vy ---
    sidstorlek = 5
    total = len(filtrerad)
    sidtotal = max((total - 1) // sidstorlek + 1, 1)
    sida = st.number_input("Sidnummer", min_value=1, max_value=sidtotal, value=1, step=1)
    start, end = (sida - 1) * sidstorlek, sida * sidstorlek

    df_sida = filtrerad.iloc[start:end]
    st.dataframe(df_sida.style.apply(färgkod, axis=1), use_container_width=True)
else:
    st.info("Ingen data att visa ännu. Lägg till ett bolag först.")
