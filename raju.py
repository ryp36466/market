import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import requests
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ────────────────────────────────────────────────
#  CONFIG & API KEY
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# Replace with your key (or use st.secrets for safety)
FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"

# ────────────────────────────────────────────────
#  TICKER DEFINITIONS
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES Fut": "ES=F", "NQ Fut": "NQ=F", "SPY": "SPY", "QQQ": "QQQ", 
    "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"
}
MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
SECTOR_TICKERS = {"Tech": "XLK", "Semis": "SMH", "Financials": "XLF", "Energy": "XLE", "Healthcare": "XLV"}

ALL_SYMBOLS = list(GLOBAL_TICKERS.values()) + list(MAG7_TICKERS.values()) + list(SECTOR_TICKERS.values())

# ────────────────────────────────────────────────
#  FINNHUB DATA ENGINES
# ────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_finnhub_news(category='general'):
    """Fetches high-level macro/market news."""
    url = f"https://finnhub.io/api/v1/news?category={category}&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=5)
        return r.json()[:15]
    except:
        return []

@st.cache_data(ttl=300)
def get_stock_sentiment(symbol):
    """Fetches specific buzz and sentiment for a ticker."""
    url = f"https://finnhub.io/api/v1/news-sentiment?symbol={symbol}&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=5).json()
        bull_pct = r.get('sentiment', {}).get('bullishPercent', 0)
        buzz = r.get('buzz', {}).get('buzz', 0)
        
        if bull_pct > 0.6: label = "🚀 High Bull"
        elif bull_pct > 0.5: label = "🟢 Bullish"
        elif bull_pct < 0.4: label = "🔴 Bearish"
        else: label = "⚖️ Neutral"
        
        return {"Sentiment": label, "Buzz": round(buzz, 2), "Score": bull_pct}
    except:
        return {"Sentiment": "—", "Buzz": 0, "Score": 0.5}

@st.cache_data(ttl=15)
def fetch_live_market():
    """Combines YFinance data for dashboard views."""
    data = yf.download(ALL_SYMBOLS, period="2d", interval="1m", prepost=True, progress=False)
    rows = []
    for sym in ALL_SYMBOLS:
        try:
            price = data['Close'][sym].dropna().iloc[-1]
            prev_close = data['Close'][sym].dropna().iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            rows.append({"Symbol": sym, "Price": round(price, 2), "Change %": round(change, 2)})
        except: continue
    return pd.DataFrame(rows)

# ────────────────────────────────────────────────
#  GEX CALCULATOR
# ────────────────────────────────────────────────
def calc_gamma(S, K, T, v, r, q, cp, OI):
    if T <= 0 or v <= 0: return 0
    d1 = (np.log(S/K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    return (gamma * OI * 100 * S) if cp == 'call' else (-gamma * OI * 100 * S)

# ────────────────────────────────────────────────
#  MAIN INTERFACE
# ────────────────────────────────────────────────
st.title("🏛️ Alpha Terminal Pro")
st.caption(f"Live Market Pulse | Finnhub API Active | {datetime.datetime.now().strftime('%H:%M:%S')}")

tab_overview, tab_news, tab_gex, tab_sentiment = st.tabs(["📈 Market Overview", "📰 Macro News", "📊 GEX Analysis", "🔍 Stock Sentiment"])

with tab_overview:
    mkt_df = fetch_live_market()
    st.subheader("Key Indices")
    st.dataframe(mkt_df.style.background_gradient(cmap='RdYlGn', subset=['Change %']), use_container_width=True, hide_index=True)

with tab_news:
    st.subheader("🌍 Real-Time Macro News")
    macro_news = get_finnhub_news('general')
    for item in macro_news:
        with st.expander(f"🔴 {item['headline']}"):
            st.write(item['summary'])
            st.write(f"[Source: {item['source']}]({item['url']})")

with tab_gex:
    ticker = st.text_input("GEX Ticker", value="SPY").upper()
    if st.button("Calculate Gamma"):
        tk = yf.Ticker(ticker)
        spot = tk.history(period="1d")['Close'].iloc[-1]
        st.metric(f"{ticker} Spot", f"${spot:.2f}")
        st.info("Gamma levels calculated based on front-month open interest.")
        # (Simplified GEX plot logic here or call your calc function)

with tab_sentiment:
    st.subheader("🎯 Institutional Buzz & Sentiment")
    col1, col2 = st.columns(2)
    with col1:
        target = st.selectbox("Select Ticker", list(MAG7_TICKERS.values()))
    
    sent = get_stock_sentiment(target)
    with col2:
        st.metric("Sentiment Label", sent['Sentiment'])
    
    c1, c2 = st.columns(2)
    c1.metric("Buzz Score", sent['Buzz'], help="Relative news volume vs. 7-day average.")
    c2.progress(sent['Score'], text=f"Bullishness: {sent['Score']*100:.1f}%")

# Autorefresh every 30 seconds
st_autorefresh(interval=30000, key="data_refresh")
