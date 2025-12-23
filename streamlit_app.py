import streamlit as st
import pandas as pd
import yfinance as yf
import os
import io
import zipfile
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pytz
import pandas_market_calendars as mcal

# --------------------------------------------------
# App config
# --------------------------------------------------
st.set_page_config(page_title="Stock Drop Tracker", layout="wide")
st.title("📉 Stock Drop Tracker!")

DATA_FOLDER = "Stock_data"
EXCEL_FILE = "Tickers_Info.xlsx"

# --------------------------------------------------
# Cached historical loader (PER TICKER)
# --------------------------------------------------
@st.cache_data(show_spinner=False)
def load_full_history(ticker: str, today: datetime.date, market) -> pd.DataFrame:
    """
    Load full historical data for a ticker. Cached per ticker to prevent re-downloading on UI changes.
    """

    csv_path = os.path.join(DATA_FOLDER, market, f"{ticker}.csv")

    # --- Case 1: No CSV → full download ---
    if not os.path.exists(csv_path):
        start_date = datetime(2010, 1, 1).date()  # datetime.today() - relativedelta(years=2)

        status_text.text(f"Data file does not exist! Downloading {ticker} from Jan 1, 2010 ...") # ({i}/{len(tickers)})
        df = yf.download(ticker, start=start_date, end=today + timedelta(days=1),  progress=False)

        if df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df.columns = df.columns.get_level_values(0)
        df.columns = ["Date", "Close", "High", "Low", "Open", "Volume"]
        return df

    # --- Case 2: CSV exists → incremental update ---
    df_old = pd.read_csv(csv_path, parse_dates=["Date"])
    # df_old = df_old[df_old["Date"] <= pd.Timestamp("2025-11-01")]

    last_date = df_old["Date"].iloc[-1]  # datetime(2025, 11, 2).date()
    status_text.text(f"{ticker} data exists! Downloading the last unavailable few days ...") # ({i}/{len(tickers)})
    df_new = yf.download(ticker, start=last_date, end=today + timedelta(days=1), progress=False)

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
    elif cap_choice == "Large-cap ($10B–$200B)":
        return df[(df["MarketCap"] >= 10) & (df["MarketCap"] <= 200)]
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

# ---------------- Check if the market is Open ----------------
# ET = ZoneInfo("America/New_York")  # Eastern Time
# now_et = datetime.now(ET)
ET = pytz.timezone("US/Eastern")
now_et = datetime.now(ET)

def is_market_open(exchange: str) -> bool:
    cal = mcal.get_calendar(exchange)

    schedule = cal.schedule(
        start_date=now_et.date(),
        end_date=now_et.date() )

    if schedule.empty:
        return False

    open_time = schedule.iloc[0]["market_open"].tz_convert(ET)
    close_time = schedule.iloc[0]["market_close"].tz_convert(ET)

    return open_time <= now_et <= close_time

# ---- CHECK ----
if market_choice in ['US', 'QQQ', 'NYSE', 'SPY']:
    exchange = 'NYSE'
elif market_choice in ['Canada', 'TSX']:
    exchange = "TSX"
    
market_is_open =  is_market_open(exchange)
# print("NYSE open:", is_market_open("NYSE"))

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
    "1 Year": datetime.today() - relativedelta(years=1),
    "2 Years": datetime.today() - relativedelta(years=2)

}

lookbacks_selected = st.multiselect(
    "Lookback Periods",
    list(lookback_options.keys()),
    default=["1 Month", "6 Months", "1 Year", "2 Years"]
)

# --------------------------------------------------
# Run analysis
# --------------------------------------------------
if st.button("🚀 Run Stock Drop Analysis"):

    # --- Load tickers ---
    try:
        tickers_info = pd.read_excel(EXCEL_FILE, sheet_name=market_choice)
    except Exception as e:
        st.error(f"Excel error: {e}")
        st.stop()

    if "MarketCap" not in tickers_info.columns:
        st.error("Excel must contain a 'MarketCap' column")
        st.stop()

    tickers_info = filter_market_cap(tickers_info, cap_choice).reset_index(drop=True)
    # def logo_url(domain):
    #     if pd.isna(domain):
    #         return None
    #     return f"https://img.logo.dev/{domain}?token={st.secrets['LOGO_DEV_API_KEY']}"

    # tickers_info["Logo"] = tickers_info["Domain"].apply(logo_url)

    tickers = tickers_info["Ticker"].dropna().unique().tolist()[:5]
    # tickers = ['RY.to', 'AC.to']
    print(tickers[::4])
    
    if not tickers:
        st.warning("No tickers match selection")
        st.stop()

    st.markdown("### Step 2: Loading Cached Data")

    today = datetime.today().date()
    results = []
    cached_histories = {}

    progress = st.progress(0)
    status_text = st.empty()

    # --------------------------------------------------
    # Sequential (cached) loading
    # --------------------------------------------------
    for i, ticker in enumerate(tickers, start=1):
        # try:
        #     tk = yf.Ticker(ticker)
        #     fi = tk.fast_info
        #     price = fi.get("last_price") or fi.get("last_close")
        #     shares = fi.get("shares_outstanding")
        #     st.write(160, ticker, price, shares)

        #     if price is None or shares is None:
        #         print(f"Missing data for {ticker}")
        #         mcap = 0
        #     else:
        #         mcap = price * shares  # already CAD for .TO tickers
        #     st.write(ticker, mcap)
            
        # except Exception as e:
        #     st.error(f"tk.fast_info does not exist {e}")

        df_all = load_full_history(ticker, today, market_choice)

        if df_all.empty:
            continue

        current_price = df_all.iloc[-1]["Close"]
        mcap_ticker = tickers_info['MarketCap'].iloc[i] 
        # logo = tickers_info.loc[tickers_info["Ticker"] == ticker, "Logo"].values[0]
        # row = {"Logo": logo, "Ticker": ticker, "Current": round(current_price, 2)}
        row = {"Ticker": ticker, "MarketCap": mcap_ticker, "Current": round(current_price, 2)}

        for lb in lookbacks_selected:
            cutoff = lookback_options[lb]
            df_recent = df_all[df_all["Date"] >= cutoff]

            if df_recent.empty:
                row[f"% Drop ({lb})"] = None
            else:
                high = df_recent["Close"].max()
                row[f"% Drop ({lb})"] = round((current_price - high) / high * 100, 2)

        results.append(row)
        cached_histories[ticker] = df_all

        progress.progress(i / len(tickers))

    # --------------------------------------------------
    # Results
    # --------------------------------------------------
    if results:
        df_results = pd.DataFrame(results)

        st.markdown("### Step 3: Results")
        st.dataframe(df_results, use_container_width=True)
        # st.dataframe(df_results,
        #              column_config={"Logo": st.column_config.ImageColumn("Logo", width="small") },
        #              use_container_width=True)

        # --------------------------------------------------
        # ZIP DOWNLOAD FROM CACHED DATA
        # --------------------------------------------------
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for ticker, df_hist in cached_histories.items():
                zipf.writestr(
                    f"{ticker}.csv",
                    df_hist.to_csv(index=False).encode("utf-8")
                )

        zip_buffer.seek(0)
        st.download_button(
            "📦 Download Cached Historical Data (ZIP)",
            data=zip_buffer,
            file_name="cached_stock_data.zip",
            mime="application/zip"
        )

    else:
        st.info("No data available.")
