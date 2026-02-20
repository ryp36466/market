import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
import requests
from bs4 import BeautifulSoup
from finvizfinance.news import News
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm

# ────────────────────────────────────────────────
#  1. PAGE & THEME CONFIG
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# Custom CSS for a sleek "Bloomberg-style" dark terminal look
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 10px; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# ────────────────────────────────────────────────
#  2. TICKER CONFIGURATIONS
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "S&P 500": "^GSPC", "Nasdaq 100": "^NDX", "VIX": "^VIX", 
    "10Y Yield": "^TNX", "DXY": "DX-Y.NYB", "SPY": "SPY", "QQQ": "QQQ"
}

SECTOR_TICKERS = {
    "Tech (XLK)": "XLK", "Software (IGV)": "IGV", "Financials (XLF)": "XLF", 
    "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV", "Disc (XLY)": "XLY", 
    "Indus (XLI)": "XLI", "Utils (XLU)": "XLU", "Real Estate": "XLRE", 
    "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"
}

NEO_CLOUD_TICKERS = {
    "Nebius": "NBIS", "Vertiv": "VRT", "Arista": "ANET", 
    "Supermicro": "SMCI", "Dell": "DELL", "Palantir": "PLTR",
    "Equinix": "EQIX", "Digital Realty": "DLR"
}

MAG7_TICKERS = {
    "Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN",
    "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"
}

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **NEO_CLOUD_TICKERS, **MAG7_TICKERS}

HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO',
    'HD', 'COST', 'NFLX', 'DIS', 'PFE', 'MRK', 'LLY', 'AVGO'
}

TIER1_FIRMS = {
    'Goldman Sachs', 'Morgan Stanley', 'JPMorgan', 'Bank of America', 'Citigroup', 
    'Barclays', 'Evercore', 'UBS', 'Jefferies', 'RBC Capital', 'Wells Fargo'
}

FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"

# ────────────────────────────────────────────────
#  3. DATA ENGINE & CALCULATIONS
# ────────────────────────────────────────────────

@st.cache_data(ttl=60)
def fetch_market_snapshot():
    symbols = list(ALL_TICKERS.values())
    hist_data = yf.download(symbols, period="5d", interval="1d", progress=False)
    intra = yf.download(symbols, period="1d", interval="5m", prepost=True, progress=False)
    
    rows = []
    for label, sym in ALL_TICKERS.items():
        try:
            price = intra['Close'][sym].dropna().iloc[-1]
            prev_close = hist_data['Close'][sym].iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            today_vol = intra['Volume'][sym].sum()
            avg_vol = hist_data['Volume'][sym].iloc[-5:-1].mean()
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            rows.append({"Asset": label, "Symbol": sym, "Price": price, "Change %": change, "RVOL": rvol})
        except: continue
    return pd.DataFrame(rows), intra, hist_data

def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365); v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return np.where(types == 'call', val, -val)

def find_gamma_flip(spot, df_options):
    prices = np.linspace(spot * 0.90, spot * 1.10, 60)
    total_gex = []
    for p in prices:
        g = calc_gamma_vectorized(p, df_options['strike'].values, df_options['dte'].values,
                                  df_options['impliedVolatility'].values, 0.04, 0.01,
                                  df_options['type'].values, df_options['openInterest'].values)
        total_gex.append(g.sum())
    total_gex = np.array(total_gex)
    zero_cross = np.where(np.diff(np.sign(total_gex)))[0]
    if len(zero_cross) > 0:
        idx = zero_cross[0]
        flip = prices[idx] + (0 - total_gex[idx]) * (prices[idx+1] - prices[idx]) / (total_gex[idx+1] - total_gex[idx])
        return flip, prices, total_gex
    return None, prices, total_gex

def get_sentiment_score(text):
    bull = ['upbeat','growth','surge','rally','beat','buy','bullish','expansion','profit','gain']
    bear = ['slump','drop','fall','miss','sell','bearish','contraction','loss','negative','sink']
    score = sum(1 for w in bull if w in text.lower()) - sum(1 for w in bear if w in text.lower())
    if score > 0: return "🟢 Bullish", score
    if score < 0: return "🔴 Bearish", score
    return "⚪ Neutral", 0

# [Simplified Earnings & News functions for reliability]
def get_earnings_lite(date_str):
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={date_str}&to={date_str}&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=5).json()
        return [ { "Symbol": x['symbol'], "EPS Est": x.get('epsEstimate', '—'), "Rev Est (B)": round(x.get('revenueEstimate', 0)/1e9, 2) } for x in r.get('earningsCalendar', []) if x['symbol'] in HUGE_CAP_SYMBOLS ]
    except: return []

# ────────────────────────────────────────────────
#  4. MAIN UI EXECUTION
# ────────────────────────────────────────────────
market_df, intra_data, hist_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"LIVE TERMINAL | EST: {time_now} | Refreshing every 5m")

# TAB NAVIGATION
tab_overview, tab_sectors, tab_rel_strength, tab_gex, tab_options, tab_earnings, tab_analyst, tab_news = st.tabs([
    "📈 Overview", "🔥 Alpha Sectors", "⚖️ Rel Strength", "📊 GEX & Flip", "🐳 Options", "🎯 Earnings", "📊 Analyst", "📰 News"
])

