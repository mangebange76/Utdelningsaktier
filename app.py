import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📊 Utdelningsaktier", layout="wide")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"

# 🧩 Google Sheets-koppling
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.astype(str).values.tolist())

# 📈 Yahoo-hämtning
def uppdatera_yahoo(ticker):
    try:
        info = yf.Ticker(ticker).info
        pris = info.get("regularMarketPrice", 0)
        utd = info.get("dividendRate", 0)
        high = info.get("fiftyTwoWeekHigh", 0)
        valuta = info.get("currency", "USD")
        return round(pris, 2), round(utd, 2), round(high, 2), valuta
    except:
        return 0, 0, 0, "USD"

# 🔢 Beräkningar
def berakna_kolumner(df):
    df["Direktavkastning (%)"] = (df["Utdelning"] / df["Kurs"] * 100).round(2)
    df["Uppside (%)"] = ((df["Riktkurs"] - df["Kurs"]) / df["Kurs"] * 100).round(2)
    df["Rekommendation"] = df["Uppside (%)"].apply(lambda x: (
        "Sälj" if x < -5 else
        "Pausa" if -5 <= x < 0 else
        "Behåll" if 0 <= x < 10 else
        "Öka" if 10 <= x < 30 else
        "Köp kraftigt"
    ))
    return df

