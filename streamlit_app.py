import streamlit as st
import pandas as pd
import yfinance as yf
import os
import io
import zipfile
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import pytz
import pandas_market_calendars as mcal
# from concurrent.futures import ThreadPoolExecutor, as_completed

# --------------------------------------------------
# 🔹 Session state initialization
# --------------------------------------------------
if "price_data" not in st.session_state:
    st.session_state.price_data = {}
    
if "last_filters" not in st.session_state:
    st.session_state.last_filters = None    
# --------------------------------------------------
# App config
# --------------------------------------------------
st.set_page_config(page_title="Stock Drop Tracker", layout="wide")
st.title("📉 Stock Drop Tracker!")

DATA_FOLDER = "Stock_data"
EXCEL_FILE = "Tickers_Info.xlsx"

# --------------------------------------------------
# Step 1: UI Layer 
# --------------------------------------------------
# st.markdown("### Step 1: Choose Market & Filters")

market_choice = st.radio("Choose Market:", ["TSX", "Nasdaq100", "S&P500"], horizontal=True)

# ---------------- Check if the market is Open ----------------
# ET = ZoneInfo("America/New_York")  # Eastern Time Python > 3.9 
ET = pytz.timezone("US/Eastern")
now_et = datetime.now(ET)

def is_market_open(exchange: str) -> bool:
    cal = mcal.get_calendar(exchange)
    schedule = cal.schedule(start_date=now_et.date(), end_date=now_et.date())
    if schedule.empty:
        return False
    open_time = schedule.iloc[0]["market_open"].tz_convert(ET)
    close_time = schedule.iloc[0]["market_close"].tz_convert(ET)
    return open_time <= now_et <= close_time

# ---- CHECK ----
# if market_choice in ['US', 'QQQ', 'NYSE', 'SPY']:
#     exchange = 'NYSE'
# elif market_choice in ['Canada', 'TSX']:
#     exchange = "TSX" 
# market_is_open =  is_market_open(exchange)
# print("NYSE open:", is_market_open("NYSE"))

cap_choice = st.selectbox(
    "Market Cap",
    [    "All",
        "Mega-cap (> $200B)",
        "Large-cap ($10B–$200B)",
        "Mid-cap ($2B–$10B)",
        "Small-cap ($300M–$2B)"    ]
)

lookback_options = {
    "1 day": datetime.today() - relativedelta(days=1),
    "1 Week": datetime.today() - relativedelta(days=7),
    "1 Month": datetime.today() - relativedelta(months=1),
    "6 Months": datetime.today() - relativedelta(months=6),
    "1 Year": datetime.today() - relativedelta(years=1),
    "2 Years": datetime.today() - relativedelta(years=2)
}

lookbacks_selected = st.multiselect(
    "Lookback Periods", 
    list(lookback_options.keys()), default=["1 Month", "1 Year", "2 Years"]
)

current_year = datetime.now().year # date.today().year
start_year = st.selectbox(
    "IF Needed: Start downloading historical data from Jan 1st of:",
    options=list(range(2000, current_year + 1)),
    index=list(range(2000, current_year + 1)).index(2024)
)
start_date = date(start_year, 1, 1)

col1, col2 = st.columns(2)
with col1:
    run = st.button("▶ Run analysis")
with col2:
    force_refresh = st.button("🔄 Force refresh data")
    
# --- Clear cached data if filters changed ---
filters = (market_choice, cap_choice, start_year)
if st.session_state.last_filters != filters:
    st.session_state.price_data.clear()
    st.session_state.last_filters = filters

# =====================================================================
# 🟦 DATA LAYER (CACHED)
# =====================================================================
# First, fetch data
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_from_yahoo(ticker, start_date, end_date):
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)

    if df.empty:
        st.warning("110: No tickers match selection")
        return None

    df = df.reset_index()
    df.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
    return df

def filter_market_cap(df, cap_choice):
    if cap_choice == "Mega-cap (> $200B)":
        # st.write("Mega cap selected")
        return df[df["MarketCap"] > 200]
    elif cap_choice == "Large-cap ($10B–$200B)":
        # st.write("Large cap selected")
        return df[(df["MarketCap"] >= 10) & (df["MarketCap"] <= 200)]
    elif cap_choice == "Mid-cap ($2B–$10B)":
        # st.write("mid cap selected")
        return df[(df["MarketCap"] >= 2) & (df["MarketCap"] < 10)]
    elif cap_choice == "Small-cap ($300M–$2B)":
        # st.write("small cap selected")
        return df[(df["MarketCap"] >= 0.3) & (df["MarketCap"] < 2)]
    # st.write("no market cap selected")
    return df