# OVERVIEW: Mag 7 & Global
with tab_overview:
    m1, m2, m3, m4 = st.columns(4)
    for i, sym in enumerate(["SPY", "QQQ", "VIX", "^TNX"]):
        row = market_df[market_df['Symbol'] == sym].iloc[0]
        [m1, m2, m3, m4][i].metric(row['Asset'], f"{row['Price']:.2f}", f"{row['Change %']:.2f}%")
    
    st.subheader("🚀 Momentum Leaders (Mag 7 + Neo Clouds)")
    combined = market_df[market_df['Asset'].isin(list(MAG7_TICKERS.keys()) + list(NEO_CLOUD_TICKERS.keys()))].copy()
    st.dataframe(combined.sort_values("Change %", ascending=False).style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)

# ALPHA SECTORS: The requested IGV + Neo focus
with tab_sectors:
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("🏢 Institutional Sectors")
        sect = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
        st.dataframe(sect.style.background_gradient(cmap='RdYlGn', subset=['Change %']), hide_index=True, use_container_width=True)
    with col_right:
        st.subheader("☁️ Neo Clouds (AI Infrastructure)")
        neo = market_df[market_df['Asset'].isin(NEO_CLOUD_TICKERS.keys())].copy()
        st.dataframe(neo.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)

# RELATIVE STRENGTH: Sector vs SPY Line Chart
with tab_rel_strength:
    st.subheader("⚖️ Relative Strength vs SPY (5-Day)")
    try:
        symbols_to_plot = ["SPY", "XLK", "IGV", "XLF", "XLE", "VRT", "NVDA"]
        plot_df = hist_data['Close'][symbols_to_plot].dropna()
        norm_df = (plot_df / plot_df.iloc[0] - 1) * 100
        fig = px.line(norm_df.reset_index().melt(id_vars='Date', var_name='Ticker', value_name='Perf %'),
                      x='Date', y='Perf %', color='Ticker', template="plotly_dark", height=500)
        fig.update_traces(patch={"line": {"width": 5, "dash": "dot"}}, selector={"legendgroup": "SPY"})
        st.plotly_chart(fig, use_container_width=True)
        
        # Delta Table
        delta = (norm_df.iloc[-1] - norm_df.iloc[-1]['SPY']).round(2).reset_index()
        delta.columns = ['Ticker', 'Alpha (vs SPY %)']
        st.write("### Sector Alpha Leaders")
        st.dataframe(delta.sort_values('Alpha (vs SPY %)', ascending=False).style.background_gradient(cmap='RdYlGn'), hide_index=True)
    except Exception as e: st.error(f"RS Error: {e}")

# GEX & FLIP: Regime Analysis
with tab_gex:
    ticker = st.text_input("GEX/Flip Analysis (Ticker)", value="SPY").upper()
    if ticker:
        with st.spinner("Calculating Gamma Profile..."):
            tk = yf.Ticker(ticker)
            spot = tk.history(period="1d")['Close'].iloc[-1]
            opts = tk.options[:3]
            chains = []
            for exp in opts:
                c = tk.option_chain(exp)
                chains.extend([c.calls.assign(type='call', exp=exp), c.puts.assign(type='put', exp=exp)])
            df_g = pd.concat(chains, ignore_index=True)
            df_g['dte'] = (pd.to_datetime(df_g['exp']) - datetime.datetime.now()).dt.days / 365.0
            
            flip, prices, profile = find_gamma_flip(spot, df_g)
            
            c1, c2 = st.columns([1, 2])
            with c1:
                st.metric("Current Price", f"${spot:.2f}")
                if flip:
                    st.metric("Gamma Flip Level", f"${flip:.2f}", f"{(spot/flip-1)*100:.2f}% from Spot")
                    st.warning("Volatility Zone" if spot < flip else "Stable Zone")
            with c2:
                fig_p = go.Figure()
                fig_p.add_trace(go.Scatter(x=prices, y=profile/1e6, name="GEX Profile", fill='tozeroy'))
                fig_p.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text="SPOT")
                if flip: fig_p.add_vline(x=flip, line_dash="dot", line_color="orange", annotation_text="FLIP")
                fig_p.update_layout(template="plotly_dark", title=f"{ticker} Gamma Regime", height=400)
                st.plotly_chart(fig_p, use_container_width=True)

# EARNINGS & ANALYSTS & NEWS
with tab_earnings:
    st.subheader("🎯 Upcoming Big Cap Earnings")
    today = datetime.datetime.now(est).date().strftime('%Y-%m-%d')
    st.table(get_earnings_lite(today))

with tab_news:
    st.subheader("📰 Market Wire & Sentiment")
    try:
        news_data = News().get_news()['news'].head(15)
        for _, item in news_data.iterrows():
            label, score = get_sentiment_score(item['Title'])
            with st.expander(f"{label} | {item['Title']}"):
                st.write(f"Source: {item['Source']}")
                st.write(f"[Link]({item['URL']})")
    except: st.info("News stream currently refreshing...")

# Auto-refresh logic
st_autorefresh(interval=300000, key="global_refresh")
