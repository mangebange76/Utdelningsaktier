import streamlit as st
import pandas as pd
import yfinance as yf
import time
import gspread
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
    sheet.update([df.columns.values.tolist()] + df.values.tolist())

def hamta_från_yahoo(ticker):
    try:
        info = yf.Ticker(ticker)
        hist = info.history(period="1y")
        if hist.empty:
            return {}

        kurs = round(info.info.get("currentPrice") or info.info.get("regularMarketPrice", 0), 2)
        high_52w = round(hist["Close"].max(), 2)
        utd = round(info.info.get("dividendRate", 0), 2)
        valuta = info.info.get("currency", "")
        namn = info.info.get("shortName", "")

        return {
            "Kurs": kurs,
            "52w High": high_52w,
            "Utdelning": utd,
            "Valuta": valuta,
            "Bolagsnamn": namn,
            "Datakälla utdelning": "Yahoo Finance"
        }
    except:
        return {}

def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger", "Kurs", "52w High",
        "Direktavkastning (%)", "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
    ]
    for kol in kolumner:
        if kol not in df.columns:
            df[kol] = ""
    return df

def beräkna_alla(df, riktkurs_procent):
    df = säkerställ_kolumner(df)
    df["Kurs"] = pd.to_numeric(df["Kurs"], errors="coerce").fillna(0)
    df["52w High"] = pd.to_numeric(df["52w High"], errors="coerce").fillna(0)
    df["Utdelning"] = pd.to_numeric(df["Utdelning"], errors="coerce").fillna(0)
    df["Riktkurs"] = df["52w High"] * (1 - riktkurs_procent / 100)
    df["Direktavkastning (%)"] = (df["Utdelning"] / df["Kurs"]).replace([float("inf")], 0) * 100
    df["Uppside (%)"] = (df["Riktkurs"] / df["Kurs"] - 1).replace([float("inf")], 0) * 100

    def rekommendation(rad):
        uppsida = rad["Uppside (%)"]
        if uppsida >= 50:
            return "Köp kraftigt"
        elif uppsida >= 10:
            return "Öka"
        elif 0 <= uppsida < 10:
            return "Behåll"
        elif -10 <= uppsida < 0:
            return "Pausa"
        else:
            return "Sälj"

    df["Rekommendation"] = df.apply(rekommendation, axis=1)
    return df

def visa_formular(df, sheet):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    tickers = [""] + df["Ticker"].dropna().unique().tolist()
    valt_ticker = st.selectbox("Välj befintlig ticker för uppdatering eller lämna tom för nytt bolag:", tickers)

    with st.form(key="formular"):
        ticker = st.text_input("Ticker", value=valt_ticker or "").upper()
        bolagsnamn = st.text_input("Bolagsnamn", value="")
        utdelning = st.number_input("Utdelning", value=0.0, step=0.01)
        valuta = st.selectbox("Valuta", ["USD", "SEK", "EUR", "NOK", "CAD"])
        ager = st.selectbox("Äger", ["Ja", "Nej"])

        sparaknapp = st.form_submit_button("Spara")

        if sparaknapp:
            data = hamta_från_yahoo(ticker)
            if data:
                kurs = data["Kurs"]
                high_52w = data["52w High"]
                utd = data["Utdelning"]
                valuta = data["Valuta"]
                bolagsnamn = data["Bolagsnamn"]
                källa = data["Datakälla utdelning"]
                st.success(f"Data hämtad: Kurs {kurs}, 52w High {high_52w}, Utdelning {utd}, Valuta {valuta}")
            else:
                st.warning("Kunde inte hämta data från Yahoo Finance, fyll i manuellt.")
                kurs = st.number_input("Kurs", value=0.0, step=0.01)
                high_52w = st.number_input("52w High", value=0.0, step=0.01)
                källa = "Manuell inmatning"

            ny_rad = {
                "Ticker": ticker,
                "Bolagsnamn": bolagsnamn,
                "Utdelning": utdelning if data == {} else utd,
                "Valuta": valuta,
                "Äger": ager,
                "Kurs": kurs,
                "52w High": high_52w,
                "Datakälla utdelning": källa
            }

            if ticker in df["Ticker"].values:
                df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
                st.success("Bolaget uppdaterat.")
            else:
                df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
                st.success("Nytt bolag tillagt.")

            df = beräkna_alla(df, riktkurs_procent=st.session_state.get("riktkurs_procent", 5))
            sheet.update([df.columns.tolist()] + df.values.tolist())

