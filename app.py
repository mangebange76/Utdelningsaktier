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
    return pd.DataFrame(skapa_koppling().get_all_records())

def spara_data(df):
    sheet = skapa_koppling()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

def säkerställ_kolumner(df):
    önskade_kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger",
        "Kurs", "52w High", "Direktavkastning (%)",
        "Riktkurs", "Uppside (%)", "Rekommendation", "Datakälla utdelning"
    ]
    for kol in önskade_kolumner:
        if kol not in df.columns:
            if "%" in kol or kol in ["Kurs", "Utdelning", "52w High", "Riktkurs", "Uppside (%)"]:
                df[kol] = 0.0
            elif kol == "Äger":
                df[kol] = False
            else:
                df[kol] = ""
    return df

def beräkna_rekommendationer(df):
    df["Direktavkastning (%)"] = (df["Utdelning"] / df["Kurs"]) * 100
    df["Uppside (%)"] = ((df["Riktkurs"] - df["Kurs"]) / df["Kurs"]) * 100

    def rekommendation(rad):
        if rad["Uppside (%)"] > 50:
            return "Köp kraftigt"
        elif 10 < rad["Uppside (%)"] <= 50:
            return "Öka"
        elif 3 < rad["Uppside (%)"] <= 10:
            return "Behåll"
        elif -5 <= rad["Uppside (%)"] <= 3:
            return "Pausa"
        else:
            return "Sälj"
    df["Rekommendation"] = df.apply(rekommendation, axis=1)
    return df

def hamta_yahoo_data(ticker):
    try:
        aktie = yf.Ticker(ticker)
        info = aktie.info
        kurs = info.get("regularMarketPrice")
        high = info.get("fiftyTwoWeekHigh")
        utd = info.get("dividendRate") or 0.0
        valuta = info.get("currency")
        namn = info.get("longName") or info.get("shortName") or ticker
        return kurs, high, utd, valuta, namn
    except:
        return None, None, None, None, None

def lagg_till_eller_uppdatera_bolag(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    ticker_list = df["Ticker"].unique().tolist()
    namn_map = {f"{row['Bolagsnamn']} ({row['Ticker']})": row['Ticker'] for _, row in df.iterrows()}

    valt = st.selectbox("Välj bolag att uppdatera (eller lämna tom för nytt)", [""] + list(namn_map.keys()))
    if valt:
        ticker_vald = namn_map[valt]
        befintlig = df[df["Ticker"] == ticker_vald].iloc[0]
    else:
        befintlig = pd.Series(dtype=object)

    with st.form("form_nytt_bolag"):
        ticker = st.text_input("Ticker", value=befintlig.get("Ticker", "") if not befintlig.empty else "").upper()
        namn = st.text_input("Bolagsnamn", value=befintlig.get("Bolagsnamn", "") if not befintlig.empty else "")
        kurs = st.number_input("Aktuell kurs", value=float(befintlig.get("Kurs", 0.0)) if not befintlig.empty else 0.0)
        high = st.number_input("52w High", value=float(befintlig.get("52w High", 0.0)) if not befintlig.empty else 0.0)
        utd = st.number_input("Årlig utdelning", value=float(befintlig.get("Utdelning", 0.0)) if not befintlig.empty else 0.0)
        riktkurs = st.number_input("Riktkurs", value=float(befintlig.get("Riktkurs", 0.0)) if not befintlig.empty else 0.0)
        valuta = st.selectbox("Valuta", ["USD", "SEK", "NOK", "EUR", "CAD"],
                              index=0 if befintlig.empty else ["USD", "SEK", "NOK", "EUR", "CAD"].index(befintlig.get("Valuta", "USD")))
        ager = st.checkbox("Jag äger aktien", value=befintlig.get("Äger", False) if not befintlig.empty else False)
        sparaknapp = st.form_submit_button("💾 Spara bolag")

    if sparaknapp and ticker:
        ykurs, yhigh, yutd, yvaluta, ynamn = hamta_yahoo_data(ticker)
        datakälla = "Yahoo Finance" if ykurs else "Manuell inmatning"

        ny_rad = {
            "Ticker": ticker,
            "Bolagsnamn": ynamn if ykurs else namn,
            "Kurs": ykurs if ykurs else kurs,
            "52w High": yhigh if yhigh else high,
            "Utdelning": yutd if ykurs else utd,
            "Valuta": yvaluta if ykurs else valuta,
            "Riktkurs": riktkurs,
            "Äger": ager,
            "Datakälla utdelning": datakälla
        }

        if not ykurs:
            st.warning("⚠️ Kunde inte hämta data – använd manuella värden.")

        if ticker in df["Ticker"].values:
            df.loc[df["Ticker"] == ticker, ny_rad.keys()] = ny_rad.values()
            st.success(f"{ticker} uppdaterat.")
        else:
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)
            st.success(f"{ticker} tillagt.")

        df = beräkna_rekommendationer(df)
        spara_data(df)
    return df

