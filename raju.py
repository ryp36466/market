import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
from finvizfinance.news import News
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ────────────────────────────────────────────────
#  1. CONFIGURATION & TICKERS
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# Secure API Key Handling
FINNHUB_KEY = st.secrets.get("FINNHUB_API_KEY", "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog")

GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES (S&P 500 Fut)": "ES=F", "NQ (Nasdaq Fut)": "NQ=F",
    "YM (Dow Fut)": "YM=F", "RTY (Russell 2000)": "RTY=F", "SPY": "SPY", 
    "QQQ": "QQQ", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
}

SECTOR_TICKERS = {
    "Tech (XLK)": "XLK", "Software (IGV)": "IGV", "Semiconductor (SMH)": "SMH",
    "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV",
    "Disc (XLY)": "XLY", "Indus (XLI)": "XLI", "Utils (XLU)": "XLU"
}

TRADING_THEMES = {
    "🔵 SEMICONDUCTORS": ["SMH", "NVDA", "AMD", "AVGO", "TSM", "ARM"],
    "🟣 SOFTWARE / SaaS": ["IGV", "MSFT", "CRM", "NOW", "PLTR", "ORCL"],
    "🟢 NEO CLOUD / AI": ["VRT", "ANET", "SMCI", "DELL", "CRWD"],
    "🟠 CRYPTO / BTC": ["BTC-USD", "MSTR", "COIN", "MARA", "IBIT"],
    "🟤 SMALL CAPS": ["IWM", "TNA", "ASTS", "OKLO"]
}

MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
MAG7_HOT_SYMBOLS = list(MAG7_TICKERS.values()) + ["SPY", "QQQ"]

# Flatten labels for mapping
symbol_to_label = {v: k for d in [GLOBAL_TICKERS, SECTOR_TICKERS, MAG7_TICKERS] for k, v in d.items()}
ALL_SYMBOLS = list(set(list(symbol_to_label.keys()) + [s for t in TRADING_THEMES.values() for s in t]))
ANALYST_SYMBOLS = sorted(list(set([s for t in TRADING_THEMES.values() for s in t])))

# ────────────────────────────────────────────────
#  2. ASYNC DATA ENGINE (Parallel Fetching)
# ────────────────────────────────────────────────

async def fetch_finnhub_quote(session, sym):
    f_sym = sym.replace('^', '').split('=')[0] if any(x in sym for x in ['^', '=']) else sym
    if sym == "DX-Y.NYB": f_sym = "DXY"
    url = f"https://finnhub.io/api/v1/quote?symbol={f_sym}&token={FINNHUB_KEY}"
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                return sym, await response.json()
            return sym, None
    except: return sym, None

async def get_all_quotes(symbols):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_finnhub_quote(session, s) for s in symbols]
        return await asyncio.gather(*tasks)

@st.cache_data(ttl=15)
def fetch_market_snapshot():
    # Batch YFinance for historicals and intraday
    intra = yf.download(ALL_SYMBOLS, period="3d", interval="1m", prepost=True, progress=False)
    hist = yf.download(ALL_SYMBOLS, period="15d", interval="1d", progress=False)
    
    # Run Async Finnhub calls
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    finnhub_data = dict(loop.run_until_complete(get_all_quotes(ALL_SYMBOLS)))
    
    rows = []
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.datetime.now(tz).strftime('%Y-%m-%d')

    for sym in ALL_SYMBOLS:
        try:
            quote = finnhub_data.get(sym)
            if quote and quote.get('c'):
                price, prev_close = quote['c'], quote['pc']
            else:
                price = intra['Close'][sym].dropna().iloc[-1]
                prev_close = hist['Close'][sym].dropna().iloc[-2]
            
            change = ((price - prev_close) / prev_close * 100)
            
            # Gap Logic
            try:
                today_open = intra['Open'][sym].loc[today_str].dropna().iloc[0]
                gap = ((today_open - prev_close) / prev_close * 100)
            except: gap = 0.0

            # RVOL Logic
            try:
                today_vol = intra['Volume'][sym].loc[today_str].sum()
                avg_vol = hist['Volume'][sym].iloc[-15:-2].mean()
                rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            except: rvol = 1.0

            rows.append({
                "Asset": symbol_to_label.get(sym, sym), "Symbol": sym, "Price": price,
                "Gap %": gap, "Change %": change, "RVOL": rvol
            })
        except: continue
    return pd.DataFrame(rows), intra, hist

