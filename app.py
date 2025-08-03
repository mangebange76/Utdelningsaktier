import streamlit as st
import pandas as pd
import yfinance as yf
import time
import gspread
from google.oauth2.service_account import Credentials

# Google Sheets setup
scope = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_info(
    st.secrets["GOOGLE_CREDENTIALS"], scopes=scope
)
client = gspread.authorize(credentials)
SHEET_URL = st.secrets["SHEET_URL"]
SHEET_NAME = "Bolag"

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

def hamta_yahoo_data(ticker):
    try:
        info = yf.Ticker(ticker).info
        fast_info = yf.Ticker(ticker).fast_info
        earnings_trend = yf.Ticker(ticker).earnings_trend

        kurs = fast_info.get("lastPrice", None)
        high_52w = fast_info.get("yearHigh", None)
        utdelning = info.get("dividendRate", None)
        valuta = info.get("financialCurrency", None)
        namn = info.get("longName", None)
        eps_ttm = info.get("trailingEps", None)

        # EPS om 2 år – gräv djupt från earningsTrend
        eps_om_2_ar = None
        if earnings_trend and "trend" in earnings_trend:
            for p in earnings_trend["trend"]:
                if p.get("period") == "+2y":
                    eps_om_2_ar = p.get("eps")

        # Payout ratio – om EPS finns
        payout_ttm = None
        payout_2y = None
        if utdelning is not None and eps_ttm:
            payout_ttm = round((utdelning / eps_ttm) * 100, 1)
        if utdelning is not None and eps_om_2_ar:
            payout_2y = round((utdelning / eps_om_2_ar) * 100, 1)

        return {
            "Kurs": kurs,
            "52w High": high_52w,
            "Utdelning": utdelning,
            "Valuta": valuta,
            "Bolagsnamn": namn,
            "EPS TTM": eps_ttm,
            "EPS 2 år": eps_om_2_ar,
            "Payout TTM (%)": payout_ttm,
            "Payout 2 år (%)": payout_2y,
            "Datakälla utdelning": "Yahoo Finance" if utdelning else "Manuell inmatning"
        }
    except Exception as e:
        return {}

def lägg_till_eller_uppdatera(df):
    st.subheader("Lägg till eller uppdatera bolag")

    tickers = df["Ticker"].tolist()
    val_befintligt = st.selectbox("Välj bolag att uppdatera (eller lämna tomt för nytt)", ["" ] + tickers)

    with st.form("lägg_till_bolag_form"):
        ticker = st.text_input("Ticker").upper() if val_befintligt == "" else val_befintligt
        namn = st.text_input("Bolagsnamn", value=df[df["Ticker"] == ticker]["Bolagsnamn"].values[0] if ticker in tickers else "")
        utdelning = st.number_input("Utdelning", min_value=0.0, step=0.01)
        valuta = st.selectbox("Valuta", ["USD", "SEK", "EUR", "NOK", "CAD"], index=0)
        äger = st.checkbox("Äger aktien", value=df[df["Ticker"] == ticker]["Äger"].values[0] if ticker in tickers else False)

        kurs = st.number_input("Aktuell kurs", min_value=0.0, step=0.01)
        high_52w = st.number_input("52w High", min_value=0.0, step=0.01)
        eps_ttm = st.number_input("EPS TTM", min_value=0.0, step=0.01)
        eps_2y = st.number_input("EPS om 2 år", min_value=0.0, step=0.01)

        spara = st.form_submit_button("Spara")

    if spara:
        yahoo_data = hamta_yahoo_data(ticker)
        ny_data = {
            "Ticker": ticker,
            "Bolagsnamn": yahoo_data.get("Bolagsnamn", namn),
            "Utdelning": yahoo_data.get("Utdelning", utdelning),
            "Valuta": yahoo_data.get("Valuta", valuta),
            "Äger": äger,
            "Kurs": yahoo_data.get("Kurs", kurs),
            "52w High": yahoo_data.get("52w High", high_52w),
            "EPS TTM": yahoo_data.get("EPS TTM", eps_ttm),
            "EPS 2 år": yahoo_data.get("EPS 2 år", eps_2y),
            "Datakälla utdelning": yahoo_data.get("Datakälla utdelning", "Manuell inmatning")
        }

        if ny_data["EPS TTM"] and ny_data["Utdelning"]:
            ny_data["Payout TTM (%)"] = round((ny_data["Utdelning"] / ny_data["EPS TTM"]) * 100, 1)
        else:
            ny_data["Payout TTM (%)"] = None

        if ny_data["EPS 2 år"] and ny_data["Utdelning"]:
            ny_data["Payout 2 år (%)"] = round((ny_data["Utdelning"] / ny_data["EPS 2 år"]) * 100, 1)
        else:
            ny_data["Payout 2 år (%)"] = None

        ny_data = pd.DataFrame([ny_data])

        if ticker in tickers:
            df.update(ny_data)
            st.success(f"{ticker} uppdaterad.")
        else:
            df = pd.concat([df, ny_data], ignore_index=True)
            st.success(f"{ticker} tillagd.")

        spara_data(df)

    return df

