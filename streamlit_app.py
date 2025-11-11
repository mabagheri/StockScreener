import streamlit as st
import pandas as pd
import yfinance as yf
import os
from datetime import datetime, timedelta

st.title("📉 Stock Drop Tracker")

# --- User inputs ---
# excel_file = pd.read_excel("Tickers_Info.xlsx", sheet_name='Canada') 
# st.file_uploader("Upload Excel file with 'Ticker' column", type=["xlsx"])
csv_folder = "Stock_data"  # st.text_input("Enter folder path where your CSV files are stored")

n_option = st.selectbox(
    "Select lookback period",
    ["1 Week", "1 Month", "6 Months", "1 Year"]
)

if n_option == "1 Week":
    n_days = 7
elif n_option == "1 Month":
    n_days = 30
elif n_option == "6 Months":
    n_days = 180
else:
    n_days = 365

# if excel_file and csv_folder:
tickers_info = pd.read_excel("Tickers_Info.xlsx", sheet_name='Canada')
tickers = tickers_info["Ticker"].dropna().unique().tolist()
tickers =  ["SPY", "QQQ", "XIC.TO", 
            "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLK", "XLB", "XLRE", "XLU"]

today = datetime.today().date()
start_date = datetime(2025, 11, 2).date()  # day after your last data

results = []

st.write(f"Fetching latest data since {start_date} ...")

for ticker in tickers:
    csv_path = os.path.join(csv_folder, f"{ticker}.csv")
    if not os.path.exists(csv_path):
        st.warning(f"No CSV found for {ticker}, skipping.")
        continue

    # Load old historical data
    df_old = pd.read_csv(csv_path, parse_dates=["Date"])
    df_old = df_old[df_old["Date"] <= pd.Timestamp("2025-11-01")]

    # Fetch recent data
    df_new = yf.download(ticker, start=start_date, end=today + timedelta(days=1))
    df_new.reset_index(inplace=True)

    # Combine
    df_new = df_new.rename(columns={"Date": "Date"})
    df_all = pd.concat([df_old, df_new], ignore_index=True).drop_duplicates(subset=["Date"])

    # Keep only last n days
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

if results:
    df_results = pd.DataFrame(results)
    # Style: highlight drops
    def highlight_drop(val):
        color = 'red' if val < 0 else 'green'
        return f'color: {color}'

    st.dataframe(df_results.style.applymap(highlight_drop, subset=[f"Drop % ({n_option})"]))
else:
    st.info("No data available yet.")
