import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import asyncio
import aiohttp
import requests
from streamlit_autorefresh import st_autorefresh
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm

# ────────────────────────────────────────────────
#  1. PAGE CONFIG & SECRETS
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

FINNHUB_KEY = st.secrets.get("FINNHUB_API_KEY", "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog")

# ────────────────────────────────────────────────
#  2. TICKER DEFINITIONS & THEMES
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES Fut": "ES=F", "NQ Fut": "NQ=F", "RTY Fut": "RTY=F",
    "SPY": "SPY", "QQQ": "QQQ", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"
}

SECTOR_ETFS = {
    "🔥 SEMIS": "SMH", "☁️ CLOUD": "IGV", "🖥️ TECH": "XLK", "💰 FIN": "XLF",
    "🏥 HEALTH": "XLV", "🛢️ ENERGY": "XLE", "🧱 INDUS": "XLI", "🛍️ CONS": "XLY",
    "🧪 MATS": "XLB", "🪙 CRYPTO": "IBIT"
}

TRADING_THEMES = {
    "🔥 SEMICONDUCTORS": ["NVDA", "AMD", "AVGO", "TSM", "ARM", "MU", "SMCI"],
    "☁️ SOFTWARE / AI": ["MSFT", "PLTR", "CRM", "CRWD", "NOW", "ORCL", "ADBE"],
    "🖥️ BIG TECH": ["AAPL", "GOOGL", "META", "AMZN", "NFLX", "DELL"],
    "🪙 CRYPTO / BTC": ["COIN", "MSTR", "MARA", "RIOT", "CLSK"],
    "🚀 SPACE / GROWTH": ["RKLB", "ASTS", "PLTR", "OKLO", "RIVN"]
}

MAG7_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

symbol_to_label = {v: k for k, v in GLOBAL_TICKERS.items()}
ALL_SYMBOLS = list(set(list(GLOBAL_TICKERS.values()) + list(SECTOR_ETFS.values()) + 
                       [s for t in TRADING_THEMES.values() for s in t] + MAG7_TICKERS))

# ────────────────────────────────────────────────
#  3. ASYNC DATA ENGINE
# ────────────────────────────────────────────────
async def fetch_quote(session, sym):
    f_sym = sym.replace('^', '').split('=')[0] if any(x in sym for x in ['^', '=']) else sym
    if sym == "DX-Y.NYB": f_sym = "DXY"
    url = f"https://finnhub.io/api/v1/quote?symbol={f_sym}&token={FINNHUB_KEY}"
    try:
        async with session.get(url, timeout=5) as response:
            return sym, await response.json()
    except:
        return sym, None

async def get_all_quotes(symbols):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_quote(session, s) for s in symbols]
        return await asyncio.gather(*tasks)

@st.cache_data(ttl=12)
def fetch_market_snapshot():
    intra = yf.download(ALL_SYMBOLS, period="3d", interval="1m", prepost=True, progress=False)
    hist = yf.download(ALL_SYMBOLS, period="20d", interval="1d", progress=False)
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    quotes = dict(loop.run_until_complete(get_all_quotes(ALL_SYMBOLS)))
    
    rows = []
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.datetime.now(tz).strftime('%Y-%m-%d')

    for sym in ALL_SYMBOLS:
        try:
            q = quotes.get(sym)
            if q and q.get('c'):
                price, prev_close = float(q['c']), float(q['pc'])
            else:
                price = intra['Close'][sym].dropna().iloc[-1]
                prev_close = hist['Close'][sym].dropna().iloc[-2]
            
            change = ((price - prev_close) / prev_close * 100)
            
            try:
                today_open = intra['Open'][sym].loc[today_str].dropna().iloc[0]
                gap = ((today_open - prev_close) / prev_close * 100)
                today_vol = intra['Volume'][sym].loc[today_str].sum()
                avg_vol = hist['Volume'][sym].iloc[-15:-2].mean()
                rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            except: gap, rvol = 0.0, 1.0

            rows.append({
                "Asset": symbol_to_label.get(sym, sym), "Symbol": sym, "Price": round(price, 2),
                "Gap %": round(gap, 2), "Change %": round(change, 2), "RVOL": round(rvol, 2)
            })
        except: continue
    return pd.DataFrame(rows), intra, hist

# ────────────────────────────────────────────────
#  24-HOUR NEWS (YOUR REQUESTED ASYNC VERSION)
# ────────────────────────────────────────────────
async def fetch_news(session, sym):
    to_date = datetime.datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"https://finnhub.io/api/v1/company-news?symbol={sym}&from={from_date}&to={to_date}&token={FINNHUB_KEY}"
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                return await response.json()
            return []
    except:
        return []

