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
    "S&P 500 Futures (ES)": "ES=F", "Nasdaq 100 Futures (NQ)": "NQ=F",
    "Dow Jones Futures (YM)": "YM=F", "SPY (S&P 500 ETF)": "SPY",
    "QQQ (Nasdaq 100 ETF)": "QQQ", "VIX": "^VIX",
    "10Y Yield (^TNX)": "^TNX", "DXY (US Dollar)": "DX-Y.NYB"
}

SECTOR_TICKERS = {
    "Technology (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV", "Consumer Disc (XLY)": "XLY", "Industrials (XLI)": "XLI",
    "Utilities (XLU)": "XLU", "Real Estate (XLRE)": "XLRE", "Consumer Staples (XLP)": "XLP",
    "Materials (XLB)": "XLB"
}

ETF_TICKERS = {
    "Bitcoin ETF (IBIT)": "IBIT", "Gold ETF (GLD)": "GLD", "Silver (SLV)": "SLV",
    "Bonds 20Y+ (TLT)": "TLT", "Semis (SMH)": "SMH", "Ark Innovation (ARKK)": "ARKK"
}

TWENTYFOUR_TICKERS = {
    "Bitcoin 24h (BTC-USD)": "BTC-USD", "Ethereum (ETH-USD)": "ETH-USD",
    "Gold Futures (GC)": "GC=F", "Crude Oil (CL)": "CL=F"
}

MAG7_TICKERS = {
    "Apple (AAPL)": "AAPL", "Microsoft (MSFT)": "MSFT", "Nvidia (NVDA)": "NVDA",
    "Amazon (AMZN)": "AMZN", "Alphabet (GOOGL)": "GOOGL", "Meta (META)": "META", "Tesla (TSLA)": "TSLA"
}

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS, **TWENTYFOUR_TICKERS, **MAG7_TICKERS}

# --- ANALYTICS ---
def analyze_sentiment(text):
    if not text or not isinstance(text, str): return "⚖️ Neutral"
    bullish = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'growth', 'bull', 'high', 'positive', 'win', 'beat', 'boost', 'strong', 'outperform', 'soar', 'raises']
    bearish = ['fall', 'down', 'drop', 'slump', 'plunge', 'bear', 'low', 'negative', 'loss', 'crash', 'dip', 'cut', 'sink', 'weak', 'miss', 'lowers', 'decline']
    text = text.lower()
    b_score = sum(1 for w in bullish if w in text)
    s_score = sum(1 for w in bearish if w in text)
    if b_score > s_score: return "🐂 Bullish"
    if s_score > b_score: return "🐻 Bearish"
    return "⚖️ Neutral"

@st.cache_data(ttl=45)
def fetch_all_market_data():
    tickers_list = list(ALL_TICKERS.values())
    ticker_to_label = {v: k for k, v in ALL_TICKERS.items()}
    
    # Batch Download
    daily_data = yf.download(tickers=tickers_list, period="60d", interval="1d", progress=False)
    intra_data = yf.download(tickers=tickers_list, period="1d", interval="5m", prepost=True, progress=False)

    rows = []
    for ticker in tickers_list:
        label = ticker_to_label.get(ticker, ticker)
        try:
            # Prev Close Logic
            prev_close = np.nan
            if 'Close' in daily_data:
                col = daily_data['Close'][ticker] if ticker in daily_data['Close'] else None
                if col is not None:
                    clean_col = col.dropna()
                    if len(clean_col) >= 2: prev_close = clean_col.iloc[-2]

            # Current Price Logic
            current_price = np.nan
            if 'Close' in intra_data:
                col_i = intra_data['Close'][ticker] if ticker in intra_data['Close'] else None
                if col_i is not None:
                    clean_intra = col_i.dropna()
                    if len(clean_intra) > 0: current_price = clean_intra.iloc[-1]
            
            if np.isnan(current_price) and 'Close' in daily_data:
                current_price = daily_data['Close'][ticker].iloc[-1]

            pct_change = ((current_price - prev_close) / prev_close * 100) if not np.isnan(current_price) and not np.isnan(prev_close) else np.nan

            # Volume Logic
            rel_vol = np.nan
            if 'Volume' in intra_data and 'Volume' in daily_data:
                day_vol = intra_data['Volume'][ticker].sum() if ticker in intra_data['Volume'] else 0
                vol_hist = daily_data['Volume'][ticker].dropna() if ticker in daily_data['Volume'] else None
                if vol_hist is not None and len(vol_hist) > 1:
                    avg_vol = vol_hist.iloc[-21:-1].mean() if len(vol_hist) >= 21 else vol_hist.iloc[:-1].mean()
                    if avg_vol > 0: rel_vol = day_vol / avg_vol

            rows.append({"Asset": label, "Symbol": ticker, "Price": current_price, "Change %": pct_change, "Rel Vol": rel_vol})
        except:
            rows.append({"Asset": label, "Symbol": ticker, "Price": np.nan, "Change %": np.nan, "Rel Vol": np.nan})
    return pd.DataFrame(rows)

