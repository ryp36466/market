import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
import requests
from bs4 import BeautifulSoup
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm

# ========================== PAGE CONFIG ==========================
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ========================== PASSWORD PROTECTION ==========================
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    def password_entered():
        if st.session_state.get("password") == "Pratimap9!@":
            st.session_state["password_correct"] = True
            st.session_state["password"] = "" 
        else:
            st.session_state["password_correct"] = False
            st.error("😕 Access Denied")

    if not st.session_state.get("password_correct", False):
        st.title("🔐 Pro Market Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    return True

if not check_password():
    st.stop()

# ========================== TICKER CONFIGS ==========================
GLOBAL_TICKERS = {"S&P 500": "^GSPC", "Nasdaq 100": "^IXIC", "VIX": "^VIX", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"}
MAG7_TICKERS = {"Apple": "AAPL", "Microsoft": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
SECTOR_TICKERS = {"Tech": "XLK", "Finance": "XLF", "Energy": "XLE", "Health": "XLV", "Retail": "XRT"}

# ========================== CORE HELPERS ==========================
@st.cache_data(ttl=60)
def fetch_market_snapshot():
    all_syms = list(GLOBAL_TICKERS.values()) + list(MAG7_TICKERS.values()) + list(SECTOR_TICKERS.values())
    data = yf.download(all_syms, period="5d", interval="1d", progress=False)
    intra = yf.download(all_syms, period="1d", interval="5m", progress=False)
    
    if isinstance(intra.columns, pd.MultiIndex):
        intra_close = intra['Close']
    else:
        intra_close = intra[['Close']]

    res = []
    combined = {**GLOBAL_TICKERS, **MAG7_TICKERS, **SECTOR_TICKERS}
    for label, sym in combined.items():
        try:
            price = intra_close[sym].dropna().iloc[-1]
            prev = data['Close'][sym].iloc[-2]
            change = ((price - prev) / prev) * 100
            res.append({"Asset": label, "Price": round(price, 2), "Change %": round(change, 2)})
        except: continue
    return pd.DataFrame(res), intra_close

@st.cache_data(ttl=1800)
def get_mag7_earnings_enhanced():
    results = []
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    
    for label, sym in MAG7_TICKERS.items():
        try:
            tk = yf.Ticker(sym)
            # Safe calendar fetch
            cal = tk.calendar
            next_date = cal.get('Earnings Date', [None])[0].strftime('%Y-%m-%d') if cal and 'Earnings Date' in cal else "TBD"
            
            # Safe surprise fetch
            hist = tk.get_earnings_dates(limit=1)
            surprise = 0.0
            if hist is not None and not hist.empty:
                val = hist['Surprise(%)'].iloc[0]
                surprise = float(val * 100) if pd.notna(val) else 0.0
            
            results.append({
                "Asset": label,
                "Symbol": sym,
                "Next Date": next_date,
                "Surprise (%)": surprise,
                "Is Today": (next_date == today_str)
            })
        except: continue
    return pd.DataFrame(results)

# ========================== MAIN UI ==========================
market_df, intra_data = fetch_market_snapshot()
st.title("🏛️ Alpha Terminal Pro")

tabs = st.tabs(["📈 Market", "📊 GEX", "🎯 Earnings", "📰 News"])

# --- MARKET TAB ---
with tabs[0]:
    st.subheader("Live Price Action")
    st.dataframe(market_df.style.background_gradient(cmap='RdYlGn', subset=['Change %']), use_container_width=True, hide_index=True)
    if "^GSPC" in intra_data.columns:
        st.plotly_chart(px.line(intra_data["^GSPC"], title="S&P 500 Intraday", template="plotly_dark"), use_container_width=True)

# --- EARNINGS TAB (FIXED ERROR) ---
with tabs[2]:
    st.subheader("🎯 Earnings Intelligence")
    earn_df = get_mag7_earnings_enhanced()
    
    if not earn_df.empty:
        # Highlighting Today's Reporters with a subtle blue row
        def highlight_today(row):
            return ['background-color: #1e3a8a' if row['Is Today'] else '' for _ in row]

        styled = earn_df.style.apply(highlight_today, axis=1)\
                         .background_gradient(cmap='RdYlGn', subset=['Surprise (%)'])
        
        # We don't need the helper column 'Is Today' in the final display
        st.dataframe(styled, use_container_width=True, hide_index=True, column_order=("Asset", "Symbol", "Next Date", "Surprise (%)"))
    else:
        st.info("No data available.")

# --- NEWS TAB ---
with tabs[3]:
    st.subheader("📰 Market Wire")
    try:
        r = requests.get("https://finviz.com/news.ashx", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.find_all("a", class_="tab-link-news")[:10]:
            st.markdown(f"• [{link.text}]({link['href']})")
    except: st.write("Feed down.")

st_autorefresh(interval=30000, key="refresh")
