import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import asyncio
import aiohttp
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
#  2. TICKER DEFINITIONS & CLEANING
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES Fut": "ES=F", "NQ Fut": "NQ=F", "RTY Fut": "RTY=F",
    "SPY": "SPY", "QQQ": "QQQ", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"
}

TRADING_THEMES = {
    "🔥 SEMICONDUCTORS": ["NVDA", "AMD", "AVGO", "TSM", "ARM", "MU", "SMCI"],
    "☁️ SOFTWARE / AI": ["MSFT", "PLTR", "CRM", "CRWD", "NOW", "ORCL", "ADBE"],
    "🖥️ BIG TECH": ["AAPL", "GOOGL", "META", "AMZN", "NFLX", "TSLA"],
    "🪙 CRYPTO / BTC": ["COIN", "MSTR", "MARA", "RIOT", "CLSK", "IBIT", "BTC-USD"],
    "🚀 SPACE / GROWTH": ["RKLB", "ASTS", "PLTR", "OKLO", "RIVN"]
}

MAG7_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
DEFAULT_NEWS_SYMS = ["SPY", "NVDA", "TSLA", "BTC-USD"]

# Integrity Check: Ensure all symbols are uppercase and unique
all_raw = list(GLOBAL_TICKERS.values()) + [s for t in TRADING_THEMES.values() for s in t] + MAG7_TICKERS + DEFAULT_NEWS_SYMS
ALL_SYMBOLS = sorted(list(set([s.upper() for s in all_raw])))

# ────────────────────────────────────────────────
#  3. ASYNC ENGINE: QUOTES & NEWS
# ────────────────────────────────────────────────

async def fetch_async(session, url):
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200: return await response.json()
            return None
    except: return None

async def get_market_package(symbols, news_tickers):
    async with aiohttp.ClientSession() as session:
        # Quote Tasks
        q_tasks = [fetch_async(session, f"https://finnhub.io/api/v1/quote?symbol={s.replace('^', '').split('=')[0]}&token={FINNHUB_KEY}") for s in symbols]
        
        # News Tasks (Last 24 Hours)
        to_date = datetime.datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        n_tasks = [fetch_async(session, f"https://finnhub.io/api/v1/company-news?symbol={s}&from={from_date}&to={to_date}&token={FINNHUB_KEY}") for s in news_tickers]
        
        results = await asyncio.gather(*(q_tasks + n_tasks))
        return results[:len(symbols)], results[len(symbols):]

@st.cache_data(ttl=15)
def fetch_terminal_data(news_focus):
    # Batch technicals from YFinance
    intra = yf.download(ALL_SYMBOLS, period="3d", interval="1m", prepost=True, progress=False)
    hist = yf.download(ALL_SYMBOLS, period="20d", interval="1d", progress=False)
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    q_data, n_data = loop.run_until_complete(get_market_package(ALL_SYMBOLS, news_focus))
    
    rows = []
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.datetime.now(tz).strftime('%Y-%m-%d')
    quotes = dict(zip(ALL_SYMBOLS, q_data))

    for sym in ALL_SYMBOLS:
        try:
            q = quotes.get(sym)
            price = q['c'] if q and q.get('c') else intra['Close'][sym].dropna().iloc[-1]
            prev_close = q['pc'] if q and q.get('pc') else hist['Close'][sym].dropna().iloc[-2]
            change = ((price - prev_close) / prev_close * 100)
            
            # RVOL Calculation
            try:
                today_vol = intra['Volume'][sym].loc[today_str].sum()
                avg_vol = hist['Volume'][sym].iloc[-15:-2].mean()
                rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            except: rvol = 1.0

            rows.append({"Symbol": sym, "Price": price, "Change %": round(change, 2), "RVOL": round(rvol, 2)})
        except: continue
        
    return pd.DataFrame(rows), n_data

# ────────────────────────────────────────────────
#  4. SIDEBAR & SETTINGS
# ────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Terminal Settings")
    
    # SAFETY: Only allow defaults that exist in ALL_SYMBOLS to prevent StreamlitAPIException
    safe_defaults = [s for s in DEFAULT_NEWS_SYMS if s in ALL_SYMBOLS]
    news_focus = st.multiselect("News Focus", options=ALL_SYMBOLS, default=safe_defaults)
    
    st.divider()
    if st.button("Refresh Terminal", use_container_width=True): 
        st.cache_data.clear()
        st.rerun()

market_df, raw_news = fetch_terminal_data(news_focus)

# ────────────────────────────────────────────────
#  5. MAIN UI
# ────────────────────────────────────────────────
st.title("🏛️ Alpha Terminal Pro")

