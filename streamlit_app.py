import streamlit as st
import pandas as pd
import yfinance as yf
import os
from datetime import datetime, timedelta

st.title("📉 Stock Drop Tracker!!!")


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
        return df[(df['MarketCap'] >= 100) & (df['MarketCap'] <= 200)]
    elif cap_choice == "Mid-cap ($2B–$10B)":
        return df[(df['MarketCap'] >= 2) & (df['MarketCap'] < 10)]
    elif cap_choice == "Small-cap ($300M–$2B)":
        return df[(df['MarketCap'] >= 0.3) & (df['MarketCap'] < 2)]
    else:
        return df

cap_choice = st.selectbox(
    "Select Market Cap Range",
    ["All", "Mega-cap (> $200B)", "Large-cap ($10B–$200B)", "Mid-cap ($2B–$10B)", "Small-cap ($300M–$2B)"],
    # default="Large-cap ($10B–$200B)"
)

# --- Lookback period selection ---
lookback_options = {
    "1 Week": 7,
    "1 Month": 30,
    "6 Months": 180,
    "1 Year": 365
}
lookbacks_selected = st.multiselect(
    "Lookback Periods:",
    list(lookback_options.keys()),
    default=["1 Month", "6 Months", "1 Year"]
)

# lookbacks_selected = st.selectbox(
#     "Select lookback period",
#     ["1 Week", "1 Month", "6 Months", "1 Year"]
# )
# n_days = {"1 Week": 7, "1 Month": 30, "6 Months": 180, "1 Year": 365}[n_option]

# --- Run button ---
if st.button("Run Stock Drop Analysis"):
    # --- Load ticker info ---
    try:
        tickers_info = pd.read_excel(excel_file, sheet_name=market_choice)
    except Exception as e:
        st.error(f"Error reading Excel file: {e}")
        st.stop()

    # Filter by market cap
    if 'MarketCap' not in tickers_info.columns:
        st.warning("Excel file must contain a 'MarketCap' column.")
        st.stop()
    else:
        tickers_info = filter_market_cap(tickers_info, cap_choice)

    if tickers_info.empty:
        st.info("No tickers match the selected filters.")
        st.stop()

    # --- Folder for CSV files ---
    csv_folder = "Stock_data"

    # --- Prepare tickers list ---
    tickers = tickers_info["Ticker"].dropna().unique().tolist()
    st.write(tickers)

    if not tickers:
        st.warning("No tickers found in selected sheet.")
        st.stop()

    st.markdown(f"### Step 2: Fetching Data ({market_choice} Market)")

    results = []
    today = datetime.today().date()
    start_date = datetime(2025, 11, 2).date()

    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, ticker in enumerate(tickers, start=1):
        csv_path = os.path.join(csv_folder, f"{ticker}.csv")
        if not os.path.exists(csv_path):
            st.warning(f"No CSV found for {ticker}! Dowmload from Jan. 1, 2020")
            status_text.text(f"Downloading {ticker} ({i}/{len(tickers)}) ...")

            df_all = yf.download(ticker, start=datetime(2020, 1, 1).date(), end=today + timedelta(days=1))
            df_all = df_all.reset_index()
            # continue

        else:
            try:
                df_old = pd.read_csv(csv_path, parse_dates=["Date"])
                df_old = df_old[df_old["Date"] <= pd.Timestamp("2025-11-01")]
            except Exception as e:
                st.warning(f"Error loading {ticker}: {e}")
                continue

            # st.write("df_old")
            # st.dataframe(df_old.tail(6))

            status_text.text(f"Downloading {ticker} ({i}/{len(tickers)}): latest days")
            df_new = yf.download(ticker, start=start_date, end=today + timedelta(days=1))
            # st.write(115, df_new.columns)
            if df_new.empty:
                continue
    
            # st.write("119, df_new")
            # st.dataframe(df_new.tail(26))
            df_new = df_new.iloc[:, :].reset_index(drop=False)
            # st.write("125, df_new")
            # st.dataframe(df_new.tail(30))
            # st.write("119", df_new.shape)

            # st.write("122,df_new")
            # st.dataframe(df_new.tail(26))

            # df_new = df_new.rename(columns={"Adj Close": "Close"})
            # df_new = df_new[["Date", "Close", "High", "Low", "Open", "Volume"]]
            df_new.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
            df_all = pd.concat([df_old, df_new], ignore_index=True).drop_duplicates(subset=["Date"])

        # cutoff = datetime.today() - timedelta(days=n_days)
        # df_window = df_all[df_all["Date"] >= cutoff]

        # if df_window.empty:
        #     continue

        st.dataframe(df_all.tail(6))
        current_price = df_all.iloc[-1]["Close"]
        current_date = df_all.iloc[-1]["Date"]
        # st.write(current_date, type(current_date))

        
        row_result = {"Ticker": ticker, "Current": round(current_price, 2)}

        # Compute drop per selected lookback
        for label in lookbacks_selected:
            n_days = lookback_options[label]
            cutoff = datetime.today() - timedelta(days=n_days)

            df_recent = df_all[df_all ["Date"] >= cutoff]
            st.write(cutoff, df_recent.shape)
            # st.write(df_recent.tail(4))
            if df_recent.empty:
                row_result[label] = None
                continue

            highest_price = round(df_recent["Close"].max(), 2)
            drop_pct = (current_price - highest_price) / highest_price * 100
            row_result[f"Drop%({label})"] = round(drop_pct, 2)

        results.append(row_result)

        # results.append({
        #     "Ticker": ticker,
        #     "Current Price": round(current_price, 2),
        #     f"Highest ({n_option})": round(highest_price, 2),
        #     f"Drop % ({n_option})": round(drop_pct, 2)
        # })

        progress_bar.progress(i / len(tickers))

    if results:
        df_results = pd.DataFrame(results)

        def highlight_drop(val):
            color = 'red' if val < 0 else 'green'
            return f'color: {color}'

        st.markdown("### Step 3: Results")
        # st.dataframe(df_results.style.applymap(highlight_drop, subset=[f"Drop % ({n_option})"]))

        st.dataframe(df_results, use_container_width=True)

        # # Download CSV
        # csv = df_summary.to_csv(index=False).encode("utf-8")
        # st.download_button("⬇ Download CSV", csv, "summary.csv", "text/csv")
    
    else:
        st.info("No data available yet.")
