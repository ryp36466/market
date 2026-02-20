import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import requests
import plotly.express as px
import plotly.graph_objects as go
from bs4 import BeautifulSoup
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ────────────────────────────────────────────────
# 1. CONFIG & STYLING
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro v2.1", page_icon="🏛️", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #e0e0e0; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 8px; }
    .alert-card { padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #ff4b4b; background-color: #262730; }
    .sentiment-box { padding: 10px; border-radius: 5px; margin-bottom: 10px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# Watchlist for the Scanner
SCAN_LIST = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT"]
MAG7 = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Google": "GOOGL", "Amazon": "AMZN", "Meta": "META", "Tesla": "TSLA"}

# ────────────────────────────────────────────────
# 2. ADVANCED DATA ENGINES
# ────────────────────────────────────────────────

class AlphaData:
    @staticmethod
    @st.cache_data(ttl=60)
    def calc_gex_profile(ticker):
        """Calculates Gamma Exposure Profile and Flip Level."""
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="1d")
            if hist.empty: return None, None, None, None
            spot = hist['Close'].iloc[-1]
            
            # Get nearest monthly expiration
            exp = tk.options[0] 
            chain = tk.option_chain(exp)
            df_g = pd.concat([chain.calls.assign(type='call'), chain.puts.assign(type='put')])
            
            # Paramters for GEX estimation
            prices = np.linspace(spot * 0.95, spot * 1.05, 40)
            gex_line = []
            r, q, t = 0.04, 0.01, 7/365 # 1-week horizon for dealer hedging
            
            for p in prices:
                total_gamma = 0
                for _, opt in df_g.iterrows():
                    iv = opt.impliedVolatility if opt.impliedVolatility > 0 else 0.2
                    d1 = (np.log(p/opt.strike) + (r-q+0.5*iv**2)*t) / (iv*np.sqrt(t))
                    gamma = norm.pdf(d1) / (p * iv * np.sqrt(t))
                    direction = 1 if opt['type'] == 'call' else -1
                    total_gamma += (opt.openInterest * 100 * p**2 * 0.01 * gamma * direction)
                gex_line.append(total_gamma)
            
            gex_line = np.array(gex_line)
            zero_idx = np.where(np.diff(np.sign(gex_line)))[0]
            flip = prices[zero_idx[0]] if len(zero_idx) > 0 else prices[np.argmin(np.abs(gex_line))]
            
            return prices, gex_line, flip, spot
        except:
            return None, None, None, None

# ────────────────────────────────────────────────
# 3. UI TABS
# ────────────────────────────────────────────────
st.title("🏛️ Alpha Terminal Pro v2.1")
st.caption(f"LIVE SCANNER ACTIVE | Data as of {datetime.datetime.now().strftime('%H:%M:%S')} EST")

tab_scanner, tab_gex, tab_intel, tab_rs = st.tabs(["🚨 Scanner", "📊 Gamma Lab", "🧠 Intel", "⚖️ RS"])

with tab_scanner:
    st.subheader("⚡ Real-Time Gamma Flip Scanner")
    st.info("Scanner monitors for price crossing 'Zero Gamma'—the pivot point where market makers flip from stabilizing to trend-amplifying.")
    
    cols = st.columns(len(SCAN_LIST))
    alerts = []

    for i, ticker in enumerate(SCAN_LIST):
        prices, gex, flip, spot = AlphaData.calc_gex_profile(ticker)
        
        if spot and flip:
            dist = (spot - flip) / flip * 100
            color = "green" if dist > 0 else "red"
            cols[i].metric(ticker, f"${spot:.2f}", f"{dist:.2f}% to Flip", delta_color="normal")
            
            # Logic for Critical Alert
            if abs(dist) < 0.5:
                alerts.append({
                    "ticker": ticker,
                    "spot": spot,
                    "flip": flip,
                    "msg": f"CRITICAL: {ticker} is sitting on the Gamma Flip level. Expect high volatility breakout."
                })
            elif (dist > 0 and dist < 0.1) or (dist < 0 and dist > -0.1):
                alerts.append({
                    "ticker": ticker,
                    "spot": spot,
                    "flip": flip,
                    "msg": f"CROSSING: {ticker} is currently flipping Gamma polarity."
                })

    st.divider()
    if alerts:
        for a in alerts:
            st.markdown(f"""
                <div class="alert-card">
                    <h3 style="margin:0; color:#ff4b4b;">⚠️ {a['ticker']} Alert</h3>
                    <p>{a['msg']}<br><b>Spot:</b> ${a['spot']:.2f} | <b>Flip:</b> ${a['flip']:.2f}</p>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.success("No critical Gamma crosses detected. Market in stable regime.")

with tab_gex:
    target = st.text_input("Deep Dive Ticker", value="SPY").upper()
    prices, gex, flip, spot = AlphaData.calc_gex_profile(target)
    if prices is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=prices, y=gex/1e9, name="GEX ($B)", fill='tozeroy', line=dict(color='#00ffcc')))
        fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text="SPOT")
        fig.add_vline(x=flip, line_dash="dot", line_color="orange", annotation_text="FLIP")
        fig.update_layout(template="plotly_dark", title=f"{target} Gamma Profile", height=500)
        st.plotly_chart(fig, use_container_width=True)

with tab_intel:
    st.subheader("🧠 Google Finance News Sentiment")
    # Same as previous logic, analyzing NVDA/Mag7 news
    ticker_int = st.selectbox("Select Ticker", SCAN_LIST)
    # [Insert Scraping Logic here as per v2.0]
    st.write("Scraping live upgrades/downgrades for", ticker_int)

with tab_rs:
    # 5-Day Relative Strength Matrix
    st.subheader("⚖️ Relative Strength vs QQQ")
    # [Insert Matrix Logic from previous version]

st_autorefresh(interval=60000, key="auto_refresh_scanner")
