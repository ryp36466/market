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
#  2. TICKERS & CATEGORIES
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES Fut": "ES=F", "NQ Fut": "NQ=F", "RTY Fut": "RTY=F",
    "SPY": "SPY", "QQQ": "QQQ", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"
}

TRADING_THEMES = {
    "🔥 SEMICONDUCTORS": ["NVDA", "AMD", "AVGO", "TSM", "ARM", "MU", "SMCI"],
    "☁️ SOFTWARE / AI": ["MSFT", "PLTR", "CRM", "CRWD", "NOW", "ORCL", "ADBE"],
    "🖥️ BIG TECH": ["AAPL", "GOOGL", "META", "AMZN", "NFLX", "DELL"],
    "🪙 CRYPTO / BTC": ["COIN", "MSTR", "MARA", "RIOT", "CLSK"],
    "🚀 SPACE / GROWTH": ["RKLB", "ASTS", "OKLO", "RIVN"]
}

MAG7_TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
ALL_SYMBOLS = list(set(list(GLOBAL_TICKERS.values()) + [s for t in TRADING_THEMES.values() for s in t] + MAG7_TICKERS))

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

@st.cache_data(ttl=12)
def fetch_terminal_data(news_focus):
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
            today_vol = intra['Volume'][sym].loc[today_str].sum()
            avg_vol = hist['Volume'][sym].iloc[-15:-2].mean()
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            rows.append({"Symbol": sym, "Price": price, "Change %": round(change, 2), "RVOL": round(rvol, 2)})
        except: continue
        
    return pd.DataFrame(rows), n_data

# ────────────────────────────────────────────────
#  4. APP LAYOUT
# ────────────────────────────────────────────────

# User-definable news focus
with st.sidebar:
    st.header("⚙️ Terminal Settings")
    news_focus = st.multiselect("News Focus", options=ALL_SYMBOLS, default=["SPY", "NVDA", "TSLA", "BTC-USD"])
    if st.button("Manual Refresh"): st.rerun()

market_df, raw_news = fetch_terminal_data(news_focus)

# --- HEADER: BATTLE PLAN ---
st.title("🏛️ Alpha Terminal Pro")
with st.container(border=True):
    c1, c2 = st.columns([3, 1])
    spy_chg = market_df[market_df['Symbol'] == 'SPY']['Change %'].values[0] if 'SPY' in market_df['Symbol'].values else 0
    with c1:
        st.subheader("📝 Morning Battle Plan")
        st.info(f"**Bias:** {'🚀 Risk-On' if spy_chg > 0.4 else '📉 Risk-Off' if spy_chg < -0.4 else '⚖️ Neutral'} | **Strategy:** {'Focus on Tech Breakouts' if spy_chg > 0 else 'Monitor Defensive Rotations'}")
    with c2:
        vix = market_df[market_df['Symbol'] == '^VIX']['Price'].values[0] if '^VIX' in market_df['Symbol'].values else 20
        st.metric("VIX Index", f"{vix:.2f}", delta="Volatile" if vix > 20 else "Calm", delta_color="inverse")

# --- TABS ---
tabs = st.tabs(["📊 Overview", "🎯 Themes", "⚖️ Alpha Delta", "📰 Live News", "📊 GEX", "💼 Portfolio"])

with tabs[0]:
    st.dataframe(market_df[market_df['Symbol'].isin(GLOBAL_TICKERS.values())].style.background_gradient(cmap='RdYlGn', subset=['Change %']), hide_index=True, use_container_width=True)

with tabs[1]:
    t_cols = st.columns(len(TRADING_THEMES))
    for i, (name, syms) in enumerate(TRADING_THEMES.items()):
        with t_cols[i]:
            st.markdown(f"**{name}**")
            st.dataframe(market_df[market_df['Symbol'].isin(syms)][['Symbol', 'Change %']].style.background_gradient(cmap='RdYlGn'), hide_index=True)

with tabs[2]:
    market_df['Alpha'] = market_df['Change %'] - spy_chg
    fig_rs = px.bar(market_df[market_df['Symbol'].isin([s for t in TRADING_THEMES.values() for s in t])].sort_values('Alpha'), x='Symbol', y='Alpha', color='Alpha', color_continuous_scale='RdYlGn')
    st.plotly_chart(fig_rs, use_container_width=True)

with tabs[3]:
    st.subheader("📰 Finnhub Live Wire (24h)")
    if raw_news:
        all_news = [item for sublist in raw_news if sublist for item in sublist]
        sorted_news = sorted(all_news, key=lambda x: x['datetime'], reverse=True)
        for item in sorted_news[:25]:
            with st.container(border=True):
                h_lower = item['headline'].lower()
                sentiment_color = "🟢" if any(w in h_lower for w in ['surge', 'buy', 'beat', 'growth']) else "🔴" if any(w in h_lower for w in ['slump', 'miss', 'fall', 'cut']) else "⚪"
                col_n1, col_n2 = st.columns([1, 15])
                col_n1.write(sentiment_color)
                with col_n2:
                    st.markdown(f"**{item['related']}** | {datetime.datetime.fromtimestamp(item['datetime']).strftime('%H:%M:%S')} | *{item['source']}*")
                    st.markdown(f"#### [{item['headline']}]({item['url']})")

with tabs[4]:
    target = st.text_input("GEX Strike Analysis", "SPY").upper()
    try:
        tk = yf.Ticker(target)
        spot = tk.history(period="1d")['Close'].iloc[-1]
        opt = tk.option_chain(tk.options[0])
        df_opt = pd.concat([opt.calls.assign(type='call'), opt.puts.assign(type='put')])
        df_opt['GEX'] = df_opt['openInterest'] * (df_opt['strike'] - spot) * np.where(df_opt['type']=='call', 1, -1)
        fig_gex = px.bar(df_opt.groupby('strike')['GEX'].sum().reset_index(), x='strike', y='GEX', title=f"{target} Gamma Wall Estimation")
        fig_gex.add_vline(x=spot, line_dash="dash", line_color="white")
        st.plotly_chart(fig_gex, use_container_width=True)
    except: st.error("Options data unavailable.")

with tabs[5]:
    st.subheader("💼 Paper Trading")
    if 'cash' not in st.session_state: st.session_state.cash = 100000.0
    if 'portfolio' not in st.session_state: st.session_state.portfolio = {}
    
    tp1, tp2, tp3 = st.columns([2,1,1])
    s_sym = tp1.selectbox("Ticker", ALL_SYMBOLS)
    s_qty = tp2.number_input("Qty", min_value=1, value=10)
    s_price = market_df[market_df['Symbol'] == s_sym]['Price'].values[0] if not market_df[market_df['Symbol'] == s_sym].empty else 0
    
    if tp3.button("EXECUTE BUY", use_container_width=True):
        cost = s_qty * s_price
        if st.session_state.cash >= cost:
            st.session_state.cash -= cost
            pos = st.session_state.portfolio.get(s_sym, {'qty': 0, 'avg': 0})
            st.session_state.portfolio[s_sym] = {'qty': pos['qty'] + s_qty, 'avg': ((pos['qty']*pos['avg']) + cost)/(pos['qty'] + s_qty)}
            st.rerun()
    st.metric("Buying Power", f"${st.session_state.cash:,.2f}")
    st.write(st.session_state.portfolio)

# Pulse
st_autorefresh(interval=30000, key="global_refresh")