# --- STYLING HELPERS ---
def color_pct(val):
    if pd.isna(val): return ''
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

def color_rel(val):
    if pd.isna(val) or val < 1.5: return ''
    return 'background-color: rgba(0, 255, 0, 0.2); font-weight: bold'

# --- MAIN APP ---
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

full_market = fetch_all_market_data().dropna(subset=['Change %'])

# Benchmarking
benchmark_change = full_market[full_market['Asset'] == "SPY (S&P 500 ETF)"]['Change %'].iloc[0] if "SPY (S&P 500 ETF)" in full_market['Asset'].values else 0.0
full_market['RS'] = full_market['Change %'] - benchmark_change

# Sidebar
st.sidebar.title("🏛️ Terminal Settings")
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="datarefresh")

# Main View
st.title("🏛️ Pro Market Terminal")
st.caption(f"Status: Live | EST: {time_now} | Auto-Refresh: {refresh}s")

# Scanner
col1, col2, col3 = st.columns([2, 2, 1])
top_g = full_market.sort_values('Change %', ascending=False).head(6)
top_l = full_market.sort_values('Change %', ascending=True).head(6)

with col1:
    st.write("**Leaders 🚀**")
    for _, r in top_g.iterrows(): st.write(f"🟢 {r['Asset']}: `{r['Change %']:+.2f}%` {'🔥' if r['Rel Vol'] > 1.5 else ''}")
with col2:
    st.write("**Laggards 📉**")
    for _, r in top_l.iterrows(): st.write(f"🔴 {r['Asset']}: `{r['Change %']:+.2f}%` {'🔥' if r['Rel Vol'] > 1.5 else ''}")
with col3:
    up, down = len(full_market[full_market['Change %'] > 0]), len(full_market[full_market['Change %'] < 0])
    st.metric("Breadth (Up/Down)", f"{up} / {down}", delta=f"{up-down}")

st.divider()

# Tabs
tab1, tab2, tab3 = st.tabs(["🌎 Markets", "📈 Sectors & Mag7", "📊 Analysis & Charts"])

with tab1:
    m_data = full_market[full_market['Asset'].isin(GLOBAL_TICKERS.keys())]
    st.dataframe(m_data.drop(columns=['Symbol']).style.format({"Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": "{:.2f}x"}).map(color_pct, subset=["Change %"]), use_container_width=True, hide_index=True)

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Sectors")
        s_data = full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())]
        st.dataframe(s_data[['Asset', 'Price', 'Change %', 'RS']].style.format({"Price": "{:.2f}", "Change %": "{:+.2f}%", "RS": "{:+.2f}"}).map(color_pct, subset=["Change %", "RS"]), use_container_width=True, hide_index=True)
    with c2:
        st.subheader("Magnificent 7")
        mag_data = full_market[full_market['Asset'].isin(MAG7_TICKERS.keys())]
        st.dataframe(mag_data[['Asset', 'Price', 'Change %', 'Rel Vol']].style.format({"Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": "{:.2f}x"}).map(color_pct, subset=["Change %"]).map(color_rel, subset=["Rel Vol"]), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Relative Strength vs. SPY")
    rs_data = full_market[full_market['Asset'].isin(list(SECTOR_TICKERS.keys()) + list(MAG7_TICKERS.keys()))].sort_values('RS')
    st.bar_chart(rs_data, x="Asset", y="RS", color="RS", use_container_width=True)
    
    st.divider()
    st.subheader("Intraday Charts")
    sel = st.multiselect('Select Asset', list(ALL_TICKERS.keys()), default=["SPY (S&P 500 ETF)", "Nvidia (NVDA)"])
    for l in sel:
        c_data = yf.Ticker(ALL_TICKERS[l]).history(period='1d', interval='5m')
        if not c_data.empty:
            st.write(f"**{l}**")
            st.line_chart(c_data['Close'])
