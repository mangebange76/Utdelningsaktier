import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

# 🧾 Autentisering
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

# 📊 Hämta data
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.astype(str).values.tolist())

# 🔄 Hämta kurs & utdelning från Yahoo Finance
def uppdatera_yahoo(ticker):
    try:
        aktie = yf.Ticker(ticker)
        pris = aktie.info.get("regularMarketPrice", 0)
        utdelning = aktie.info.get("dividendRate", 0) or 0
        high_52w = aktie.info.get("fiftyTwoWeekHigh", 0)
        valuta = aktie.info.get("currency", "USD")
        return pris, utdelning, high_52w, valuta
    except:
        return 0, 0, 0, "USD"

# 🔢 Beräkna kolumner
def berakna_kolumner(df):
    df["Direktavkastning (%)"] = df.apply(lambda x: round((float(x["Utdelning"]) / float(x["Kurs"]) * 100) if float(x["Kurs"]) > 0 else 0, 2), axis=1)
    df["Uppside (%)"] = df.apply(lambda x: round(((float(x["Riktkurs"]) - float(x["Kurs"])) / float(x["Kurs"]) * 100) if float(x["Kurs"]) > 0 else 0, 2), axis=1)

    def rek(row):
        if row["Uppside (%)"] >= 50:
            return "Köp kraftigt"
        elif row["Uppside (%)"] >= 10:
            return "Öka"
        elif row["Uppside (%)"] >= 3:
            return "Behåll"
        elif row["Uppside (%)"] >= -5:
            return "Pausa"
        else:
            return "Sälj"

    df["Rekommendation"] = df.apply(rek, axis=1)
    return df

# 🧾 Säkerställ alla kolumner finns
def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
        "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
    ]
    for k in kolumner:
        if k not in df.columns:
            df[k] = ""
    return df

# ➕ Lägg till / uppdatera bolag manuellt
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
        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny.keys()] = ny.values()
            st.success("Bolaget uppdaterat!")
        else:
            df = pd.concat([df, pd.DataFrame([ny])], ignore_index=True)
            st.success("Bolaget tillagt!")
        spara_data(df)
    return df

# 🔍 Analys & investeringsförslag
def analys_och_forslag(df):
    st.subheader("📈 Analys & investeringsförslag")

    # 🎛 Filtrering
    rekommendationer = sorted(df["Rekommendation"].dropna().unique())
    val_rek = st.multiselect("Filtrera på rekommendation", rekommendationer, default=rekommendationer)
    val_da = st.multiselect("Direktavkastning över", ["3%", "5%", "7%", "10%"])
    visa_ager = st.checkbox("Visa endast bolag jag äger")

    filtrerad = df[df["Rekommendation"].isin(val_rek)]

    if "3%" in val_da:
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= 3]
    if "5%" in val_da:
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= 5]
    if "7%" in val_da:
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= 7]
    if "10%" in val_da:
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] >= 10]
    if visa_ager:
        filtrerad = filtrerad[filtrerad["Äger"] == "Ja"]

    filtrerad = filtrerad.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    if len(filtrerad) == 0:
        st.info("Inga bolag matchar filtren.")
        return

    if "forslag_index" not in st.session_state:
        st.session_state.forslag_index = 0

    index = st.session_state.forslag_index
    if index >= len(filtrerad):
        index = 0

    rad = filtrerad.iloc[index]

    st.markdown(f"### 💡 Förslag {index+1} av {len(filtrerad)}")
    st.markdown(f"""
        - **Bolag:** {rad['Bolagsnamn']} ({rad['Ticker']})
        - **Kurs:** {rad['Kurs']} {rad['Valuta']}
        - **Riktkurs:** {rad['Riktkurs']} {rad['Valuta']}
        - **Uppside:** {rad['Uppside (%)']}%
        - **Direktavkastning:** {rad['Direktavkastning (%)']}%
        - **Rekommendation:** {rad['Rekommendation']}
    """)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Föregående"):
            st.session_state.forslag_index = max(0, st.session_state.forslag_index - 1)
    with col2:
        if st.button("➡️ Nästa"):
            st.session_state.forslag_index = min(len(filtrerad) - 1, st.session_state.forslag_index + 1)

# 🔄 Uppdatera från Yahoo
def yahoo_uppdatering(df):
    st.subheader("🔄 Uppdatera data från Yahoo Finance")

    tickers = df["Ticker"].dropna().unique().tolist()
    valt = st.selectbox("Välj bolag att uppdatera", ["Alla bolag"] + tickers)

    if st.button("🔁 Starta uppdatering"):
        if valt == "Alla bolag":
            misslyckade = []
            status = st.empty()
            bar = st.progress(0)

            for i, ticker in enumerate(tickers):
                status.text(f"Uppdaterar {i+1} av {len(tickers)} – {ticker}")
                pris, utd, high, valuta = uppdatera_yahoo(ticker)
                if pris == 0:
                    misslyckade.append(ticker)
                    continue
                df.loc[df["Ticker"] == ticker, ["Kurs", "Utdelning", "52w High", "Valuta"]] = [pris, utd, high, valuta]
                df.loc[df["Ticker"] == ticker, "Datakälla utdelning"] = "Yahoo Finance"
                bar.progress((i+1)/len(tickers))
                time.sleep(1)

            df = berakna_kolumner(df)
            spara_data(df)
            st.success("✅ Alla bolag är uppdaterade!")
            if misslyckade:
                st.warning("Kunde inte uppdatera följande tickers:\n" + ", ".join(misslyckade))
        else:
            pris, utd, high, valuta = uppdatera_yahoo(valt)
            if pris == 0:
                st.error("❌ Kunde inte hämta data.")
            else:
                df.loc[df["Ticker"] == valt, ["Kurs", "Utdelning", "52w High", "Valuta"]] = [pris, utd, high, valuta]
                df.loc[df["Ticker"] == valt, "Datakälla utdelning"] = "Yahoo Finance"
                df = berakna_kolumner(df)
                spara_data(df)
                st.success(f"✅ {valt} uppdaterad!")

# 🚀 Start
def main():
    st.title("📊 Aktieanalys och investeringsförslag")

    df = hamta_data()
    df = säkerställ_kolumner(df)
    df = berakna_kolumner(df)

    meny = st.radio("📌 Välj vy", ["Analys & investeringsförslag", "Lägg till / uppdatera bolag", "Uppdatera från Yahoo"])

    if meny == "Analys & investeringsförslag":
        analys_och_forslag(df)
    elif meny == "Lägg till / uppdatera bolag":
        df = lagg_till_eller_uppdatera(df)
    elif meny == "Uppdatera från Yahoo":
        yahoo_uppdatering(df)

if __name__ == "__main__":
    main()
