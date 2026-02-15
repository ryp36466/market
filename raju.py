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
            # Get Intraday data for the latest price
            hist_intraday = t.history(period="1d", interval="5m")
            # Get Daily data for the previous close
            hist_daily = t.history(period="5d", interval="1d")
            
            if not hist_intraday.empty and len(hist_daily) >= 2:
                last = hist_intraday["Close"].iloc[-1]
                prev = hist_daily["Close"].iloc[-2] # Previous market close
                pct = (last - prev) / prev * 100
                rows.append([label, last, pct])
            else:
                rows.append([label, np.nan, np.nan])
        except Exception:
            rows.append([label, np.nan, np.nan])
            
    return pd.DataFrame(rows, columns=["Index", "Last Price", "% Change"])

def market_score(df):
    score = 0
    try:
        # Get values safely using the exact labels in TICKERS
        nasdaq = df.loc[df["Index"] == "Nasdaq 100 (QQQ)", "% Change"].values[0]
        spx = df.loc[df["Index"] == "S&P 500 (SPY)", "% Change"].values[0]
        vix = df.loc[df["Index"] == "VIX", "% Change"].values[0]
        dxy = df.loc[df["Index"] == "DXY", "% Change"].values[0]
        y10 = df.loc[df["Index"] == "10Y Yield (^TNX)", "% Change"].values[0]

        # Stocks UP = Risk On (+1)
        if not np.isnan(nasdaq) and nasdaq > 0: score += 1
        if not np.isnan(spx) and spx > 0: score += 1
        
        # VIX DOWN = Risk On (+1)
        if not np.isnan(vix) and vix < 0: score += 1
        
        # DXY DOWN = Risk On (+1)
        if not np.isnan(dxy) and dxy < 0: score += 1
        
        # Yields DOWN = Risk On (+1)
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
    selected = st.multiselect('Select indices to chart', df['Index'].tolist(), default=['S&P 500 (SPY)', 'Nasdaq 100 (QQQ)'])

    for label in selected:
        ticker = TICKERS[label]
        # Fetch intraday data for charts
        data = yf.Ticker(ticker).history(period='1d', interval='5m')
        
        if not data.empty:
            st.write(f"**{label}**")
            st.line_chart(data['Close'])
        else:
            st.write(f"**{label}** — no intraday data available")

    st.caption('Tip: refresh the page or press the Streamlit refresh button to update. The app caches data briefly to reduce API calls.')

# Auto-refresh
count = st_autorefresh(interval=refresh * 1000, key="datarefresh")
