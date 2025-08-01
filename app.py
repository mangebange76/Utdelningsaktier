import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import time

st.set_page_config(page_title="📊 Utdelningsaktier", layout="wide")

# 🛠️ Autentisering och Google Sheets-koppling
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

# 🧠 Funktioner
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    try:
        sheet = skapa_koppling()
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except:
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
            df[kol] = ""
    return df

def hamta_info_yahoo(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        kurs = info.get("regularMarketPrice")
        high_52w = info.get("fiftyTwoWeekHigh")
        utd = info.get("dividendRate")
        valuta = info.get("currency")
        namn = info.get("longName") or info.get("shortName")
        return kurs, high_52w, utd, valuta, namn
    except:
        return None, None, None, None, None

def beräkna_och_uppdatera(df):
    for i, rad in df.iterrows():
        try:
            kurs = float(rad["Kurs"])
            high = float(rad["52w High"])
            utd = float(rad["Utdelning"])
            riktkurs = float(rad["Riktkurs"])
        except:
            continue

        if kurs > 0:
            df.at[i, "Direktavkastning (%)"] = round((utd / kurs) * 100, 2) if utd else ""
            df.at[i, "Uppside (%)"] = round(((riktkurs - kurs) / kurs) * 100, 2) if riktkurs else ""

            uppsida = df.at[i, "Uppside (%)"]
            if uppsida == "":
                df.at[i, "Rekommendation"] = ""
            elif float(uppsida) >= 50:
                df.at[i, "Rekommendation"] = "Köp mycket"
            elif 10 <= float(uppsida) < 50:
                df.at[i, "Rekommendation"] = "Öka"
            elif 3 <= float(uppsida) < 10:
                df.at[i, "Rekommendation"] = "Behåll"
            elif -10 <= float(uppsida) < 3:
                df.at[i, "Rekommendation"] = "Pausa"
            else:
                df.at[i, "Rekommendation"] = "Sälj"
    return df

# 🎯 Huvudvyer
def analysvy(df):
    st.header("📈 Analys och investeringsförslag")

    # Filtrering
    rekommendationer = sorted(df["Rekommendation"].dropna().unique())
    val_rek = st.selectbox("Filtrera på rekommendation", ["Alla"] + rekommendationer)
    direktval = st.selectbox("Direktavkastning över (%)", ["Alla", "3", "5", "7", "10"])
    visa_ager = st.checkbox("Visa endast bolag jag äger")

    filtrerat = df.copy()
    if val_rek != "Alla":
        filtrerat = filtrerat[filtrerat["Rekommendation"] == val_rek]
    if direktval != "Alla":
        filtrerat = filtrerat[pd.to_numeric(filtrerat["Direktavkastning (%)"], errors="coerce") > int(direktval)]
    if visa_ager:
        filtrerat = filtrerat[filtrerat["Äger"].str.lower() == "ja"]

    filtrerat = filtrerat.sort_values(by="Uppside (%)", ascending=False, na_position="last").reset_index(drop=True)

    st.markdown(f"### Visar {len(filtrerat)} bolag")

    # Bläddra ett i taget
    if "bläddra_index" not in st.session_state:
        st.session_state.bläddra_index = 0

    if len(filtrerat) > 0:
        idx = st.session_state.bläddra_index
        if idx >= len(filtrerat):
            idx = 0
        rad = filtrerat.iloc[idx]

        st.markdown(f"#### Förslag {idx+1} av {len(filtrerat)}")
        st.write(f"**{rad['Bolagsnamn']} ({rad['Ticker']})**")
        st.write(f"- Kurs: {rad['Kurs']} {rad['Valuta']}")
        st.write(f"- Riktkurs: {rad['Riktkurs']} {rad['Valuta']}")
        st.write(f"- Utdelning: {rad['Utdelning']}")
        st.write(f"- Direktavkastning: {rad['Direktavkastning (%)']}%")
        st.write(f"- Uppside: {rad['Uppside (%)']}%")
        st.write(f"- Rekommendation: {rad['Rekommendation']}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ Föregående"):
                st.session_state.bläddra_index = max(0, idx - 1)
        with col2:
            if st.button("➡️ Nästa"):
                st.session_state.bläddra_index = min(len(filtrerat) - 1, idx + 1)
    else:
        st.info("Inga bolag matchar filtren.")

    # Hela tabellen
    st.markdown("---")
    st.subheader("📋 Samtliga bolag")
    st.dataframe(df, use_container_width=True)

def lagg_till_eller_uppdatera(df):
    st.header("➕ Lägg till / uppdatera bolag")
    namn_map = {f"{rad['Bolagsnamn']} ({rad['Ticker']})": rad['Ticker'] for _, rad in df.iterrows()}
    valt = st.selectbox("Välj bolag att uppdatera (eller lämna tom för nytt)", [""] + sorted(namn_map.keys()))

    if valt:
        ticker_vald = namn_map[valt]
        befintlig = df[df["Ticker"] == ticker_vald].iloc[0]
    else:
        befintlig = pd.Series(dtype=object)

    with st.form("form"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "")).upper()
        bolagsnamn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        utdelning = st.number_input("Utdelning", value=float(befintlig.get("Utdelning", 0.0)))
        valuta = st.selectbox("Valuta", ["USD", "SEK", "EUR", "NOK", "CAD"], index=0)
        ager = st.selectbox("Äger", ["Ja", "Nej"], index=0)
        kurs = st.number_input("Aktuell kurs", value=float(befintlig.get("Kurs", 0.0)))
        high = st.number_input("52w High", value=float(befintlig.get("52w High", 0.0)))
        riktkurs = st.number_input("Riktkurs", value=float(befintlig.get("Riktkurs", 0.0)))
        knapp = st.form_submit_button("💾 Spara")

    if knapp and ticker:
        yahoo_kurs, yahoo_high, yahoo_utd, yahoo_valuta, yahoo_namn = hamta_info_yahoo(ticker)

        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": yahoo_namn or bolagsnamn,
            "Utdelning": yahoo_utd if yahoo_utd is not None else utdelning,
            "Valuta": yahoo_valuta or valuta,
            "Äger": ager,
            "Kurs": yahoo_kurs if yahoo_kurs is not None else kurs,
            "52w High": yahoo_high if yahoo_high is not None else high,
            "Riktkurs": riktkurs,
            "Datakälla utdelning": "Yahoo Finance" if yahoo_utd is not None else "Manuell inmatning"
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
            st.success("Bolaget uppdaterat.")
        else:
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            st.success("Bolag tillagt.")

        spara_data(df)
    return df

