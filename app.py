import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📈 Utdelningsaktier", layout="wide")

# 🟦 Inställningar för Google Sheets
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

# 🟦 Koppling till arket
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

# 🟦 Hämtar aktuell kurs och utdelning från Yahoo
def hamta_yahoo_data(ticker):
    try:
        aktie = yf.Ticker(ticker)
        info = aktie.info
        kurs = info.get("regularMarketPrice", 0.0)
        utd = info.get("dividendRate", 0.0)
        return kurs, utd, "Yahoo Finance"
    except:
        return 0.0, 0.0, "Manuell"

# 🟦 Uppdatera data från Yahoo för alla bolag
def uppdatera_data(df):
    st.subheader("🔄 Massuppdatering från Yahoo Finance")
    if st.button("Uppdatera alla bolag"):
        with st.spinner("Hämtar data..."):
            for i, row in df.iterrows():
                ticker = row["Ticker"]
                kurs, utd, källa = hamta_yahoo_data(ticker)
                df.at[i, "Kurs"] = kurs
                df.at[i, "Utdelning"] = utd
                df.at[i, "Datakälla utdelning"] = källa

                # Direktavkastning
                if kurs > 0:
                    df.at[i, "Direktavkastning (%)"] = round((utd / kurs) * 100, 2)
                else:
                    df.at[i, "Direktavkastning (%)"] = 0.0

                # Uppside
                try:
                    riktkurs = float(row["Riktkurs"])
                    df.at[i, "Uppside (%)"] = round(((riktkurs - kurs) / kurs) * 100, 2)
                except:
                    df.at[i, "Uppside (%)"] = 0.0
        spara_data(df)
        st.success("✅ Uppdatering klar!")

# 🟦 Lägg till / uppdatera bolag
def lagg_till_bolag(df):
    st.subheader("➕ Lägg till / uppdatera bolag")

    tickers = df["Ticker"].tolist()
    valt_ticker = st.selectbox("Välj bolag att uppdatera (eller lämna tom för nytt)", [""] + tickers)

    if valt_ticker and valt_ticker in df["Ticker"].values:
        befintlig = df[df["Ticker"] == valt_ticker].iloc[0]
    else:
        befintlig = {}

    with st.form("form"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "")).upper()
        namn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", ""))
        utdelning = st.number_input("Utdelning", value=float(befintlig.get("Utdelning", 0.0)))
        valuta = st.selectbox("Valuta", ["USD", "NOK", "CAD", "SEK", "EUR"], index=0)
        äger = st.selectbox("Äger du aktien?", ["Nej", "Ja"], index=1 if befintlig.get("Äger") == "Ja" else 0)
        kurs = st.number_input("Kurs", value=float(befintlig.get("Kurs", 0.0)))
        high = st.number_input("52w High", value=float(befintlig.get("52w High", 0.0)))
        riktkurs = st.number_input("Riktkurs", value=float(befintlig.get("Riktkurs", 0.0)))
        källa = st.selectbox("Datakälla utdelning", ["Yahoo Finance", "Manuell"], index=0 if befintlig.get("Datakälla utdelning") == "Yahoo Finance" else 1)

        spara = st.form_submit_button("💾 Spara")

    if spara and ticker:
        ny = {
            "Ticker": ticker,
            "Bolagsnamn": namn,
            "Utdelning": utdelning,
            "Valuta": valuta,
            "Äger": äger,
            "Kurs": kurs,
            "52w High": high,
            "Direktavkastning (%)": round((utdelning / kurs) * 100, 2) if kurs > 0 else 0.0,
            "Riktkurs": riktkurs,
            "Uppside (%)": round(((riktkurs - kurs) / kurs) * 100, 2) if kurs > 0 else 0.0,
            "Rekommendation": "",
            "Datakälla utdelning": källa
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker] = ny
            st.success(f"{ticker} uppdaterad.")
        else:
            df = pd.concat([df, pd.DataFrame([ny])], ignore_index=True)
            st.success(f"{ticker} tillagd.")
        spara_data(df)
    return df

# 🟦 Bläddringsvy
def visa_bolag(df):
    st.subheader("📋 Bolagsöversikt")
    filter_rek = st.multiselect("Filtrera på rekommendation", sorted(df["Rekommendation"].dropna().unique()))
    filter_äger = st.checkbox("Visa endast bolag jag äger")
    min_da = st.slider("Minsta direktavkastning (%)", 0.0, 15.0, 0.0)

    visning = df.copy()
    if filter_rek:
        visning = visning[visning["Rekommendation"].isin(filter_rek)]
    if filter_äger:
        visning = visning[visning["Äger"] == "Ja"]
    visning = visning[pd.to_numeric(visning["Direktavkastning (%)"], errors="coerce").fillna(0) >= min_da]

    visning = visning.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)

    totalt = len(df)
    filtrerat = len(visning)
    st.markdown(f"**Visar {filtrerat} av {totalt} bolag**")

    if visning.empty:
        st.info("Inga bolag matchar filtren.")
        return

    if "index" not in st.session_state:
        st.session_state.index = 0
    elif st.session_state.index >= filtrerat:
        st.session_state.index = 0

    rad = visning.iloc[st.session_state.index]
    st.markdown(f"""
    ### {rad['Bolagsnamn']} ({rad['Ticker']})
    - **Kurs:** {rad['Kurs']} {rad['Valuta']}
    - **Utdelning:** {rad['Utdelning']} ({rad['Direktavkastning (%)']}%)
    - **52w High:** {rad['52w High']}
    - **Riktkurs:** {rad['Riktkurs']}
    - **Uppside:** {rad['Uppside (%)']}%
    - **Rekommendation:** {rad['Rekommendation']}
    - **Äger:** {rad['Äger']}
    - **Datakälla utdelning:** {rad['Datakälla utdelning']}
    """)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Föregående") and st.session_state.index > 0:
            st.session_state.index -= 1
    with col2:
        if st.button("➡️ Nästa") and st.session_state.index < filtrerat - 1:
            st.session_state.index += 1

# 🟦 Huvudfunktion
def main():
    st.title("📈 Utdelningsaktier – analys och bläddring")
    df = hamta_data()

    meny = st.sidebar.radio("Navigering", ["Bläddra", "Lägg till / uppdatera", "Uppdatera från Yahoo"])

    if meny == "Bläddra":
        visa_bolag(df)
    elif meny == "Lägg till / uppdatera":
        df = lagg_till_bolag(df)
    elif meny == "Uppdatera från Yahoo":
        uppdatera_data(df)

if __name__ == "__main__":
    main()
