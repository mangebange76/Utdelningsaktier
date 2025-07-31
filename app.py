import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

# Google Sheets-koppling
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

# Funktioner
def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    data = skapa_koppling().get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

def uppdatera_data(df):
    for i, rad in df.iterrows():
        ticker = str(rad["Ticker"]).strip().upper()
        try:
            info = yf.Ticker(ticker).info
            kurs = info.get("regularMarketPrice", None)
            high = info.get("fiftyTwoWeekHigh", None)
            utdelning = info.get("dividendRate", None)
            valuta = info.get("currency", "USD")
            if kurs and high:
                df.at[i, "Kurs"] = round(kurs, 2)
                df.at[i, "52w High"] = round(high, 2)
                df.at[i, "Riktkurs"] = round(high * (1 - riktkurs_procent / 100), 2)
                df.at[i, "Uppside (%)"] = round((df.at[i, "Riktkurs"] - kurs) / kurs * 100, 2)
                df.at[i, "Direktavkastning (%)"] = round((utdelning / kurs) * 100, 2) if utdelning else 0
                df.at[i, "Datakälla utdelning"] = "Yahoo Finance" if utdelning else "Manuell"
        except Exception:
            continue
    return df

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

    # 🔽 Sortera på uppsida i fallande ordning
    visning = visning.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)

    if visning.empty:
        st.info("Inga bolag matchar filtren.")
        return

    if "index" not in st.session_state:
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
        if st.button("➡️ Nästa") and st.session_state.index < len(visning) - 1:
            st.session_state.index += 1

def redigera(df):
    st.subheader("✏️ Lägg till / ändra bolag")
    tickers = [""] + df["Ticker"].dropna().unique().tolist()
    vald = st.selectbox("Välj bolag att uppdatera (eller lämna tom för nytt)", tickers)

    if vald:
        rad = df[df["Ticker"] == vald].iloc[0]
    else:
        rad = pd.Series({k: "" for k in df.columns})

    with st.form("form"):
        kolumnvärden = {}
        for kolumn in df.columns:
            if kolumn == "Äger":
                kolumnvärden[kolumn] = st.selectbox("Äger du aktien?", ["Ja", "Nej"], index=0 if rad[kolumn] == "Ja" else 1)
            elif kolumn == "Valuta":
                kolumnvärden[kolumn] = st.selectbox("Valuta", ["USD", "NOK", "SEK", "EUR", "CAD"], index=0)
            else:
                kolumnvärden[kolumn] = st.text_input(kolumn, value=str(rad[kolumn]))

        sparaknapp = st.form_submit_button("💾 Spara")

    if sparaknapp and kolumnvärden["Ticker"]:
        ny = pd.DataFrame([kolumnvärden])
        df = df[df["Ticker"] != kolumnvärden["Ticker"]]
        df = pd.concat([df, ny], ignore_index=True)
        spara_data(df)
        st.success("Bolaget sparat.")
    return df

# Huvudfunktion
def main():
    global riktkurs_procent
    st.title("📈 Utdelningsaktier")

    riktkurs_procent = st.sidebar.selectbox("Riktkurs (% under 52w high)", list(range(1, 11)), index=4)

    df = hamta_data()

    meny = st.sidebar.radio("Välj vy", ["Bolagsvy", "Lägg till / ändra", "Uppdatera kurser"])
    if meny == "Bolagsvy":
        visa_bolag(df)
    elif meny == "Lägg till / ändra":
        df = redigera(df)
    elif meny == "Uppdatera kurser":
        st.info("Detta hämtar kurs, 52w high och utdelning från Yahoo Finance.")
        if st.button("🔄 Hämta kursdata"):
            df = uppdatera_data(df)
            spara_data(df)
            st.success("Uppdatering klar.")
        st.dataframe(df)

if __name__ == "__main__":
    main()