# 🧮 Lägg till / uppdatera bolag
def lagg_till_eller_uppdatera(df):
    st.subheader("➕ Lägg till eller uppdatera bolag manuellt")
    tickers = df["Ticker"].tolist()
    valt = st.selectbox("Välj bolag att uppdatera", [""] + tickers)
    befintlig = df[df["Ticker"] == valt].iloc[0] if valt else {}

    with st.form("form_nytt_bolag"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", ""))
        namn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        kurs = st.number_input("Kurs", value=float(befintlig.get("Kurs", 0)))
        high = st.number_input("52w High", value=float(befintlig.get("52w High", 0)))
        riktkurs = st.number_input("Riktkurs", value=float(befintlig.get("Riktkurs", 0)))
        utdelning = st.number_input("Utdelning", value=float(befintlig.get("Utdelning", 0)))
        valuta = st.text_input("Valuta", value=befintlig.get("Valuta", "USD"))
        äger = st.selectbox("Äger du aktien?", ["Ja", "Nej"], index=0 if befintlig.get("Äger", "") == "Ja" else 1)
        källa = st.text_input("Datakälla utdelning", value=befintlig.get("Datakälla utdelning", ""))

        sparaknapp = st.form_submit_button("💾 Spara bolag")

    if sparaknapp and ticker:
        if ticker in df["Ticker"].values:
            ny = {
                "Ticker": ticker,
                "Bolagsnamn": namn,
                "Kurs": kurs,
                "52w High": high,
                "Riktkurs": riktkurs,
                "Utdelning": utdelning,
                "Valuta": valuta,
                "Äger": äger,
                "Datakälla utdelning": källa
            }
            df.loc[df["Ticker"] == ticker, ny.keys()] = ny.values()
            st.success("Bolaget uppdaterat!")
        else:
            pris, utd, h52, val = uppdatera_yahoo(ticker)
            if pris == 0:
                st.error("❌ Kunde inte hämta data från Yahoo Finance.")
                return df

            ny = {
                "Ticker": ticker,
                "Bolagsnamn": namn,
                "Kurs": pris,
                "52w High": h52,
                "Riktkurs": h52 * 0.95,
                "Utdelning": utd,
                "Valuta": val,
                "Äger": äger,
                "Datakälla utdelning": "Yahoo Finance"
            }
            df = pd.concat([df, pd.DataFrame([ny])], ignore_index=True)
            st.success("Bolaget tillagt med data från Yahoo Finance!")

        df = berakna_kolumner(df)
        spara_data(df)

    return df

# 🔁 Uppdatering av kurser
def uppdatera_data(df):
    st.subheader("🔄 Uppdatera kurser från Yahoo Finance")
    ticker_val = st.selectbox("Välj bolag att uppdatera", ["Alla"] + df["Ticker"].tolist())
    if st.button("🔁 Starta uppdatering"):
        if ticker_val == "Alla":
            misslyckade = []
            status = st.empty()
            bar = st.progress(0)
            for i, row in df.iterrows():
                status.text(f"🔄 Uppdaterar {i + 1} av {len(df)} – {row['Ticker']}")
                pris, utd, h52, val = uppdatera_yahoo(row["Ticker"])
                if pris == 0:
                    misslyckade.append(row["Ticker"])
                    continue
                df.at[i, "Kurs"] = pris
                df.at[i, "Utdelning"] = utd
                df.at[i, "52w High"] = h52
                df.at[i, "Valuta"] = val
                time.sleep(1)
                bar.progress((i + 1) / len(df))
            status.text("✅ Alla bolag är uppdaterade!")
            spara_data(berakna_kolumner(df))
            st.success("✅ Uppdatering klar!")
            if misslyckade:
                st.warning("Kunde inte uppdatera: " + ", ".join(misslyckade))
        else:
            i = df[df["Ticker"] == ticker_val].index[0]
            pris, utd, h52, val = uppdatera_yahoo(ticker_val)
            if pris == 0:
                st.error("❌ Kunde inte uppdatera från Yahoo.")
            else:
                df.at[i, "Kurs"] = pris
                df.at[i, "Utdelning"] = utd
                df.at[i, "52w High"] = h52
                df.at[i, "Valuta"] = val
                df = berakna_kolumner(df)
                spara_data(df)
                st.success(f"✅ {ticker_val} uppdaterad!")
    return df

# 🎯 Analys och investeringsförslag
def analysvy(df):
    st.subheader("📈 Analys & investeringsförslag")
    df = berakna_kolumner(df)

    # Filter
    rekommendationer = sorted(df["Rekommendation"].dropna().unique())
    val = st.multiselect("Filtrera på rekommendation", rekommendationer, default=rekommendationer)
    yieldval = st.selectbox("Minsta direktavkastning (%)", [0, 3, 5, 7, 10], index=0)
    endast_ägda = st.checkbox("Visa endast ägda bolag")

    filtrerat = df[
        (df["Rekommendation"].isin(val)) &
        (df["Direktavkastning (%)"] >= yieldval)
    ]
    if endast_ägda:
        filtrerat = filtrerat[filtrerat["Äger"] == "Ja"]

    filtrerat = filtrerat.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    if filtrerat.empty:
        st.info("Inga bolag matchar filtren.")
        return

    st.markdown(f"**Antal bolag som matchar:** {len(filtrerat)}")

    if "index" not in st.session_state:
        st.session_state.index = 0

    index = st.session_state.index
    if index >= len(filtrerat):
        index = 0

    rad = filtrerat.iloc[index]
    st.markdown(f"### 📌 Förslag {index + 1} av {len(filtrerat)}")
    st.write(f"**{rad['Bolagsnamn']} ({rad['Ticker']})**")
    st.write(f"📈 Kurs: {rad['Kurs']} {rad['Valuta']} | 🎯 Riktkurs: {rad['Riktkurs']}")
    st.write(f"📊 Utdelning: {rad['Utdelning']} | 💸 Direktavkastning: {rad['Direktavkastning (%)']}%")
    st.write(f"🧭 Uppside: {rad['Uppside (%)']}% | 📢 Rekommendation: **{rad['Rekommendation']}**")

    col1, col2 = st.columns(2)
    if col1.button("⬅️ Föregående"):
        st.session_state.index = max(0, index - 1)
    if col2.button("➡️ Nästa"):
        st.session_state.index = min(len(filtrerat) - 1, index + 1)

# 🚀 Main
def main():
    st.title("📊 Utdelningsaktier")
    df = hamta_data()
    df = lagg_till_eller_uppdatera(df)
    df = uppdatera_data(df)
    analysvy(df)

if __name__ == "__main__":
    main()
