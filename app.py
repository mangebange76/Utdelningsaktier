import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)

def skapa_koppling():
    return client.open_by_url(SHEET_URL).worksheet(SHEET_NAME)

def hamta_data():
    sheet = skapa_koppling()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

def lagg_till_eller_uppdatera(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    tickers = df["Ticker"].tolist()
    valt = st.selectbox("Välj bolag att uppdatera", [""] + tickers)

    if valt:
        rad = df[df["Ticker"] == valt].iloc[0]
    else:
        rad = {}

    with st.form("form"):
        ticker = st.text_input("Ticker", value=rad.get("Ticker", "")).upper()
        namn = st.text_input("Bolagsnamn", value=rad.get("Bolagsnamn", ""))
        utdelning = st.number_input("Utdelning", value=float(rad.get("Utdelning", 0)))
        valuta = st.selectbox("Valuta", ["USD", "SEK", "NOK", "EUR", "CAD"], index=0 if not rad else ["USD", "SEK", "NOK", "EUR", "CAD"].index(rad.get("Valuta", "USD")))
        ager = st.checkbox("Äger", value=rad.get("Äger", "") == "Ja")
        kurs = st.number_input("Kurs", value=float(rad.get("Kurs", 0)))
        high = st.number_input("52w High", value=float(rad.get("52w High", 0)))
        riktkurs = st.number_input("Riktkurs", value=float(rad.get("Riktkurs", 0)))
        datakalla = st.selectbox("Datakälla utdelning", ["Yahoo Finance", "Manuell"], index=0 if rad.get("Datakälla utdelning", "") != "Manuell" else 1)

        sparaknapp = st.form_submit_button("💾 Spara")

    if sparaknapp:
        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": namn,
            "Utdelning": utdelning,
            "Valuta": valuta,
            "Äger": "Ja" if ager else "Nej",
            "Kurs": kurs,
            "52w High": high,
            "Riktkurs": riktkurs,
            "Datakälla utdelning": datakalla
        }

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
            st.success(f"{ticker} uppdaterat!")
        else:
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            st.success(f"{ticker} tillagt!")
    return df

def uppdatera_fr_yahoo(df):
    st.subheader("🔄 Uppdatera från Yahoo Finance")
    valt = st.selectbox("Välj bolag att uppdatera", ["Alla"] + df["Ticker"].tolist())

    if st.button("Uppdatera"):
        misslyckade = []
        if valt == "Alla":
            total = len(df)
            status = st.empty()
            bar = st.progress(0)
            for i, row in df.iterrows():
                ticker = row["Ticker"]
                status.text(f"Uppdaterar {i+1} av {total} – {ticker}")
                try:
                    info = yf.Ticker(ticker).info
                    df.at[i, "Kurs"] = round(info.get("regularMarketPrice", 0), 2)
                    df.at[i, "52w High"] = round(info.get("fiftyTwoWeekHigh", 0), 2)
                    df.at[i, "Valuta"] = info.get("currency", "USD")
                    df.at[i, "Utdelning"] = round(info.get("dividendRate", 0) or 0, 2)
                    df.at[i, "Datakälla utdelning"] = "Yahoo Finance"
                except Exception:
                    misslyckade.append(ticker)
                bar.progress((i+1)/total)
                time.sleep(1)
            status.text("✅ Alla bolag är uppdaterade!")
            if misslyckade:
                st.warning("Kunde inte uppdatera följande tickers:\n" + ", ".join(misslyckade))
        else:
            i = df[df["Ticker"] == valt].index[0]
            try:
                info = yf.Ticker(valt).info
                df.at[i, "Kurs"] = round(info.get("regularMarketPrice", 0), 2)
                df.at[i, "52w High"] = round(info.get("fiftyTwoWeekHigh", 0), 2)
                df.at[i, "Valuta"] = info.get("currency", "USD")
                df.at[i, "Utdelning"] = round(info.get("dividendRate", 0) or 0, 2)
                df.at[i, "Datakälla utdelning"] = "Yahoo Finance"
                st.success(f"✅ {valt} uppdaterad!")
            except Exception:
                st.error(f"Kunde inte uppdatera {valt}")
        spara_data(df)

def analys_och_forslag(df):
    st.subheader("📊 Analys & investeringsförslag")

    # Räkna ut direktavkastning, uppsida och rekommendation
    df["Direktavkastning (%)"] = round((df["Utdelning"] / df["Kurs"]) * 100, 2)
    df["Uppside (%)"] = round(((df["Riktkurs"] - df["Kurs"]) / df["Kurs"]) * 100, 2)
    df["Rekommendation"] = df["Uppside (%)"].apply(lambda x: "Sälj" if x < 0 else "Pausa" if x < 3 else "Behåll" if x < 10 else "Öka" if x < 25 else "Köp kraftigt")

    # Filtrering
    st.markdown("### 🔍 Filtrera bolag")

    kol1, kol2, kol3 = st.columns(3)
    with kol1:
        val_rek = st.multiselect("Rekommendation", ["Sälj", "Pausa", "Behåll", "Öka", "Köp kraftigt"])
    with kol2:
        val_da = st.selectbox("Direktavkastning över", [0, 3, 5, 7, 10], index=0)
    with kol3:
        visa_ager = st.checkbox("Visa endast bolag jag äger")

    filtrerad = df.copy()
    if val_rek:
        filtrerad = filtrerad[filtrerad["Rekommendation"].isin(val_rek)]
    if val_da > 0:
        filtrerad = filtrerad[filtrerad["Direktavkastning (%)"] > val_da]
    if visa_ager:
        filtrerad = filtrerad[filtrerad["Äger"] == "Ja"]

    filtrerad = filtrerad.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

    if filtrerad.empty:
        st.info("Inga bolag matchar filtren.")
        return

    if "forslag_index" not in st.session_state:
        st.session_state.forslag_index = 0

    total = len(filtrerad)
    index = st.session_state.forslag_index
    index = max(0, min(index, total - 1))

    rad = filtrerad.iloc[index]

    st.markdown(f"""
        ### 💡 Förslag {index + 1} av {total}
        - **Bolag:** {rad['Bolagsnamn']} ({rad['Ticker']})
        - **Kurs:** {rad['Kurs']} {rad['Valuta']}
        - **Utdelning:** {rad['Utdelning']} ({rad['Direktavkastning (%)']}%)
        - **Riktkurs:** {rad['Riktkurs']} → **Uppside:** {rad['Uppside (%)']}%
        - **Rekommendation:** {rad['Rekommendation']}
    """)

    kn1, kn2 = st.columns([1, 1])
    with kn1:
        if st.button("⬅️ Föregående"):
            if st.session_state.forslag_index > 0:
                st.session_state.forslag_index -= 1
    with kn2:
        if st.button("➡️ Nästa"):
            if st.session_state.forslag_index < total - 1:
                st.session_state.forslag_index += 1

    st.dataframe(filtrerad, use_container_width=True)

def main():
    st.title("📈 Utdelningsaktier – analys & investeringar")
    df = hamta_data()

    meny = st.sidebar.radio("Välj vy", ["Analys & förslag", "Lägg till / uppdatera bolag", "Uppdatera från Yahoo"])

    if meny == "Analys & förslag":
        analys_och_forslag(df)
    elif meny == "Lägg till / uppdatera bolag":
        df = lagg_till_eller_uppdatera(df)
        spara_data(df)
    elif meny == "Uppdatera från Yahoo":
        uppdatera_fr_yahoo(df)

if __name__ == "__main__":
    main()
