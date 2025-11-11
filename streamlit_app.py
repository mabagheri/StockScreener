import streamlit as st
import pandas as pd
import yfinance as yf
import os
from datetime import datetime, timedelta

st.title("📉 Stock Drop Tracker")


# --- User inputs ---
st.markdown("### Step 1: Choose Market and Market Cap Filters")

# File and sheet selection
excel_file = "Tickers_Info.xlsx"
market_choice = st.radio("Select Market:", ["Canada", "US"], horizontal=True)

# Market cap filters
def filter_market_cap(df, cap_choice):
    if cap_choice == "Mega-cap (> $200B)":
        return df[df['MarketCap'] > 200]
    elif cap_choice == "Large-cap ($10B–$200B)":
        return df[(df['MarketCap'] >= 10) & (df['MarketCap'] <= 200)]
    elif cap_choice == "Mid-cap ($2B–$10B)":
        return df[(df['MarketCap'] >= 2) & (df['MarketCap'] < 10)]
    elif cap_choice == "Small-cap ($300M–$2B)":
        return df[(df['MarketCap'] >= 0.3) & (df['MarketCap'] < 2)]
    else:
        return df

cap_choice = st.selectbox(
    "Select Market Cap Range",
    ["All", "Mega-cap (> $200B)", "Large-cap ($10B–$200B)", "Mid-cap ($2B–$10B)", "Small-cap ($300M–$2B)"]
)

# --- Load ticker info ---
try:
    tickers_info = pd.read_excel(excel_file, sheet_name=market_choice)
except Exception as e:
    st.error(f"Error reading Excel file: {e}")
    st.stop()

# Filter by market cap
if 'MarketCap' not in tickers_info.columns:
    st.warning("Excel file must contain a 'MarketCap' column.")
else:
    tickers_info = filter_market_cap(tickers_info, cap_choice)

if tickers_info.empty:
    st.info("No tickers match the selected filters.")
    st.stop()

# --- Lookback period selection ---
n_option = st.selectbox(
    "Select lookback period",
    ["1 Week", "1 Month", "6 Months", "1 Year"]
)

n_days = {"1 Week": 7, "1 Month": 30, "6 Months": 180, "1 Year": 365}[n_option]

# --- Folder for CSV files ---
csv_folder = "Stock_data"

# --- Prepare tickers list ---
tickers = tickers_info["Ticker"].dropna().unique().tolist()

if not tickers:
    st.warning("No tickers found in selected sheet.")
    st.stop()

results = []
today = datetime.today().date()
start_date = datetime(2025, 11, 2).date()
st.markdown(f"### Step 2: Fetching Data ({market_choice} Market) since {start_date} ...")

# tickers_info = pd.read_excel("Tickers_Info.xlsx", sheet_name='Canada')
# tickers = tickers_info["Ticker"].dropna().unique().tolist()
# tickers = ["SPY", "QQQ", "XIC.TO", "XLC", "XLY", "XLP", "XLV", "XLI", "XLK", "XLRE", "XLU"]
progress_bar = st.progress(0)
status_text = st.empty()
for i, ticker in enumerate(tickers, start=1):      
    
    csv_path = os.path.join(csv_folder, f"{ticker}.csv")
    if not os.path.exists(csv_path):
        st.warning(f"No CSV found for {ticker}, skipping.")
        continue

    # Load old historical data
    df_old = pd.read_csv(csv_path, parse_dates=["Date"])
    df_old = df_old[df_old["Date"] <= pd.Timestamp("2025-11-01")]
    # st.write(ticker, df_old.shape, df_old.head(3))

    # Fetch recent data
    status_text.text(f"Downloading {ticker} ({i}/{len(tickers)}) ...")
    df_new = yf.download(ticker, start=start_date, end=today + timedelta(days=1))
    # st.write(ticker, df_new.shape, df_new.head(4))

    df_new = df_new.iloc[:, :].reset_index(drop=False)
    # st.write(ticker, df_new.shape, df_new.head(4))
    df_new.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
    # st.write(ticker, df_new.shape, df_new.head(4))

    # Combine
    df_all = pd.concat([df_old, df_new], ignore_index=True).drop_duplicates(subset=["Date"])
    # st.write(ticker, df_all.shape, df_all.head(5))

    # Keep only the last n days
    cutoff = datetime.today() - timedelta(days=n_days)
    
    df_window = df_all[df_all["Date"] >= cutoff]

    if df_window.empty:
        continue

    current_price = df_window.iloc[-1]["Close"]
    highest_price = df_window["Close"].max()
    drop_pct = (current_price - highest_price) / highest_price * 100

    results.append({
        "Ticker": ticker,
        "Current Price": round(current_price, 2),
        f"Highest ({n_option})": round(highest_price, 2),
        f"Drop % ({n_option})": round(drop_pct, 2)
    })
    # st.write(results)

if results:
    df_results = pd.DataFrame(results)
    # Style: highlight drops
    def highlight_drop(val):
        color = 'red' if val < 0 else 'green'
        return f'color: {color}'

    st.dataframe(df_results.style.applymap(highlight_drop, subset=[f"Drop % ({n_option})"]))
else:
    st.info("No data available yet.")
