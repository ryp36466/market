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
GLOBAL_TICKERS = {"S&P 500": "ES=F", "Nasdaq": "NQ=F", "VIX": "^VIX", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"}
SECTOR_TICKERS = {
    "Technology (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV", "Consumer Disc (XLY)": "XLY", "Semis (SMH)": "SMH",
    "Utilities (XLU)": "XLU", "Real Estate (XLRE)": "XLRE"
}
ETF_TICKERS = {"Bitcoin (IBIT)": "IBIT", "Gold (GLD)": "GLD", "Silver (SLV)": "SLV", "Bonds (TLT)": "TLT"}

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS}

# --- ANALYTICS ---
def analyze_sentiment(text):
    if not text or not isinstance(text, str): return "⚖️ Neutral"
    text = text.lower()
    bullish = ['surge', 'rally', 'beat', 'growth', 'buy', 'upgrade', 'high', 'jump', 'gain']
    bearish = ['plunge', 'drop', 'miss', 'cut', 'fall', 'sell', 'downgrade', 'sink', 'loss']
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
            # Fetch 5 days to ensure we have a solid 'Yesterday' close regardless of weekends
            hist = t.history(period="5d", interval="1d")
            
            if len(hist) >= 2:
                last_close = hist["Close"].iloc[-2] # The actual yesterday/prev session close
                current_price = t.fast_info.last_price
                pct_change = ((current_price - last_close) / last_close) * 100
                
                rows.append({
                    "Asset": label, 
                    "Symbol": ticker, 
                    "Last Close": last_close, 
                    "Current Price": current_price, 
                    "Change %": pct_change
                })
        except: continue
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def get_impact_news(ticker_symbol):
    try:
        news = yf.Ticker(ticker_symbol).news[:5]
        if ticker_symbol in IMPACT_MAP:
            for stock in IMPACT_MAP[ticker_symbol]:
                news += yf.Ticker(stock).news[:2]
        return news
    except: return []

def color_pct(val):
    if pd.isna(val): return ''
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

# --- APP LAYOUT ---
st.sidebar.title("⚡ Impact Terminal")
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="datarefresh")

# Fetch data
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
                impact_badge = "⚠️ IMPACT" if any(s in title.upper() for s in IMPACT_MAP.get(row['Symbol'], [])) else ""
                st.markdown(f"**{sentiment}** {impact_badge}")
                st.markdown(f"[{title}]({art.get('link','#')})")
                st.caption(f"Source: {art.get('publisher','Unknown')}")
                st.divider()

# MAIN CONTENT
st.title("🏛️ Market Impact Terminal")
est = pytz.timezone('US/Eastern')
st.caption(f"Live EST: {datetime.datetime.now(est).strftime('%H:%M:%S')} | Refresh: {refresh}s")

# SCANNER METRICS
m1, m2, m3 = st.columns(3)
with m1: st.metric("Top Leader", top_3.iloc[0]['Asset'], f"{top_3.iloc[0]['Change %']:.2f}%")
with m2: 
    up = len(full_market[full_market['Change %']>0])
    down = len(full_market[full_market['Change %']<0])
    st.metric("Breadth (Up/Down)", f"{up} / {down}", delta=f"{up-down}")
with m3:
    vix_row = full_market[full_market['Symbol']=='^VIX']
    if not vix_row.empty:
        st.metric("VIX (Fear Index)", f"{vix_row['Current Price'].values[0]:.2f}", f"{vix_row['Change %'].values[0]:.2f}%", delta_color="inverse")

st.divider()

# TABS
t1, t2, t3 = st.tabs(["🌎 Markets & Prices", "📊 Relative Strength", "📈 Intraday Charts"])

with t1:
    st.subheader("Yesterday vs. Today")
    display_cols = ['Asset', 'Last Close', 'Current Price', 'Change %']
    st.dataframe(
        full_market[display_cols].style.format({
            'Last Close': '{:.2f}', 
            'Current Price': '{:.2f}', 
            'Change %': '{:+.2f}%'
        }).map(color_pct, subset=["Change %"]), 
        use_container_width=True, hide_index=True
    )

with t2:
    st.subheader("Sector RS (vs S&P 500)")
    spy_pct = global_df[global_df['Asset']=="S&P 500"]['Change %'].values[0]
    sector_df['RS'] = sector_df['Change %'] - spy_pct
    st.bar_chart(sector_df.sort_values('RS'), x="Asset", y="RS", color="RS")

with t3:
    selected = st.multiselect('View Charts', list(ALL_TICKERS.keys()), default=["S&P 500"])
    for label in selected:
        ticker = ALL_TICKERS[label]
        data = yf.Ticker(ticker).history(period='1d', interval='5m')
        if not data.empty:
            st.write(f"**{label}**")
            st.line_chart(data['Close'])