def analysvy(df):
    st.subheader("📈 Analys och investeringsförslag")

    # Filtrering
    unika_rek = df["Rekommendation"].dropna().unique().tolist()
    valda_rek = st.multiselect("Filtrera på rekommendation:", unika_rek, default=unika_rek)

    direkt_filter = st.selectbox("Filtrera på direktavkastning över:", [0, 3, 5, 7, 10], index=0)
    visa_endast_ager = st.checkbox("Visa endast bolag jag äger")

    filtrerat_df = df[df["Rekommendation"].isin(valda_rek)]
    filtrerat_df = filtrerat_df[pd.to_numeric(filtrerat_df["Direktavkastning (%)"], errors="coerce") > direkt_filter]
    if visa_endast_ager:
        filtrerat_df = filtrerat_df[filtrerat_df["Äger"] == "Ja"]

    filtrerat_df = filtrerat_df.copy()
    filtrerat_df["Uppside (%)"] = pd.to_numeric(filtrerat_df["Uppside (%)"], errors="coerce")
    filtrerat_df = filtrerat_df.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)

    antal = len(filtrerat_df)
    if antal == 0:
        st.warning("Inga bolag matchar filtren.")
        return

    # Bläddringsfunktion
    index = st.number_input("Förslag", min_value=1, max_value=antal, step=1, value=1)
    bolag = filtrerat_df.iloc[index - 1]

    st.markdown(f"### Förslag {index} av {antal}")
    st.write(f"**{bolag['Bolagsnamn']}** ({bolag['Ticker']})")
    st.write(f"- Kurs: {bolag['Kurs']} {bolag['Valuta']}")
    st.write(f"- Riktkurs: {bolag['Riktkurs']} {bolag['Valuta']}")
    st.write(f"- Uppside: {bolag['Uppside (%)']} %")
    st.write(f"- Direktavkastning: {bolag['Direktavkastning (%)']} %")
    st.write(f"- Utdelning: {bolag['Utdelning']} {bolag['Valuta']}")
    st.write(f"- Rekommendation: **{bolag['Rekommendation']}**")

    # Visa hela tabellen
    st.markdown("---")
    st.subheader("📋 Alla bolag i databasen")
    st.dataframe(df)

def massuppdatera(df):
    st.subheader("🔁 Massuppdatera alla bolag från Yahoo Finance")

    if st.button("Starta massuppdatering"):
        tickers = df["Ticker"].tolist()
        totalt = len(tickers)
        nya_df = df.copy()

        for i, ticker in enumerate(tickers):
            st.info(f"Uppdaterar bolag {i+1} av {totalt}: {ticker}")
            data = hämta_data_från_yahoo(ticker)
            time.sleep(1)

            if data:
                for fält, värde in data.items():
                    if värde:  # Endast skriv över om data finns
                        nya_df.loc[nya_df["Ticker"] == ticker, fält] = värde
                nya_df = beräkna_och_komplettera(nya_df)
            else:
                st.warning(f"Kunde inte hämta data för {ticker} – ingen förändring")

        spara_data(nya_df)
        st.success("✅ Massuppdatering klar!")


def main():
    st.title("📈 Utdelningsaktier – Analys och förslag")
    meny = st.sidebar.radio("Navigera", ["Lägg till / uppdatera bolag", "Analys", "Uppdatera ett bolag", "Uppdatera alla bolag"])

    df = hamta_data()
    df = säkerställ_kolumner(df)

    if meny == "Lägg till / uppdatera bolag":
        lägg_till_eller_uppdatera(df)
    elif meny == "Analys":
        analysvy(df)
    elif meny == "Uppdatera ett bolag":
        uppdatera_enskilt_bolag(df)
    elif meny == "Uppdatera alla bolag":
        massuppdatera(df)


if __name__ == "__main__":
    main()