# ────────────────────────────────────────────────
#  MATH FUNCTIONS
# ────────────────────────────────────────────────
def get_gamma_exposure(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365.0)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = gamma * OI * 100 * S
    return np.where(types == 'call', val, -val)

# ────────────────────────────────────────────────
#  FETCH DATA
# ────────────────────────────────────────────────
market_df, intra_data, hist_data = fetch_market_snapshot()

# ────────────────────────────────────────────────
#  ALERTS
# ────────────────────────────────────────────────
if 'alert_log' not in st.session_state: 
    st.session_state.alert_log = []

def process_alerts(df, intra):
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.datetime.now(tz).strftime('%Y-%m-%d')
    for _, row in df.iterrows():
        if row['RVOL'] > 4.0:
            msg = f"{row['Symbol']} RVOL EXPLOSION: {row['RVOL']}x"
            if not any(msg in a for a in st.session_state.alert_log[:5]):
                st.session_state.alert_log = [f"[{datetime.datetime.now(tz).strftime('%H:%M')}] 🔥 {msg}"] + st.session_state.alert_log[:10]

# ────────────────────────────────────────────────
#  UI
# ────────────────────────────────────────────────
st.title("🏛️ Alpha Terminal Pro")
st.caption(f"Last Sync: {datetime.datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')} EST")

with st.sidebar:
    st.header("🎰 LIVE ALERTS")
    process_alerts(market_df, intra_data)
    with st.container(height=300, border=True):
        for a in st.session_state.alert_log: 
            st.write(a)
    if st.button("Clear Log"): 
        st.session_state.alert_log = []; st.rerun()

tabs = st.tabs(["📰 24h News Feed", "📝 Battle Plan", "📊 Market Overview", "🎯 Themes", "⚖️ Alpha Delta", "📊 Gamma GEX", "💼 Portfolio"])

# ==================== NEW 24H NEWS TAB ====================
with tabs[0]:
    st.subheader("📰 Live Finnhub Feed (Last 24h)")
    news_focus = st.multiselect("Filter by Ticker", options=ALL_SYMBOLS, default=["SPY", "NVDA", "TSLA", "BTC-USD", "SMH"])
    
    if st.button("🔄 Refresh News Feed", type="primary"):
        with st.spinner("Scanning wires across all tickers..."):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            async def get_news_batch(symbols):
                async with aiohttp.ClientSession() as session:
                    tasks = [fetch_news(session, s) for s in symbols]
                    return await asyncio.gather(*tasks)
            
            all_news_raw = loop.run_until_complete(get_news_batch(news_focus))
            
            processed_news = []
            for news_list in all_news_raw:
                for item in news_list:
                    processed_news.append({
                        "time": datetime.datetime.fromtimestamp(item['datetime']).strftime('%H:%M:%S'),
                        "symbol": item.get('related', item.get('symbol', 'N/A')),
                        "headline": item['headline'],
                        "source": item['source'],
                        "url": item['url'],
                        "summary": item.get('summary', '')
                    })
            
            if processed_news:
                for article in sorted(processed_news, key=lambda x: x['time'], reverse=True)[:30]:
                    with st.container(border=True):
                        col_icon, col_txt = st.columns([1, 15])
                        h_lower = article['headline'].lower()
                        color = "#00FF00" if any(w in h_lower for w in ['surge','beat','buy','growth','up']) else "#FF4B4B" if any(w in h_lower for w in ['slump','miss','drop','cut','down']) else "white"
                        
                        col_icon.write("🗞️")
                        with col_txt:
                            st.markdown(f"**{article['symbol']}** | {article['time']} | *{article['source']}*")
                            st.markdown(f"#### [{article['headline']}]({article['url']})")
                            if article['summary']:
                                with st.expander("Read Summary"):
                                    st.write(article['summary'])
            else:
                st.info("No major headlines found in the last 24h for selected tickers.")

