import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz

# Page configuration
st.set_page_config(page_title="Pro Terminal | Live Impact", page_icon="⚡", layout="wide")

# --- SECTOR IMPACT MAPPING ---
# This maps sectors to the "Impact Stocks" that move them
IMPACT_MAP = {
    "XLK": ["AAPL", "MSFT", "NVDA"],
    "XLF": ["JPM", "BAC", "GS"],
    "XLE": ["XOM", "CVX"],
    "XLV": ["LLY", "UNH", "JNJ"],
    "XLY": ["AMZN", "TSLA"],
    "IBIT": ["BTC-USD", "COIN", "MARA"],
    "SMH": ["NVDA", "TSM", "AMD"]
}

# --- TICKER CONFIGURATIONS ---
GLOBAL_TICKERS = {"S&P 500": "ES=F", "Nasdaq": "NQ=F", "VIX": "^VIX", "10Y Yield": "^TNX"}
SECTOR_TICKERS = {
    "Technology (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV", "Consumer Disc (XLY)": "XLY", "Semis (SMH)": "SMH"
}
ETF_TICKERS = {"Bitcoin (IBIT)": "IBIT", "Gold (GLD)": "GLD", "Bonds (TLT)": "TLT"}

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS}

# --- ANALYTICS ---
def analyze_sentiment(text):
    if not text or not isinstance(text, str): return "⚖️ Neutral"
    text = text.lower()
    bullish = ['surge', 'rally', 'beat', 'growth', 'buy', 'upgrade', 'high', 'jump']
    bearish = ['plunge', 'drop', 'miss', 'cut', 'fall', 'sell', 'downgrade', 'sink']
    b_score = sum(1 for w in bullish if w in text)
    s_score = sum(1 for w in bearish if w in text)
    if b_score > s_score: return "🐂 Bullish"
    if s_score > b_score: return "🐻 Bearish"
    return "⚖️ Neutral"

@st.cache_data(ttl=30)
def fetch_market_data(ticker_dict):
    rows = []
    for label, ticker in ticker_dict.items():
        try:
            t = yf.Ticker(ticker)
            h = t.history(period="1d", interval="5m")
            if not h.empty:
                last = h["Close"].iloc[-1]
                prev = t.history(period="2d")["Close"].iloc[-2]
                pct = (last - prev) / prev * 100
                rows.append({"Asset": label, "Symbol": ticker, "Price": last, "Change %": pct})
        except: continue
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def get_impact_news(ticker_symbol):
    try:
        # Get primary ticker news
        news = yf.Ticker(ticker_symbol).news[:5]
        # Also check impact stocks if this is a sector
        if ticker_symbol in IMPACT_MAP:
            for stock in IMPACT_MAP[ticker_symbol]:
                news += yf.Ticker(stock).news[:2]
        return news
    except: return []

# --- APP LAYOUT ---
st.sidebar.title("⚡ Impact Terminal")
st_autorefresh(interval=30000, key="datarefresh")

global_df = fetch_market_data(GLOBAL_TICKERS)
sector_df = fetch_market_data(SECTOR_TICKERS)
etf_df = fetch_market_data(ETF_TICKERS)

full_market = pd.concat([global_df, sector_df, etf_df]).dropna()
top_3 = full_market.sort_values('Change %', ascending=False).head(3)

# LIVE IMPACT SIDEBAR
st.sidebar.subheader("🎯 Stock-Level Impact")
for _, row in top_3.iterrows():
    with st.sidebar.expander(f"NEWS: {row['Asset']}", expanded=True):
        articles = get_impact_news(row['Symbol'])
        if articles:
            for art in articles:
                title = art.get('title', 'N/A')
                sentiment = analyze_sentiment(title)
                # Check if specific stock impact is mentioned
                impact_badge = "⚠️ IMPACT" if any(s in title.upper() for s in IMPACT_MAP.get(row['Symbol'], [])) else ""
                
                st.markdown(f"**{sentiment}** {impact_badge}")
                st.markdown(f"[{title}]({art.get('link','#')})")
                st.caption(f"Source: {art.get('publisher','Unknown')}")
                st.divider()

# MAIN DASHBOARD
st.title("🏛️ Market Impact Terminal")
col1, col2, col3 = st.columns(3)
with col1: st.metric("Top Mover", top_3.iloc[0]['Asset'], f"{top_3.iloc[0]['Change %']:.2f}%")
with col2: st.metric("Breadth", f"{len(full_market[full_market['Change %']>0])} UP", f"{len(full_market[full_market['Change %']<0])} DOWN")
with col3: 
    vix = full_market[full_market['Symbol']=='^VIX']['Price'].values[0]
    st.metric("VIX (Fear)", f"{vix:.2f}", f"{full_market[full_market['Symbol']=='^VIX']['Change %'].values[0]:.2f}%", delta_color="inverse")

# TABS
t1, t2, t3 = st.tabs(["🌎 Markets", "📊 RS Analysis", "📈 Charts"])
with t1:
    st.dataframe(full_market[['Asset', 'Price', 'Change %']].style.format({'Price': '{:.2f}', 'Change %': '{:+.2f}%'}), use_container_width=True)
with t2:
    spy_pct = full_market[full_market['Asset']=="S&P 500"]['Change %'].values[0]
    sector_df['RS'] = sector_df['Change %'] - spy_pct
    st.bar_chart(sector_df.sort_values('RS'), x="Asset", y="RS", color="RS")
