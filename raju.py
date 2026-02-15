import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz

# Page configuration
st.set_page_config(page_title="Pro Market Terminal", page_icon="🏛️", layout="wide")

# --- TICKER CONFIGURATIONS ---
GLOBAL_TICKERS = {
    "S&P 500 Futures (ES)": "ES=F",
    "Nasdaq 100 Futures (NQ)": "NQ=F",
    "Dow Jones Futures (YM)": "YM=F",
    "VIX": "^VIX",
    "10Y Yield (^TNX)": "^TNX",
    "DXY (US Dollar)": "DX-Y.NYB"
}

SECTOR_TICKERS = {
    "Technology (XLK)": "XLK",
    "Financials (XLF)": "XLF",
    "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV",
    "Consumer Disc (XLY)": "XLY",
    "Industrials (XLI)": "XLI",
    "Utilities (XLU)": "XLU",
    "Real Estate (XLRE)": "XLRE",
    "Consumer Staples (XLP)": "XLP",
    "Materials (XLB)": "XLB"
}

ETF_TICKERS = {
    "Bitcoin (IBIT)": "IBIT",
    "Gold (GLD)": "GLD",
    "Silver (SLV)": "SLV",
    "Bonds 20Y+ (TLT)": "TLT",
    "Semis (SMH)": "SMH",
    "Ark Innovation (ARKK)": "ARKK"
}

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS}

# --- ANALYTICS FUNCTIONS ---
def analyze_sentiment(text):
    """Simple keyword-based sentiment analyzer for headlines"""
    if not text or not isinstance(text, str):
        return "⚖️ Neutral"
        
    bullish_words = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'growth', 'bull', 'high', 'positive', 'win', 'beat', 'boost']
    bearish_words = ['fall', 'down', 'drop', 'slump', 'plunge', 'bear', 'low', 'negative', 'loss', 'crash', 'dip', 'cut', 'sink']
    
    text = text.lower()
    bull_score = sum(1 for word in bullish_words if word in text)
    bear_score = sum(1 for word in bearish_words if word in text)
    
    if bull_score > bear_score: return "🐂 Bullish"
    if bear_score > bull_score: return "🐻 Bearish"
    return "⚖️ Neutral"

@st.cache_data(ttl=30)
def fetch_market_data(ticker_dict):
    rows = []
    for label, ticker in ticker_dict.items():
        try:
            t = yf.Ticker(ticker)
            hist_daily = t.history(period="5d", interval="1d")
            hist_int = t.history(period="1d", interval="5m")
            
            if not hist_int.empty:
                last = hist_int["Close"].iloc[-1]
                prev = hist_daily["Close"].iloc[-2] if len(hist_daily) > 1 else last
                pct = (last - prev) / prev * 100
                rows.append({"Asset": label, "Symbol": ticker, "Price": last, "Change %": pct})
            else:
                rows.append({"Asset": label, "Symbol": ticker, "Price": t.fast_info.last_price, "Change %": 0.0})
        except:
            rows.append({"Asset": label, "Symbol": ticker, "Price": np.nan, "Change %": np.nan})
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def get_ticker_news(ticker_symbol):
    try:
        return yf.Ticker(ticker_symbol).news[:3]
    except:
        return []

def color_pct(val):
    if pd.isna(val): return ''
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

# --- APP LOGIC ---
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

# Fetch data
global_df = fetch_market_data(GLOBAL_TICKERS)
sector_df = fetch_market_data(SECTOR_TICKERS)
etf_df = fetch_market_data(ETF_TICKERS)

full_market = pd.concat([global_df, sector_df, etf_df]).dropna(subset=['Change %'])
top_gainers = full_market.sort_values('Change %', ascending=False).head(3)

# --- SIDEBAR (Settings & News) ---
st.sidebar.title("🏛️ Market Settings")
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="datarefresh")

st.sidebar.divider()
st.sidebar.subheader("📰 Leader News & Sentiment")

for _, row in top_gainers.iterrows():
    with st.sidebar.expander(f"{row['Asset']} ({row['Change %']:+.2f}%)"):
        news_items = get_ticker_news(row['Symbol'])
        if news_items:
            for item in news_items:
                # SAFE EXTRACTION
                title = item.get('title', 'No Title Available')
                link = item.get('link', '#')
                publisher = item.get('publisher', 'Unknown Source')
                
                sentiment = analyze_sentiment(title)
                st.markdown(f"**{sentiment}**")
                st.markdown(f"[{title}]({link})")
                st.caption(f"Source: {publisher}")
                st.divider()
        else:
            st.write("No recent headlines found.")

# --- MAIN CONTENT ---
st.title("🏛️ Pro Market Terminal")
st.caption(f"Status: Live | EST Time: {time_now} | Auto-Refresh: {refresh}s")

# SCANNER SECTION
st.subheader("🔍 Market Scanner")
col_g, col_l, col_b = st.columns([2, 2, 1])

top_losers = full_market.sort_values('Change %', ascending=True).head(3)

with col_g:
    st.write("**Top 3 Leaders 🚀**")
    for _, row in top_gainers.iterrows():
        st.write(f"🟢 {row['Asset']}: `{row['Change %']:+.2f}%`")

with col_l:
    st.write("**Top 3 Laggards 📉**")
    for _, row in top_losers.iterrows():
        st.write(f"🔴 {row['Asset']}: `{row['Change %']:+.2f}%`")

with col_b:
    st.write("**Breadth**")
    up_count = len(full_market[full_market['Change %'] > 0])
    down_count = len(full_market[full_market['Change %'] < 0])
    st.metric("Up vs Down", f"{up_count} / {down_count}", delta=f"{up_count-down_count}")

st.divider()

# TABS
tab1, tab2, tab3 = st.tabs(["🌎 Global Indices", "Sector & ETFs", "📊 Relative Strength & Charts"])

with tab1:
    st.subheader("Major Markets")
    st.dataframe(
        global_df.drop(columns=['Symbol']).style.format({"Price": "{:.2f}", "Change %": "{:+.2f}%"}).map(color_pct, subset=["Change %"]),
        use_container_width=True, hide_index=True
    )

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Sectors (SPDR)")
        st.dataframe(
            sector_df.drop(columns=['Symbol']).style.format({"Price": "{:.2f}", "Change %": "{:+.2f}%"}).map(color_pct, subset=["Change %"]),
            use_container_width=True, hide_index=True
        )
    with c2:
        st.subheader("Key ETFs")
        st.dataframe(
            etf_df.drop(columns=['Symbol']).style.format({"Price": "{:.2f}", "Change %": "{:+.2f}%"}).map(color_pct, subset=["Change %"]),
            use_container_width=True, hide_index=True
        )

with tab3:
    st.subheader("Relative Strength (vs. S&P 500)")
    spy_change = global_df[global_df['Asset'] == "S&P 500 Futures (ES)"]['Change %'].values[0]
    sector_df['RS'] = sector_df['Change %'] - spy_change
    rs_sorted = sector_df.sort_values('RS', ascending=True)
    
    st.bar_chart(data=rs_sorted, x="Asset", y="RS", color="RS", use_container_width=True)
    
    st.divider()
    st.subheader("Intraday Charts (EST)")
    selected = st.multiselect('Select Asset to View', list(ALL_TICKERS.keys()), default=["S&P 500 Futures (ES)"])
    for label in selected:
        ticker = ALL_TICKERS[label]
        data = yf.Ticker(ticker).history(period='1d', interval='5m')
        if not data.empty:
            data.index = data.index.tz_convert('US/Eastern')
            st.write(f"**{label}**")
            st.line_chart(data['Close'], use_container_width=True)
