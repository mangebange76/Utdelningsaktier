import streamlit as st
import pandas as pd
import yfinance as yf
import gspread
import time
from google.oauth2.service_account import Credentials

# === Google Sheets setup ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(
    st.secrets["GOOGLE_CREDENTIALS"], scopes=scope
)
client = gspread.authorize(credentials)
sheet = client.open_by_url(st.secrets["SHEET_URL"]).worksheet("Bolag")

# === Grundinställningar ===
VALUTALISTA = ["USD", "SEK", "EUR", "NOK", "CAD"]
REK_LISTA = ["Köp kraftigt", "Öka", "Behåll", "Pausa", "Sälj"]

# === Funktioner ===
def säkerställ_kolumner(df):
    kolumner = [
        "Ticker", "Bolagsnamn", "Utdelning", "Valuta", "Äger",
        "Kurs", "52w High", "Direktavkastning (%)", "Riktkurs", "Uppside (%)",
        "Rekommendation", "Datakälla utdelning", "EPS TTM", "EPS om 2 år",
        "Payout ratio TTM (%)", "Payout ratio 2 år (%)"
    ]
    for col in kolumner:
        if col not in df.columns:
            df[col] = ""
    return df

def hamta_data():
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    df = säkerställ_kolumner(df)
    return df

def spara_data(df):
    sheet.clear()
    sheet.append_row(df.columns.tolist())
    for _, row in df.iterrows():
        sheet.append_row([str(x) for x in row.tolist()])

def yahoo_data(ticker):
    try:
        aktie = yf.Ticker(ticker)
        info = aktie.info

        return {
            "Kurs": info.get("currentPrice"),
            "52w High": info.get("fiftyTwoWeekHigh"),
            "Utdelning": info.get("dividendRate"),
            "Valuta": info.get("currency"),
            "Bolagsnamn": info.get("longName") or info.get("shortName"),
            "EPS TTM": info.get("trailingEps"),
            "EPS om 2 år": info.get("forwardEps"),
            "Datakälla utdelning": "Yahoo Finance"
        }
    except:
        return {}

def beräkna_fält(df):
    df["Kurs"] = pd.to_numeric(df["Kurs"], errors="coerce")
    df["52w High"] = pd.to_numeric(df["52w High"], errors="coerce")
    df["Utdelning"] = pd.to_numeric(df["Utdelning"], errors="coerce")
    df["EPS TTM"] = pd.to_numeric(df["EPS TTM"], errors="coerce")
    df["EPS om 2 år"] = pd.to_numeric(df["EPS om 2 år"], errors="coerce")

    df["Direktavkastning (%)"] = (df["Utdelning"] / df["Kurs"] * 100).round(2)
    df["Riktkurs"] = (df["52w High"] * 0.95).round(2)
    df["Uppside (%)"] = ((df["Riktkurs"] - df["Kurs"]) / df["Kurs"] * 100).round(2)
    df["Payout ratio TTM (%)"] = (df["Utdelning"] / df["EPS TTM"] * 100).round(2)
    df["Payout ratio 2 år (%)"] = (df["Utdelning"] / df["EPS om 2 år"] * 100).round(2)

    df["Rekommendation"] = df["Uppside (%)"].apply(lambda x:
        "Köp kraftigt" if x > 50 else
        "Öka" if x > 10 else
        "Behåll" if x > 3 else
        "Pausa" if x > 0 else
        "Sälj"
    )
    return df

def visa_bolag(df, i, filtrerat_df):
    bolag = filtrerat_df.iloc[i]
    st.subheader(f"Förslag {i+1} av {len(filtrerat_df)}")
    for kolumn in df.columns:
        st.write(f"**{kolumn}:** {bolag[kolumn]}")