# ────────────────────────────────────────────────
#  3. ANALYTICS & MATH
# ────────────────────────────────────────────────

def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365.0)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = gamma * OI * 100 * S
    return np.where(types == 'call', val, -val)

@st.cache_data(ttl=600)
def get_pcr_data():
    results = []
    for sym in ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"]:
        try:
            tk = yf.Ticker(sym)
            chain = tk.option_chain(tk.options[0])
            pcr = chain.puts['volume'].sum() / chain.calls['volume'].sum()
            results.append({"Asset": sym, "PCR": round(pcr, 2), "Sentiment": "🐂 Bull" if pcr < 0.7 else "🐻 Bear" if pcr > 1.1 else "⚖️ Neu"})
        except: continue
    return pd.DataFrame(results)

@st.cache_data(ttl=1800)
def get_analyst_ratings():
    ratings = []
    for sym in ANALYST_SYMBOLS[:15]: # Limit to top 15 for speed
        try:
            info = yf.Ticker(sym).info
            ratings.append({
                "Asset": symbol_to_label.get(sym, sym), "Consensus": info.get("recommendationKey", "N/A").replace('_', ' ').title(),
                "Target Mean": info.get("targetMeanPrice"), "Current": info.get("currentPrice"),
                "Upside %": ((info.get("targetMeanPrice", 0) / info.get("currentPrice", 1)) - 1) * 100
            })
        except: continue
    return pd.DataFrame(ratings)

# ────────────────────────────────────────────────
#  4. UI LAYOUT
# ────────────────────────────────────────────────

market_df, intra_data, hist_data = fetch_market_snapshot()
st.title("🏛️ Alpha Terminal Pro")
st.caption(f"Last Sync: {datetime.datetime.now().strftime('%H:%M:%S')} EST | Parallel Engine Active")

# Sidebar Metrics
if not market_df.empty:
    vix_val = market_df[market_df['Symbol'] == "^VIX"]['Price'].values[0]
    st.sidebar.metric("VIX (Fear Index)", f"{vix_val:.2f}", delta="- Risk On" if vix_val < 20 else "+ Volatility")

tabs = st.tabs(["📊 Market Overview", "🎯 Themes", "📊 GEX / Gamma", "🐳 Options", "📊 Analyst Ratings", "🔍 Regime Bias"])

with tabs[0]:
    st.subheader("🗝️ Key Indices & Mag7")
    col1, col2 = st.columns([2, 1])
    
    indices = market_df[market_df['Symbol'].isin(GLOBAL_TICKERS.values())]
    col1.dataframe(indices.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'Gap %']), hide_index=True, use_container_width=True)
    
    mag7 = market_df[market_df['Symbol'].isin(MAG7_TICKERS.values())].sort_values('Change %', ascending=False)
    col2.dataframe(mag7[['Asset', 'Change %']].style.background_gradient(cmap='RdYlGn'), hide_index=True, use_container_width=True)

with tabs[1]:
    cols = st.columns(len(TRADING_THEMES))
    for i, (name, syms) in enumerate(TRADING_THEMES.items()):
        with cols[i]:
            st.markdown(f"**{name}**")
            theme_df = market_df[market_df['Symbol'].isin(syms)]
            st.dataframe(theme_df[['Asset', 'Change %']].style.background_gradient(cmap='RdYlGn'), hide_index=True)

with tabs[2]:
    user_ticker = st.text_input("GEX Lookup", value="SPY").upper()
    try:
        tk = yf.Ticker(user_ticker)
        spot = tk.history(period="1d")['Close'].iloc[-1]
        exp = tk.options[0]
        c = tk.option_chain(exp).calls.assign(type='call')
        p = tk.option_chain(exp).puts.assign(type='put')
        df_g = pd.concat([c, p])
        df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'], 5/365, df_g['impliedVolatility'], 0.04, 0.01, df_g['type'], df_g['openInterest'])
        
        fig = px.bar(df_g.groupby('strike')['GEX'].sum().reset_index(), x='strike', y='GEX', title=f"{user_ticker} Gamma Profile")
        fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text="SPOT")
        st.plotly_chart(fig, use_container_width=True)
    except: st.error("Options data unavailable for this ticker.")