def analys_och_investeringsvy(df):
    st.subheader("📊 Analys & investeringsförslag")

    filtrerade = df.copy()

    rekommendationer = filtrerade["Rekommendation"].unique().tolist()
    rek_val = st.selectbox("Filtrera på rekommendation", ["Alla"] + sorted(rekommendationer))
    if rek_val != "Alla":
        filtrerade = filtrerade[filtrerade["Rekommendation"] == rek_val]

    direktval = st.selectbox("Direktavkastning över", ["Ingen", "3", "5", "7", "10"])
    if direktval != "Ingen":
        filtrerade = filtrerade[filtrerade["Direktavkastning (%)"] > float(direktval)]

    visa_ager = st.checkbox("Visa endast bolag jag äger")
    if visa_ager:
        filtrerade = filtrerade[filtrerade["Äger"] == True]

    filtrerade = filtrerade.sort_values(by="Uppside (%)", ascending=False).reset_index(drop=True)

    st.caption(f"🔎 Visar {len(filtrerade)} bolag")

    if len(filtrerade) == 0:
        st.warning("Inga bolag matchar filtervalen.")
        return

    if "analys_index" not in st.session_state:
        st.session_state.analys_index = 0

    index = st.session_state.analys_index
    if index >= len(filtrerade):
        index = 0
        st.session_state.analys_index = 0

    rad = filtrerade.iloc[index]

    st.markdown(f"### 📈 Förslag {index+1} av {len(filtrerade)}")
    st.markdown(f"""
    - **Bolag:** {rad['Bolagsnamn']} ({rad['Ticker']})
    - **Aktuell kurs:** {rad['Kurs']} {rad['Valuta']}
    - **52w High:** {rad['52w High']} {rad['Valuta']}
    - **Riktkurs:** {rad['Riktkurs']} {rad['Valuta']}
    - **Uppside:** {round(rad['Uppside (%)'], 2)}%
    - **Direktavkastning:** {round(rad['Direktavkastning (%)'], 2)}%
    - **Rekommendation:** {rad['Rekommendation']}
    """)

    col1, col2 = st.columns(2)
    if col1.button("⬅️ Föregående"):
        st.session_state.analys_index = max(index - 1, 0)
    if col2.button("➡️ Nästa"):
        st.session_state.analys_index = min(index + 1, len(filtrerade) - 1)

def uppdatera_kurser(df):
    st.subheader("🔄 Uppdatera data från Yahoo Finance")
    tickers = df["Ticker"].tolist()
    misslyckade = []

    status = st.empty()
    bar = st.progress(0)
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        status.text(f"🔄 Uppdaterar {i+1}/{total}: {ticker}")
        kurs, high, utd, valuta, namn = hamta_yahoo_data(ticker)

        if kurs:
            df.loc[df["Ticker"] == ticker, "Kurs"] = kurs
            df.loc[df["Ticker"] == ticker, "52w High"] = high
            df.loc[df["Ticker"] == ticker, "Utdelning"] = utd
            df.loc[df["Ticker"] == ticker, "Valuta"] = valuta
            df.loc[df["Ticker"] == ticker, "Bolagsnamn"] = namn
            df.loc[df["Ticker"] == ticker, "Datakälla utdelning"] = "Yahoo Finance"
        else:
            misslyckade.append(ticker)

        bar.progress((i+1)/total)
        time.sleep(1)

    df = beräkna_rekommendationer(df)
    spara_data(df)
    status.text("✅ Uppdatering klar.")
    if misslyckade:
        st.warning("Kunde inte uppdatera följande tickers:\n" + ", ".join(misslyckade))

def main():
    st.title("💰 Utdelningsaktier")

    df = hamta_data()
    df = säkerställ_kolumner(df)
    df = beräkna_rekommendationer(df)

    meny = st.sidebar.radio("Meny", ["Analys & förslag", "Lägg till / uppdatera bolag", "Uppdatera alla kurser"])
    if meny == "Analys & förslag":
        analys_och_investeringsvy(df)
    elif meny == "Lägg till / uppdatera bolag":
        df = lagg_till_eller_uppdatera_bolag(df)
    elif meny == "Uppdatera alla kurser":
        uppdatera_kurser(df)

if __name__ == "__main__":
    main()