def lägg_till_eller_uppdatera(df):
    st.subheader("➕ Lägg till eller uppdatera bolag")
    tickers = df["Ticker"].tolist()
    valt_bolag = st.selectbox("Välj bolag att uppdatera (eller lämna tomt för nytt)", [""] + tickers)
    
    if valt_bolag:
        existerande = df[df["Ticker"] == valt_bolag].iloc[0].to_dict()
    else:
        existerande = {k: "" for k in df.columns}

    with st.form("nytt_bolag"):
        ticker = st.text_input("Ticker", existerande["Ticker"])
        utdelning = st.text_input("Utdelning", existerande["Utdelning"])
        valuta = st.selectbox("Valuta", VALUTALISTA, index=VALUTALISTA.index(existerande["Valuta"]) if existerande["Valuta"] in VALUTALISTA else 0)
        äger = st.selectbox("Äger", ["Ja", "Nej"], index=0 if existerande["Äger"] == "Ja" else 1)
        spara = st.form_submit_button("Spara")

    if spara and ticker:
        data = yahoo_data(ticker)
        if data:
            st.success(f"Hämtad data: Kurs {data.get('Kurs')} {data.get('Valuta')}, Utdelning {data.get('Utdelning')}")
        else:
            st.warning("Kunde inte hämta data – fyll i manuellt!")

        ny_rad = {
            "Ticker": ticker,
            "Utdelning": data.get("Utdelning") or utdelning,
            "Valuta": data.get("Valuta") or valuta,
            "Äger": äger,
            "Kurs": data.get("Kurs") or "",
            "52w High": data.get("52w High") or "",
            "Bolagsnamn": data.get("Bolagsnamn") or "",
            "EPS TTM": data.get("EPS TTM") or "",
            "EPS om 2 år": data.get("EPS om 2 år") or "",
            "Datakälla utdelning": data.get("Datakälla utdelning") or "Manuell inmatning"
        }

        if valt_bolag:
            index = df[df["Ticker"] == valt_bolag].index[0]
            for k, v in ny_rad.items():
                df.at[index, k] = v
        else:
            for k in df.columns:
                if k not in ny_rad:
                    ny_rad[k] = ""
            df = pd.concat([df, pd.DataFrame([ny_rad])], ignore_index=True)

        df = beräkna_fält(df)
        spara_data(df)
        st.success("Bolaget har sparats!")

def main():
    st.title("📊 Utdelningsaktier – Analys och investeringsförslag")
    df = hamta_data()

    # === Lägg till / uppdatera ===
    lägg_till_eller_uppdatera(df)

    # === Filtrering ===
    st.subheader("🔍 Filtrera bolag")
    valda_rek = st.multiselect("Rekommendation", sorted(df["Rekommendation"].unique()))
    direkt_filter = st.selectbox("Minsta direktavkastning (%)", [0, 3, 5, 7, 10])
    visa_ägda = st.checkbox("Visa endast bolag jag äger")
    eps_vinst = st.checkbox("EPS 2 år > EPS TTM")
    payout_min = st.slider("Payout 2 år min (%)", 0, 100, 0)
    payout_max = st.slider("Payout 2 år max (%)", 0, 100, 100)

    filtrerat = df.copy()
    if valda_rek:
        filtrerat = filtrerat[filtrerat["Rekommendation"].isin(valda_rek)]
    filtrerat = filtrerat[pd.to_numeric(filtrerat["Direktavkastning (%)"], errors="coerce") >= direkt_filter]
    if visa_ägda:
        filtrerat = filtrerat[filtrerat["Äger"].str.lower() == "ja"]
    if eps_vinst:
        filtrerat = filtrerat[
            pd.to_numeric(filtrerat["EPS om 2 år"], errors="coerce") >
            pd.to_numeric(filtrerat["EPS TTM"], errors="coerce")
        ]
    filtrerat = filtrerat[
        (pd.to_numeric(filtrerat["Payout ratio 2 år (%)"], errors="coerce") >= payout_min) &
        (pd.to_numeric(filtrerat["Payout ratio 2 år (%)"], errors="coerce") <= payout_max)
    ]

    # === Bläddra ===
    st.subheader(f"📈 Investeringsförslag ({len(filtrerat)} bolag)")
    if not filtrerat.empty:
        index = st.number_input("Bläddra", 1, len(filtrerat), step=1) - 1
        visa_bolag(df, index, filtrerat)
    else:
        st.warning("Inga bolag matchar filtren.")

    # === Massuppdatering ===
    st.subheader("🔁 Massuppdatera från Yahoo")
    if st.button("Uppdatera alla"):
        fel = []
        for i, row in df.iterrows():
            st.info(f"Uppdaterar {i+1}/{len(df)}: {row['Ticker']}")
            data = yahoo_data(row["Ticker"])
            if data:
                for key, val in data.items():
                    df.at[i, key] = val
            else:
                fel.append(row["Ticker"])
            time.sleep(1)
        df = beräkna_fält(df)
        spara_data(df)
        if fel:
            st.warning("Kunde inte uppdatera: " + ", ".join(fel))
        else:
            st.success("Alla bolag uppdaterade!")

    # === Visa alla bolag ===
    st.subheader("📋 Alla bolag i databasen")
    st.dataframe(df)

if __name__ == "__main__":
    main()