# --- TOP STATS ---
with st.container(border=True):
    c1, c2, c3 = st.columns([2, 1, 1])
    spy_chg = market_df[market_df['Symbol'] == 'SPY']['Change %'].values[0] if 'SPY' in market_df['Symbol'].values else 0
    with c1:
        st.subheader("📝 Morning Battle Plan")
        bias = "🚀 Risk-On" if spy_chg > 0.4 else "📉 Risk-Off" if spy_chg < -0.4 else "⚖️ Neutral"
        st.markdown(f"**Bias:** {bias} | **Market Regime:** {'Trend Following' if abs(spy_chg) > 0.5 else 'Mean Reversion'}")
    with c2:
        vix = market_df[market_df['Symbol'] == '^VIX']['Price'].values[0] if '^VIX' in market_df['Symbol'].values else 20
        st.metric("Volatility (VIX)", f"{vix:.2f}", delta="High Vol" if vix > 22 else "Low Vol", delta_color="inverse")
    with c3:
        st.metric("S&P 500 Change", f"{spy_chg}%", delta=f"{spy_chg}%")

# --- TABS ---
tabs = st.tabs(["📊 Overview", "🎯 Themes", "⚖️ Alpha Delta", "📰 Live News", "📊 GEX", "💼 Portfolio"])

with tabs[0]: # Overview
    st.dataframe(market_df[market_df['Symbol'].isin(GLOBAL_TICKERS.values())].style.background_gradient(cmap='RdYlGn', subset=['Change %']), hide_index=True, use_container_width=True)

with tabs[1]: # Themes
    t_cols = st.columns(len(TRADING_THEMES))
    for i, (name, syms) in enumerate(TRADING_THEMES.items()):
        with t_cols[i]:
            st.markdown(f"**{name}**")
            theme_view = market_df[market_df['Symbol'].isin([s.upper() for s in syms])][['Symbol', 'Change %']]
            st.dataframe(theme_view.style.background_gradient(cmap='RdYlGn'), hide_index=True)

with tabs[2]: # Alpha Delta
    market_df['Alpha'] = market_df['Change %'] - spy_chg
    fig_rs = px.bar(market_df[market_df['Symbol'].isin([s for t in TRADING_THEMES.values() for s in t])].sort_values('Alpha'), 
                    x='Symbol', y='Alpha', color='Alpha', color_continuous_scale='RdYlGn', title="Relative Strength vs SPY")
    st.plotly_chart(fig_rs, use_container_width=True)

with tabs[3]: # News
    st.subheader("📰 Finnhub Live Wire")
    if raw_news:
        all_news = [item for sublist in raw_news if sublist for item in sublist]
        sorted_news = sorted(all_news, key=lambda x: x['datetime'], reverse=True)
        for item in sorted_news[:20]:
            with st.container(border=True):
                h = item['headline'].lower()
                sentiment = "🟢" if any(w in h for w in ['surge', 'buy', 'beat', 'growth', 'upgrade']) else "🔴" if any(w in h for w in ['slump', 'miss', 'fall', 'cut', 'downgrade']) else "⚪"
                st.markdown(f"{sentiment} **{item['related']}** | {datetime.datetime.fromtimestamp(item['datetime']).strftime('%H:%M')} | *{item['source']}*")
                st.markdown(f"#### [{item['headline']}]({item['url']})")

with tabs[4]: # Gamma GEX
    target = st.text_input("GEX Strike Analysis", "SPY").upper()
    try:
        tk = yf.Ticker(target)
        spot = tk.history(period="1d")['Close'].iloc[-1]
        opt = tk.option_chain(tk.options[0])
        df_opt = pd.concat([opt.calls.assign(type='call'), opt.puts.assign(type='put')])
        df_opt['GEX'] = df_opt['openInterest'] * (df_opt['strike'] - spot) * np.where(df_opt['type']=='call', 1, -1)
        fig_gex = px.bar(df_opt.groupby('strike')['GEX'].sum().reset_index(), x='strike', y='GEX', title=f"{target} Gamma Profile")
        fig_gex.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text="SPOT")
        st.plotly_chart(fig_gex, use_container_width=True)
    except: st.error("Options data unavailable for this ticker.")

with tabs[5]: # Portfolio
    if 'cash' not in st.session_state: st.session_state.cash = 100000.0
    if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
    
    p1, p2, p3 = st.columns([2,1,1])
    s_sym = p1.selectbox("Select Asset", ALL_SYMBOLS)
    s_qty = p2.number_input("Quantity", min_value=1, value=10)
    s_price = market_df[market_df['Symbol'] == s_sym]['Price'].values[0] if not market_df[market_df['Symbol'] == s_sym].empty else 0
    
    if p3.button("Execute Trade", use_container_width=True):
        cost = s_qty * s_price
        if st.session_state.cash >= cost:
            st.session_state.cash -= cost
            pos = st.session_state.portfolio.get(s_sym, {'qty': 0, 'avg': 0})
            st.session_state.portfolio[s_sym] = {'qty': pos['qty'] + s_qty, 'avg': ((pos['qty']*pos['avg']) + cost)/(pos['qty'] + s_qty)}
            st.success(f"Bought {s_qty} {s_sym} @ ${s_price}")
            st.rerun()
    
    st.divider()
    st.metric("Available Cash", f"${st.session_state.cash:,.2f}")
    st.write("**Current Positions:**", st.session_state.portfolio)

# Pulse refresh
st_autorefresh(interval=30000, key="terminal_refresh")
