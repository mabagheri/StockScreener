import streamlit as st
import pandas as pd
import yfinance as yf
import os
import io
import zipfile
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# --------------------------------------------------
# App config
# --------------------------------------------------
st.set_page_config(page_title="Stock Drop Tracker", layout="wide")
st.title("📉 Stock Drop Tracker")

DATA_FOLDER = "Stock_data"
EXCEL_FILE = "Tickers_Info.xlsx"
MAX_WORKERS = 8   # parallel downloads (TSX-safe)

# --------------------------------------------------
# Cached historical loader (PER TICKER)
# --------------------------------------------------
@st.cache_data(show_spinner=False)
def load_full_history(ticker: str, today: datetime.date) -> pd.DataFrame:
    """
    Load full historical data for a ticker.
    Cached per ticker to prevent re-downloading.
    """

    csv_path = os.path.join(DATA_FOLDER, f"{ticker}.csv")

    # --- No CSV → full download ---
    if not os.path.exists(csv_path):
        start_date = datetime.today() - relativedelta(years=2)

        df = yf.download(
            ticker,
            start=start_date.date(),
            end=today + timedelta(days=1),
            progress=False,
            threads=False
        )

        if df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df.columns = df.columns.get_level_values(0)
        df.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
        return df

    # --- CSV exists → incremental update ---
    df_old = pd.read_csv(csv_path, parse_dates=["Date"])
    df_old = df_old[df_old["Date"] <= pd.Timestamp("2025-11-01")]

    start_date = datetime(2025, 11, 2).date()
    df_new = yf.download(
        ticker,
        start=start_date,
        end=today + timedelta(days=1),
        progress=False,
        threads=False
    )

    if not df_new.empty:
        df_new = df_new.reset_index()
        df_new.columns = df_new.columns.get_level_values(0)
        df_new.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
        df_all = pd.concat([df_old, df_new], ignore_index=True)
        df_all = df_all.drop_duplicates(subset=["Date"])
    else:
        df_all = df_old

    return df_all


# --------------------------------------------------
# Market cap filter
# --------------------------------------------------
def filter_market_cap(df, cap_choice):
    if cap_choice == "Mega-cap (> $200B)":
        return df[df["MarketCap"] > 200]
    elif cap_choice == "Large-cap ($40B–$200B)":
        return df[(df["MarketCap"] >= 40) & (df["MarketCap"] <= 200)]
    elif cap_choice == "Mid-cap ($2B–$10B)":
        return df[(df["MarketCap"] >= 2) & (df["MarketCap"] < 10)]
    elif cap_choice == "Small-cap ($300M–$2B)":
        return df[(df["MarketCap"] >= 0.3) & (df["MarketCap"] < 2)]
    return df


# --------------------------------------------------
# UI – Step 1
# --------------------------------------------------
st.markdown("### Step 1: Choose Market & Filters")

market_choice = st.radio("Market", ["TSX", "US"], horizontal=True)

cap_choice = st.selectbox(
    "Market Cap",
    [
        "All",
        "Mega-cap (> $200B)",
        "Large-cap ($40B–$200B)",
        "Mid-cap ($2B–$10B)",
        "Small-cap ($300M–$2B)"
    ]
)

lookback_options = {
    "1 Week": datetime.today() - relativedelta(days=7),
    "1 Month": datetime.today() - relativedelta(months=1),
    "6 Months": datetime.today() - relativedelta(months=6),
    "1 Year": datetime.today() - relativedelta(years=1)
}

lookbacks_selected = st.multiselect(
    "Lookback Periods",
    list(lookback_options.keys()),
    default=["1 Month", "6 Months", "1 Year"]
)

# --------------------------------------------------
# Run
# --------------------------------------------------
if st.button("🚀 Run Stock Drop Analysis"):

    # --- Load tickers ---
    try:
        tickers_info = pd.read_excel(EXCEL_FILE, sheet_name=market_choice)
    except Exception as e:
        st.error(f"Excel error: {e}")
        st.stop()

    if "MarketCap" not in tickers_info.columns:
        st.error("Excel must contain a MarketCap column")
        st.stop()

    tickers_info = filter_market_cap(tickers_info, cap_choice)
    tickers = tickers_info["Ticker"].dropna().unique().tolist()

    if not tickers:
        st.warning("No tickers match selection")
        st.stop()

    st.markdown("### Step 2: Downloading & Computing (Parallelized)")

    today = datetime.today().date()
    results = {}
    progress = st.progress(0)

    # --------------------------------------------------
    # Parallel download + caching
    # --------------------------------------------------
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(load_full_history, ticker, today): ticker
            for ticker in tickers
        }

        for i, future in enumerate(as_completed(futures)):
            ticker = futures[future]
            df_all = future.result()

            if df_all.empty:
                continue

            current_price = df_all.iloc[-1]["Close"]
            row = {"Ticker": ticker, "Current": round(current_price, 2)}

            for lb in lookbacks_selected:
                cutoff = lookback_options[lb]
                df_recent = df_all[df_all["Date"] >= cutoff]

                if df_recent.empty:
                    row[f"Drop % ({lb})"] = None
                else:
                    high = df_recent["Close"].max()
                    row[f"Drop % ({lb})"] = round(
                        (current_price - high) / high * 100, 2
                    )

            results[ticker] = (row, df_all)
            progress.progress((i + 1) / len(tickers))

    # --------------------------------------------------
    # Results table
    # --------------------------------------------------
    if results:
        df_results = pd.DataFrame([v[0] for v in results.values()])
        st.markdown("### Step 3: Results")
        st.dataframe(df_results, use_container_width=True)

        # --------------------------------------------------
        # ZIP DOWNLOAD FROM CACHED DATA
        # --------------------------------------------------
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for ticker, (_, df_hist) in results.items():
                csv_bytes = df_hist.to_csv(index=False).encode("utf-8")
                zipf.writestr(f"{ticker}.csv", csv_bytes)

        zip_buffer.seek(0)
        st.download_button(
            "📦 Download Cached Historical Data (ZIP)",
            data=zip_buffer,
            file_name="cached_stock_data.zip",
            mime="application/zip"
        )

    else:
        st.info("No data available")
