import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime

# Page configuration
st.set_page_config(page_title="Market Dashboard", page_icon="📈", layout="wide")

st.title("Market Dashboard")
st.caption(f"Updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Tickers Dictionary
TICKERS = {
    "S&P 500 Index ($SPX)": "^GSPC",
    "S&P 500 (SPY)": "SPY",
    "Nasdaq 100 (QQQ)": "QQQ",
    "Dow Jones (DIA)": "DIA",
    "Russell 2000 (IWM)": "IWM",
    "VIX": "^VIX",
    "10Y Yield (^TNX)": "^TNX",
    "DXY": "DX-Y.NYB"  # Corrected ticker for Dollar Index
}

# Fetch data (cached briefly to reduce API calls)
@st.cache_data(ttl=30)
def get_data():
    rows = []
    for label, ticker in TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            # Get 7 days of daily data to ensure we have a 'Previous Close'
            hist_daily = t.history(period="7d", interval="1d")
            # Get intraday data
            hist_intraday = t.history(period="1d", interval="5m")
            
            if not hist_intraday.empty and len(hist_daily) >= 2:
                last = hist_intraday["Close"].iloc[-1]
                prev = hist_daily["Close"].iloc[-2]
                pct = (last - prev) / prev * 100
                rows.append([label, last, pct])
            else:
                # FALLBACK: If history is empty, try to get the live price directly
                last = t.fast_info.last_price
                # If we can't get percent change, we set it to 0.0 so the app doesn't crash
                rows.append([label, last, 0.0])
        except Exception:
            rows.append([label, np.nan, np.nan])
            
    return pd.DataFrame(rows, columns=["Index", "Last Price", "% Change"])

def market_score(df):
    score = 0
    try:
        # We use a helper to find the % change for a specific index name safely
        def get_pct(name):
            val = df.loc[df["Index"] == name, "% Change"].values
            return val[0] if len(val) > 0 else np.nan

        nasdaq = get_pct("Nasdaq 100 (QQQ)")
        spx = get_pct("S&P 500 Index ($SPX)")
        spy = get_pct("S&P 500 (SPY)")
        vix = get_pct("VIX")
        dxy = get_pct("DXY")
        y10 = get_pct("10Y Yield (^TNX)")

        if not np.isnan(nasdaq) and nasdaq > 0: score += 1
        if not np.isnan(spx) and spx > 0: score += 1
        if not np.isnan(vix) and vix < 0: score += 1
        if not np.isnan(dxy) and dxy < 0: score += 1
        if not np.isnan(y10) and y10 < 0: score += 1
    except Exception:
        pass
    return score

def color_pct(val):
    if pd.isna(val): return ''
    if val > 0: return 'color: green'
    if val < 0: return 'color: red'
    return 'color: orange'

# Sidebar controls
st.sidebar.markdown('**Controls**')
refresh = st.sidebar.number_input('Auto refresh interval (seconds)', min_value=15, max_value=600, value=60, step=15)
st.sidebar.write('Choose indices to chart and set refresh interval.')



# Main App Logic
with st.spinner('Fetching market data...'):
    df = get_data()
    score = market_score(df)

    # Determine Market Condition
    if score >= 4:
        condition = '🟢 Strong Risk-On'
    elif score >= 2:
        condition = '🟡 Neutral / Mixed'
    else:
        condition = '🔴 Risk-Off / Selloff Conditions'

    st.subheader(f"Market Condition: {condition}")
    
    # Display Dataframe
    st.subheader('📈 Market Overview')
    st.dataframe(
        df.style.format({"Last Price": "{:.2f}", "% Change": "{:+.2f}%"})
        .map(color_pct, subset=["% Change"]),
        height=350,
        use_container_width=True
    )

 # Charts Section
    st.subheader('📉 Intraday Charts')
    selected = st.multiselect('Select indices to chart', TICKERS.keys(), default=['S&P 500 Index ($SPX)', 'Nasdaq 100 (QQQ)'])

    for label in selected:
        ticker = TICKERS[label]
        # Fetch 5-minute intraday data for the last day
        data = yf.Ticker(ticker).history(period='1d', interval='5m')
        
        if not data.empty:
            st.write(f"**{label}**")
            
            # This is the key: we plot the 'Close' column
            # Streamlit line_charts automatically scale to the data range
            st.line_chart(data['Close'], use_container_width=True)
        else:
            st.info(f"💡 {label}: No intraday data available right now (Market might be closed).")
# Auto-refresh
count = st_autorefresh(interval=refresh * 1000, key="datarefresh")
