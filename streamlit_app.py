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
st.write(tickers)
tickers = ["SPY", "QQQ", "XIC.TO", "XLC", "XLY", "XLP", "XLV", "XLI", "XLK", "XLRE", "XLU"]

today = datetime.today().date()
start_date = datetime(2025, 11, 2).date()  # day after your last data

results = []

st.write(f"Fetching latest data since {start_date} ...")

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
    highest_price = df_window["High"].max()
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
