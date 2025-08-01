import streamlit as st
import pandas as pd
import gspread
import yfinance as yf
import time
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Utdelningsaktier", layout="wide")

# 🔐 Auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(st.secrets["GOOGLE_CREDENTIALS"], scopes=scope)
client = gspread.authorize(credentials)
sheet = client.open_by_url(st.secrets["SHEET_URL"]).worksheet("Bolag")

def hamta_data():
    return pd.DataFrame(sheet.get_all_records())

def spara_data(df):
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

def berakna_kolumner(df):
    df["Direktavkastning (%)"] = round(df["Utdelning"] / df["Kurs"] * 100, 2)
    df["Uppside (%)"] = round((df["Riktkurs"] - df["Kurs"]) / df["Kurs"] * 100, 2)
    df["Rekommendation"] = df["Uppside (%)"].apply(lambda u: (
        "Sälj" if u < 0 else
        "Pausa" if u < 3 else
        "Behåll" if u < 10 else
        "Öka" if u < 50 else
        "Köp kraftigt"
    ))
    return df

def filtrera_data(df):
    st.subheader("🔎 Filtrera bolag")

    val = st.multiselect("Filtrera på rekommendation", df["Rekommendation"].unique())
    da_filter = st.selectbox("Visa bara med direktavkastning över...", [0, 3, 5, 7, 10])
    visa_ager = st.checkbox("Visa endast bolag jag äger")

    if val:
        df = df[df["Rekommendation"].isin(val)]
    if da_filter > 0:
        df = df[df["Direktavkastning (%)"] >= da_filter]
    if visa_ager:
        df = df[df["Äger"] == "Ja"]

    st.markdown(f"**{len(df)} bolag matchar filtret.**")
    return df.sort_values("Uppside (%)", ascending=False).reset_index(drop=True)

def investeringsvy(df):
    st.subheader("📊 Investeringsanalys & förslag")
    kapital = st.number_input("Tillgängligt kapital (SEK)", value=1000)

    if "index" not in st.session_state:
        st.session_state.index = 0

    if df.empty:
        st.info("Inga bolag matchar dina filter.")
        return

    i = st.session_state.index
    if i >= len(df):
        st.info("Du har nått slutet av listan.")
        return

    rad = df.iloc[i]
    kurs = rad["Kurs"]
    antal = int(kapital // kurs)
    investering = antal * kurs

    st.markdown(f"""
    ### 📈 Förslag {i+1} av {len(df)}
    - **Bolag:** {rad['Bolagsnamn']} ({rad['Ticker']})
    - **Aktuell kurs:** {kurs} {rad['Valuta']}
    - **Utdelning:** {rad['Utdelning']} ({rad['Direktavkastning (%)']}%)
    - **Riktkurs:** {rad['Riktkurs']} ({rad['Uppside (%)']}%)
    - **Rekommendation:** {rad['Rekommendation']}
    - **Köp:** {antal} aktier för {round(investering, 2)} {rad['Valuta']}
    """)

    col1, col2 = st.columns(2)
    if col1.button("⬅️ Föregående") and st.session_state.index > 0:
        st.session_state.index -= 1
    if col2.button("➡️ Nästa") and st.session_state.index < len(df) - 1:
        st.session_state.index += 1

def lagg_till_eller_uppdatera(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    tickers = df["Ticker"].tolist()
    valt = st.selectbox("Välj bolag att uppdatera", [""] + tickers)

    if valt:
        rad = df[df["Ticker"] == valt].iloc[0]
    else:
        rad = {}

    with st.form("form_lagg_till"):
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

def uppdatera_yahoo(df):
    st.subheader("🔄 Uppdatera från Yahoo Finance")
    val = st.selectbox("Välj bolag att uppdatera", ["Alla"] + list(df["Ticker"]))

    if st.button("🔁 Starta uppdatering"):
        uppdaterade = 0
        misslyckade = []

        tickers = df["Ticker"].tolist() if val == "Alla" else [val]

        with st.spinner("Uppdaterar..."):
            for i, t in enumerate(tickers):
                st.write(f"🔄 Uppdaterar {i+1} av {len(tickers)}: {t}")
                try:
                    info = yf.Ticker(t).info
                    kurs = info.get("currentPrice")
                    utd = info.get("dividendRate")
                    valuta = info.get("currency", "USD")
                    if kurs:
                        df.loc[df["Ticker"] == t, "Kurs"] = kurs
                    if utd:
                        df.loc[df["Ticker"] == t, "Utdelning"] = utd
                        df.loc[df["Ticker"] == t, "Datakälla utdelning"] = "Yahoo Finance"
                    if valuta:
                        df.loc[df["Ticker"] == t, "Valuta"] = valuta
                    uppdaterade += 1
                except Exception:
                    misslyckade.append(t)
                time.sleep(1)

        spara_data(df)
        st.success(f"✅ Klart. {uppdaterade} bolag uppdaterade.")
        if misslyckade:
            st.warning("❌ Kunde inte uppdatera: " + ", ".join(misslyckade))

def main():
    st.title("📈 Utdelningsaktier med analys & förslag")
    df = hamta_data()
    df = berakna_kolumner(df)

    meny = st.sidebar.radio("Välj vy", ["Analys & förslag", "Lägg till/uppdatera", "Yahoo-uppdatering"])

    if meny == "Analys & förslag":
        filtrerat = filtrera_data(df)
        investeringsvy(filtrerat)
        st.divider()
        st.dataframe(filtrerat, use_container_width=True)

    elif meny == "Lägg till/uppdatera":
        df = lagg_till_eller_uppdatera(df)
        spara_data(df)

    elif meny == "Yahoo-uppdatering":
        uppdatera_yahoo(df)

if __name__ == "__main__":
    main()