# ==================== REST OF YOUR TABS ====================
with tabs[1]:
    st.subheader("🕓 Premarket Battle Plan")
    es_chg = market_df[market_df['Symbol'] == 'ES=F']['Change %'].iloc[0] if 'ES=F' in market_df['Symbol'].values else 0
    nq_chg = market_df[market_df['Symbol'] == 'NQ=F']['Change %'].iloc[0] if 'NQ=F' in market_df['Symbol'].values else 0
    col1, col2 = st.columns([2, 1])
    with col1:
        st.info(f"""
        **Macro Pulse:** {'🚀 Risk-On' if nq_chg > 0.5 else '🐻 Risk-Off' if nq_chg < -0.5 else '⚖️ Neutral/Chop'}
        - Futures: NQ ({nq_chg:+.2f}%) vs ES ({es_chg:+.2f}%)
        - Strategy: {'Focus on Tech Breakouts' if nq_chg > es_chg else 'Focus on Value/Defensive Rotation'}
        """)
    with col2:
        vix = market_df[market_df['Symbol'] == '^VIX']['Price'].iloc[0] if '^VIX' in market_df['Symbol'].values else 20
        st.metric("VIX Fear Index", f"{vix:.2f}", delta="Volatile" if vix > 20 else "Calm", delta_color="inverse")

with tabs[2]:
    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.write("**Key Indices**")
        indices = market_df[market_df['Symbol'].isin(GLOBAL_TICKERS.values())]
        st.dataframe(indices.style.background_gradient(cmap='RdYlGn', subset=['Change %']), hide_index=True)
    with col_b:
        st.write("**Mag 7 Performance**")
        m7 = market_df[market_df['Symbol'].isin(MAG7_TICKERS)]
        st.dataframe(m7[['Symbol', 'Change %']].style.background_gradient(cmap='RdYlGn'), hide_index=True)

with tabs[3]:
    theme_cols = st.columns(len(TRADING_THEMES))
    for i, (name, syms) in enumerate(TRADING_THEMES.items()):
        with theme_cols[i]:
            st.markdown(f"**{name}**")
            t_df = market_df[market_df['Symbol'].isin(syms)]
            st.dataframe(t_df[['Symbol', 'Change %']].style.background_gradient(cmap='RdYlGn'), hide_index=True)

with tabs[4]:
    st.subheader("Relative Strength vs SPY (Alpha Delta)")
    spy_chg = market_df[market_df['Symbol'] == 'SPY']['Change %'].iloc[0] if not market_df.empty else 0
    rs_df = market_df[market_df['Symbol'].isin([s for t in TRADING_THEMES.values() for s in t])].copy()
    rs_df['Alpha'] = rs_df['Change %'] - spy_chg
    fig = px.bar(rs_df.sort_values('Alpha'), x='Symbol', y='Alpha', color='Alpha', color_continuous_scale='RdYlGn')
    st.plotly_chart(fig, use_container_width=True)

with tabs[5]:
    st.subheader("Options Gamma Profile")
    target = st.text_input("Analyze Symbol", "SPY").upper()
    try:
        tk = yf.Ticker(target)
        spot = tk.history(period="1d")['Close'].iloc[-1]
        chain = tk.option_chain(tk.options[0])
        calls, puts = chain.calls.assign(type='call'), chain.puts.assign(type='put')
        df_opt = pd.concat([calls, puts])
        df_opt['GEX'] = get_gamma_exposure(spot, df_opt['strike'], 5/365, df_opt['impliedVolatility'], 0.04, 0.01, df_opt['type'], df_opt['openInterest'])
        fig_gex = px.bar(df_opt.groupby('strike')['GEX'].sum().reset_index(), x='strike', y='GEX')
        fig_gex.add_vline(x=spot, line_dash="dash", line_color="red")
        st.plotly_chart(fig_gex, use_container_width=True)
    except: st.error("No options data found.")

with tabs[6]:
    st.subheader("💼 Paper Trading Simulator")
    if 'cash' not in st.session_state: st.session_state.cash = 100000.0
    if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
    
    p1, p2, p3 = st.columns([2,1,1])
    t_sym = p1.selectbox("Ticker", ALL_SYMBOLS)
    t_qty = p2.number_input("Qty", min_value=1, value=10)
    curr_p = market_df[market_df['Symbol'] == t_sym]['Price'].iloc[0] if not market_df[market_df['Symbol'] == t_sym].empty else 0
    
    if p3.button("BUY", type="primary", use_container_width=True):
        cost = t_qty * curr_p
        if st.session_state.cash >= cost:
            st.session_state.cash -= cost
            pos = st.session_state.portfolio.get(t_sym, {'qty': 0, 'avg': 0})
            new_qty = pos['qty'] + t_qty
            st.session_state.portfolio[t_sym] = {'qty': new_qty, 'avg': ((pos['qty']*pos['avg']) + cost)/new_qty}
            st.rerun()
    
    st.metric("Buying Power", f"${st.session_state.cash:,.2f}")
    if st.session_state.portfolio:
        st.write(st.session_state.portfolio)

# ────────────────────────────────────────────────
#  AUTO REFRESH
# ────────────────────────────────────────────────
st_autorefresh(interval=30000, key="data_refresh")
