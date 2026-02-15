import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz

# Page configuration
st.set_page_config(page_title="Pro Terminal | Live Impact", page_icon="⚡", layout="wide")

# --- TICKERS ---
GLOBAL_TICKERS = {"S&P 500": "ES=F", "Nasdaq": "NQ=F", "VIX": "^VIX", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"}
SECTOR_TICKERS = {"Tech (XLK)": "XLK", "Finance (XLF)": "XLF", "Energy (XLE)": "XLE", "Semis (SMH)": "SMH"}
ETF_TICKERS = {"Bitcoin (IBIT)": "IBIT", "Gold (GLD)": "GLD", "Bonds (TLT)": "TLT"}
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS}

def analyze_sentiment(text):
    if not text: return "⚖️ Neutral"
    text = text.lower()
    if any(word in text for word in ['surge', 'rally', 'gain', 'up', 'beat']): return "🐂 Bullish"
    if any(word in text for word in ['plunge', 'drop', 'fall', 'down', 'miss']): return "🐻 Bearish"
    return "⚖️ Neutral"

@st.cache_data(ttl=30)
def fetch_market_data():
    rows = []
    for label, ticker in ALL_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            # Use 5d to ensure we get a valid previous close
            h = t.history(period="5d", interval="1d")
            if len(h) >= 2:
                prev_close = h["Close"].iloc[-2]
                curr_price = t.fast_info.last_price
                change = ((curr_price - prev_close) / prev_close) * 100
                rows.append({"Asset": label, "Symbol": ticker, "Prev Close": prev_close, "Price": curr_price, "Change %": change})
        except: continue
    return pd.DataFrame(rows)

def color_pct(val):
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

# --- UI LOGIC ---
st.sidebar.title("⚡ Settings")
refresh = st.sidebar.number_input("Refresh (sec)", 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="refresh")

data = fetch_market_data()

# NEWS SIDEBAR
st.sidebar.subheader("🎯 Live News")
top_3 = data.sort_values("Change %", ascending=False).head(3)
for _, row in top_3.iterrows():
    with st.sidebar.expander(f"{row['Asset']} News"):
        news = yf.Ticker(row['Symbol']).news
        if news:
            for n in news[:3]:
                title = n.get('title', 'No Title')
                st.write(f"**{analyze_sentiment(title)}**")
                st.markdown(f"[{title}]({n.get('link', '#')})")
                st.caption(f"Source: {n.get('publisher', 'Unknown')}")
        else: st.write("No news found.")

# MAIN PANEL
st.title("🏛️ Market Impact Terminal")
m1, m2, m3 = st.columns(3)
with m1: st.metric("Top Gainer", top_3.iloc[0]['Asset'], f"{top_3.iloc[0]['Change %']:.2f}%")
with m2: st.metric("Total Assets", len(data), f"{len(data[data['Change %']>0])} Up")
with m3: 
    vix = data[data['Symbol']=='^VIX']['Price'].values[0] if '^VIX' in data['Symbol'].values else 0
    st.metric("VIX Index", f"{vix:.2f}")

t1, t2, t3 = st.tabs(["🌎 Prices", "📊 Strength", "📈 Charts"])

with t1:
    # PREVENT KEYERROR: Create a clean display DF and ensure column exists
    df_display = data[['Asset', 'Prev Close', 'Price', 'Change %']].copy()
    st.dataframe(
        df_display.style.format({'Prev Close': '{:.2f}', 'Price': '{:.2f}', 'Change %': '{:+.2f}%'})
        .map(color_pct, subset=['Change %']),
        use_container_width=True, hide_index=True
    )

with t2:
    spy_val = data[data['Asset']=="S&P 500"]['Change %'].values[0] if "S&P 500" in data['Asset'].values else 0
    data['RS'] = data['Change %'] - spy_val
    st.bar_chart(data.sort_values('RS'), x="Asset", y="RS")

with t3:
    sel = st.multiselect("Pick Charts", list(ALL_TICKERS.keys()), default=["S&P 500"])
    for s in sel:
        chart_data = yf.Ticker(ALL_TICKERS[s]).history(period="1d", interval="5m")
        if not chart_data.empty:
            st.write(f"**{s}**")
            st.line_chart(chart_data['Close'])