def uppdatera_alla(df):
    st.header("🔁 Uppdatera alla bolag från Yahoo Finance")
    if st.button("Uppdatera nu"):
        misslyckade = []
        totalt = len(df)
        status = st.empty()
        bar = st.progress(0)

        for i, rad in df.iterrows():
            ticker = rad["Ticker"]
            status.text(f"🔄 Uppdaterar {i + 1} av {totalt} ({ticker})...")
            kurs, high, utd, valuta, namn = hamta_info_yahoo(ticker)

            if kurs is None:
                misslyckade.append(ticker)
                continue

            df.at[i, "Kurs"] = kurs
            df.at[i, "52w High"] = high
            df.at[i, "Utdelning"] = utd
            df.at[i, "Valuta"] = valuta
            df.at[i, "Bolagsnamn"] = namn
            df.at[i, "Datakälla utdelning"] = "Yahoo Finance"

            bar.progress((i + 1) / totalt)
            time.sleep(1)

        df = beräkna_och_uppdatera(df)
        spara_data(df)
        status.text("✅ Uppdatering klar.")
        if misslyckade:
            st.warning("Kunde inte uppdatera följande tickers:\n" + ", ".join(misslyckade))
        else:
            st.success("Alla bolag uppdaterades.")

# 🧭 Navigering
def main():
    df = hamta_data()
    df = säkerställ_kolumner(df)
    df = beräkna_och_uppdatera(df)

    meny = st.sidebar.radio("Välj vy", ["Analys", "Lägg till / uppdatera bolag", "Uppdatera alla från Yahoo"])
    if meny == "Analys":
        analysvy(df)
    elif meny == "Lägg till / uppdatera bolag":
        df = lagg_till_eller_uppdatera(df)
    elif meny == "Uppdatera alla från Yahoo":
        uppdatera_alla(df)

if __name__ == "__main__":
    main()