with tabs[3]:
    st.dataframe(get_pcr_data(), use_container_width=True, hide_index=True)

with tabs[4]:
    st.dataframe(get_analyst_ratings().style.background_gradient(cmap='RdYlGn', subset=['Upside %']), use_container_width=True, hide_index=True)

with tabs[5]:
    st.subheader("🔍 Market Regime Analysis")
    def get_bias(row):
        if row['Change %'] > 1.5: return "🚀 Strong Bull"
        if row['Change %'] < -1.5: return "💥 Strong Bear"
        return "⚖️ Neutral / Chop"
    
    market_df['Regime'] = market_df.apply(get_bias, axis=1)
    st.dataframe(market_df[['Asset', 'Change %', 'Regime']].style.map(
        lambda x: 'background-color: #004400' if 'Bull' in str(x) else ('background-color: #440000' if 'Bear' in str(x) else ''),
        subset=['Regime']
    ), hide_index=True, use_container_width=True)

# Auto-refresh: 30 seconds
st_autorefresh(interval=30000, key="data_refresh")

# ────────────────────────────────────────────────
#  RELATIVE STRENGTH HEATMAP LOGIC
# ────────────────────────────────────────────────

with tabs[5]: # Or add a 6th tab: "⚖️ Leaderboard"
    st.subheader("⚖️ Relative Strength vs SPY (Alpha Delta)")
    st.caption("Shows which stocks are outperforming the benchmark. Green = Leading | Red = Lagging")

    if not market_df.empty:
        try:
            # 1. Get the Benchmark Performance
            spy_change = market_df[market_df['Symbol'] == 'SPY']['Change %'].values[0]
            
            # 2. Build the RS Dataset
            rs_data = []
            for theme, symbols in TRADING_THEMES.items():
                for sym in symbols:
                    row = market_df[market_df['Symbol'] == sym]
                    if not row.empty:
                        stock_chg = row['Change %'].values[0]
                        rs_data.append({
                            "Theme": theme.split()[-1], # Shorten name
                            "Ticker": sym,
                            "Alpha Delta": round(stock_chg - spy_change, 2),
                            "Actual %": round(stock_chg, 2)
                        })
            
            rs_df = pd.DataFrame(rs_data)

            # 3. Create the Heatmap Matrix
            # We pivot the data so Themes are columns and Tickers are rows
            # Since themes have different stocks, we'll use a Bar chart for better clarity 
            # or a specialized Plotly Heatmap
            
            fig_rs = px.bar(
                rs_df.sort_values("Alpha Delta", ascending=False),
                x="Ticker",
                y="Alpha Delta",
                color="Alpha Delta",
                text="Alpha Delta",
                color_continuous_scale="RdYlGn",
                range_color=[-3, 3], # Caps the intensity at +/- 3% relative strength
                template="plotly_dark",
                title=f"Alpha Delta (Stock % minus SPY {spy_change:+.2f}%)"
            )
            
            fig_rs.update_traces(textposition='outside')
            fig_rs.add_hline(y=0, line_dash="dash", line_color="white")
            st.plotly_chart(fig_rs, use_container_width=True)

            # 4. The "Top 5 Alpha" Leaders
            st.markdown("### 🏆 Top 5 Momentum Leaders")
            top_leaders = rs_df.sort_values("Alpha Delta", ascending=False).head(5)
            
            cols = st.columns(5)
            for idx, leader in enumerate(top_leaders.to_dict('records')):
                with cols[idx]:
                    st.metric(
                        label=leader['Ticker'],
                        value=f"{leader['Actual %']}%",
                        delta=f"{leader['Alpha Delta']}% vs SPY"
                    )
        except Exception as e:
            st.warning(f"Waiting for SPY data to sync... {e}")