def analysvy(df):
    st.subheader("📊 Analys & investeringsförslag")

    # Filtreringsalternativ
    kol_rek = df["Rekommendation"].dropna().unique().tolist()
    val_rek = st.multiselect("Filtrera på rekommendation", kol_rek, default=kol_rek)

    direktval = st.selectbox("Minsta direktavkastning (%)", [0, 3, 5, 7, 10], index=0)
    visa_äger = st.checkbox("Visa endast bolag jag äger")
    visa_eps_tillväxt = st.checkbox("Visa endast bolag med stigande vinst (EPS 2 år > EPS TTM)")

    payout_min = st.slider("Payout ratio om 2 år (minimum %)", min_value=0, max_value=100, value=0)
    payout_max = st.slider("Payout ratio om 2 år (maximum %)", min_value=0, max_value=100, value=100)

    filtrerat_df = df.copy()

    if val_rek:
        filtrerat_df = filtrerat_df[filtrerat_df["Rekommendation"].isin(val_rek)]
    if visa_äger:
        filtrerat_df = filtrerat_df[filtrerat_df["Äger"] == True]
    if direktval > 0:
        filtrerat_df = filtrerat_df[filtrerat_df["Direktavkastning (%)"] >= direktval]
    if visa_eps_tillväxt:
        filtrerat_df = filtrerat_df[(filtrerat_df["EPS 2 år"] > filtrerat_df["EPS TTM"])]
    filtrerat_df = filtrerat_df[
        (filtrerat_df["Payout 2 år (%)"].fillna(0) >= payout_min) &
        (filtrerat_df["Payout 2 år (%)"].fillna(0) <= payout_max)
    ]

    filtrerat_df = filtrerat_df.sort_values(by="Uppside (%)", ascending=False)

    st.markdown(f"### {len(filtrerat_df)} bolag matchar dina filter")
    
    if len(filtrerat_df) == 0:
        st.warning("Inga bolag matchar dina filter.")
        return

    # Bläddra bland bolag
    index = st.number_input("Bläddra mellan förslag", min_value=1, max_value=len(filtrerat_df), step=1)
    valt_bolag = filtrerat_df.iloc[index - 1]

    st.markdown(f"#### Förslag {index} av {len(filtrerat_df)}")
    st.write(valt_bolag.to_frame().T)

    # Visa hela tabellen längst ner
    st.markdown("---")
    st.markdown("### Samtliga bolag i databasen")
    st.dataframe(df.reset_index(drop=True))

def menyval():
    return st.sidebar.radio("Meny", ["Lägg till / uppdatera bolag", "Analys & investeringsförslag", "Uppdatera alla bolag"])

def main():
    st.set_page_config(page_title="Utdelningsaktier", layout="wide")
    meny = menyval()
    df = hamta_data()
    df = säkerställ_kolumner(df)

    if meny == "Lägg till / uppdatera bolag":
        lägg_till_eller_uppdatera(df)

    elif meny == "Analys & investeringsförslag":
        analysvy(df)

    elif meny == "Uppdatera alla bolag":
        st.subheader("🔄 Massuppdatering från Yahoo Finance")
        if st.button("Starta uppdatering"):
            alla_tickers = df["Ticker"].dropna().unique().tolist()
            totalt = len(alla_tickers)
            misslyckade = []

            for i, ticker in enumerate(alla_tickers):
                st.write(f"Uppdaterar bolag {i+1} av {totalt}: {ticker}")
                data = hämta_data_yahoo(ticker)
                if data:
                    for key, value in data.items():
                        if key in df.columns:
                            df.loc[df["Ticker"] == ticker, key] = value
                else:
                    misslyckade.append(ticker)
                time.sleep(1)

            spara_data(df)
            if misslyckade:
                st.warning(f"Kunde inte uppdatera följande tickers: {', '.join(misslyckade)}")
            else:
                st.success("Alla bolag har uppdaterats!")

if __name__ == "__main__":
    main()