# ✅ Load or update CSV per ticker
def load_or_update_csv(ticker, start_date, end_date, force_refresh=False):
    csv_path = os.path.join(DATA_FOLDER, market_choice  ,f"{ticker}.csv")
    st.write(csv_path)

    # --- Force refresh: ignore CSV ---
    if force_refresh or not os.path.exists(csv_path):
        status_text.text(f"Downloading {ticker} from {int(start_year)} ...") # ({i}/{len(tickers)})
        df = fetch_from_yahoo(ticker, start_date, end_date)
        if df is not None:
            df.to_csv(csv_path, index=False)
        return df

    # --- Load existing CSV ---
    df_old = pd.read_csv(csv_path, parse_dates=["Date"])
    last_date = df_old["Date"].max().date()
    # --- Already up to date ---
    if last_date >= end_date - timedelta(days=2):
        status_text.text(f"{ticker} data exists and is up-to-date : )") # ({i}/{len(tickers)})
        return df_old

    # --- Download missing dates ---
    status_text.text(f"Historical data exists for {ticker}; Fetching the last few days!") # ({i}/{len(tickers)})
    df_new = fetch_from_yahoo(ticker, last_date + timedelta(days=1), end_date)

    if df_new is None:
        return df_old

    df_all = pd.concat([df_old, df_new], ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["Date"])

    # df_all.to_csv(csv_path, index=False)
    return df_all

# ====================================================================
# 🟦 COMPUTE LAYER
# ===================================================================
def compute_drops(df, lookbacks):
    current = df.iloc[-1]["Close"]
    out = {"Current": round(current, 2)}

    for name, cutoff in lookbacks.items():
        recent = df[df["Date"] >= cutoff]
        display_name = name.replace(' Year', "Yr") if " Year" in name else name
        if recent.empty:
            out[f"Drop%: {display_name}"] = None
        else:
            high = recent["Close"].max()
            out[f"Drop%: {display_name}"] = round((current - high) / high * 100, 2)

    return out

def todays_change_pct(df):
    if len(df) < 2:
        return None
    today_close = df.iloc[-1]["Close"]
    prev_close = df.iloc[-2]["Close"]
    return round((today_close - prev_close) / prev_close * 100, 2)
    
# ===============================
# ▶ RUN LOGIC
# ===============================
if run or force_refresh:

    if force_refresh:
        st.session_state.price_data.clear()
        st.cache_data.clear()

    tickers_info = pd.read_excel("Tickers_Info.xlsx", sheet_name=market_choice)
    if "MarketCap" not in tickers_info.columns:
        st.error("Excel must contain a 'MarketCap' column")
        st.stop()

    tickers_info = filter_market_cap(tickers_info, cap_choice).reset_index(drop=True)
    tickers_info["MarketCap"] = pd.to_numeric(tickers_info["MarketCap"], errors="coerce")
    
    tickers = tickers_info["Ticker"].dropna().unique().tolist()
    end_date = date.today() + timedelta(days=1)

    st.markdown("### Loading price data")

    progress = st.progress(0)
    status_text = st.empty()

    for i, ticker in enumerate(tickers, start=1):

        if ticker not in st.session_state.price_data:
            df = load_or_update_csv(ticker, start_date, end_date, force_refresh=force_refresh)

            if df is not None:
                st.session_state.price_data[ticker] = df
            else:
                st.write(f"218 {i}:{ticker}")

        progress.progress(i / len(tickers))

# ===============================
# 📊 RESULTS
# ===============================
if st.session_state.price_data:
    
    results = []

    for ticker, df in st.session_state.price_data.items():
        try:
            tk = yf.Ticker(ticker)
            fi = tk.fast_info
            mcap = round(fi.market_cap/1e9, 2)
            # st.write(231, ticker, mcap)            
        except Exception as e:
            st.warning("No tickers match selection")
            st.error(f"tk.fast_info does not exist {e}")

        row = {"Ticker": ticker, "MarketCap":mcap, "Today %": todays_change_pct(df)}
        row.update(
            compute_drops(
                df,
                {k: lookback_options [k] for k in lookbacks_selected}
            )
        )
        results.append(row)

    df_results = pd.DataFrame(results)

    st.markdown("### Results:")

    # if st.session_state.show_logos:
    #     tickers_info["Logo"] = tickers_info["Domain"].apply(
    #         lambda d: f"https://img.logo.dev/{d}?token={st.secrets['LOGO_DEV_API_KEY']}"
    #         if pd.notna(d) else None)

    #     df_results = df_results.merge(tickers_info[["Ticker", "Logo"]], on="Ticker", how="left")

    #     st.dataframe(df_results,
    #                  column_config={"Logo": st.column_config.ImageColumn("Logo", width="small")},  use_container_width=True)
    # else:
    st.dataframe(df_results, use_container_width=True)

# ===============================
# 📦 ZIP DOWNLOAD
# ===============================
download_toggle = st.radio(
    "Download cached CSV files?",
    options=["No", "Yes"],
    horizontal=True,
    index=0  # Default = No
)
if st.session_state.price_data and download_toggle == "Yes":

    st.markdown("## 📦 Download cached CSVs")

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for ticker, df in st.session_state.price_data.items():
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            zip_file.writestr(f"{ticker}.csv", csv_bytes)

    zip_buffer.seek(0)

    st.download_button(
        label="⬇ Download cached CSVs (ZIP)",
        data=zip_buffer,
        file_name=f"stock_data_{market_choice}.zip",
        mime="application/zip"
    )    
