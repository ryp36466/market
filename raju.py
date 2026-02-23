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
#  2. TICKER DEFINITIONS
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
DEFAULT_NEWS_SYMS = ["SPY", "NVDA", "TSLA", "BTC-USD", "SMH", "QQQ"]

all_raw = list(GLOBAL_TICKERS.values()) + [s for t in TRADING_THEMES.values() for s in t] + MAG7_TICKERS + DEFAULT_NEWS_SYMS
ALL_SYMBOLS = sorted(list(set([s.upper() for s in all_raw])))

# ────────────────────────────────────────────────
#  3. ASYNC ENGINE
# ────────────────────────────────────────────────
async def fetch_async(session, url):
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200: return await response.json()
            return None
    except: return None

async def get_market_package(symbols, news_tickers):
    async with aiohttp.ClientSession() as session:
        q_tasks = [fetch_async(session, f"https://finnhub.io/api/v1/quote?symbol={s.replace('^', '').split('=')[0]}&token={FINNHUB_KEY}") for s in symbols]
        to_date = datetime.datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        n_tasks = [fetch_async(session, f"https://finnhub.io/api/v1/company-news?symbol={s}&from={from_date}&to={to_date}&token={FINNHUB_KEY}") for s in news_tickers]
        results = await asyncio.gather(*(q_tasks + n_tasks))
        return results[:len(symbols)], results[len(symbols):]

@st.cache_data(ttl=15)
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
            
            try:
                today_vol = intra['Volume'][sym].loc[today_str].sum()
                avg_vol = hist['Volume'][sym].iloc[-15:-2].mean()
                rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            except: rvol = 1.0

            rows.append({"Symbol": sym, "Price": price, "Change %": round(change, 2), "RVOL": round(rvol, 2)})
        except: continue
        
    return pd.DataFrame(rows), n_data

# ────────────────────────────────────────────────
#  SENTIMENT
# ────────────────────────────────────────────────
def get_sentiment_score(text):
    bull = ['upbeat','growth','surge','rally','beat','buy','bullish','expansion','profit','gain','positive','jump','upgrade','raise','strong','outperform','higher','rise','soar']
    bear = ['slump','drop','fall','miss','sell','bearish','contraction','loss','negative','inflation','fear','risk','sink','downgrade','cut','weak','underperform','lower','decline','plunge']
    score = sum(1 for w in bull if w in text.lower()) - sum(1 for w in bear if w in text.lower())
    if score > 2: return "🟢 Bullish", score
    if score < -2: return "🔴 Bearish", score
    if score > 0: return "🟡 Mild Bull", score
    if score < 0: return "🟠 Mild Bear", score
    return "⚪ Neutral", 0

# ────────────────────────────────────────────────
#  FINVIZ 24-HOUR NEWS (STOCK SPECIFIC + TIME FILTER)
# ────────────────────────────────────────────────
@st.cache_data(ttl=180)
def get_finviz_news_24h():
    news = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    now_est = datetime.datetime.now(pytz.timezone('US/Eastern'))

    for sym in ALL_SYMBOLS[:25]:   # limit to avoid too many requests
        try:
            url = f"https://finviz.com/quote.ashx?t={sym}"
            r = requests.get(url, headers=headers, timeout=8)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", class_="news-table")
            if not table: continue

            for row in table.find_all("tr")[:10]:
                tds = row.find_all("td")
                if len(tds) < 2: continue
                time_str = tds[0].text.strip()
                a = tds[1].find("a")
                if not a: continue
                title = a.text.strip()
                link = a.get("href")
                if not link.startswith("http"): link = "https://finviz.com" + link

                # Parse Finviz time and filter last 24 hours
                try:
                    if 'ago' in time_str:
                        hours = int(time_str.split('h')[0].strip())
                        parsed = now_est - datetime.timedelta(hours=hours)
                    elif 'Yesterday' in time_str:
                        parsed = now_est - datetime.timedelta(days=1)
                    else:
                        dt = datetime.datetime.strptime(time_str, '%I:%M %p')
                        parsed = now_est.replace(hour=dt.hour, minute=dt.minute, second=0, microsecond=0)
                    
                    if (now_est - parsed).total_seconds() / 3600 > 24:
                        continue  # skip older than 24h
                except:
                    continue

                label, score = get_sentiment_score(title)
                
                news.append({
                    "Asset": sym,
                    "Title": title,
                    "URL": link,
                    "Time": time_str,
                    "Sentiment": label,
                    "Score": score
                })
        except:
            continue

    df = pd.DataFrame(news)
    if not df.empty:
        df = df.sort_values("Score", ascending=False).drop_duplicates("Title").head(50)
    return df

# ────────────────────────────────────────────────
#  FETCH DATA
# ────────────────────────────────────────────────
news_focus = ["SPY", "NVDA", "TSLA", "BTC-USD", "SMH", "QQQ"]
market_df, raw_news = fetch_terminal_data(news_focus)
finviz_news_df = get_finviz_news_24h()

# ────────────────────────────────────────────────
#  SIDEBAR
# ────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    news_focus = st.multiselect("Finnhub News Focus", options=ALL_SYMBOLS, default=news_focus)
    st.divider()
    if st.button("Refresh Terminal", use_container_width=True): 
        st.cache_data.clear()
        st.rerun()

# ────────────────────────────────────────────────
#  UI
# ────────────────────────────────────────────────
st.title("🏛️ Alpha Terminal Pro")

# Top Stats (kept from your code)
with st.container(border=True):
    c1, c2, c3 = st.columns([2, 1, 1])
    spy_chg = market_df[market_df['Symbol'] == 'SPY']['Change %'].values[0] if 'SPY' in market_df['Symbol'].values else 0
    with c1:
        st.subheader("📝 Morning Battle Plan")
        bias = "🚀 Risk-On" if spy_chg > 0.4 else "📉 Risk-Off" if spy_chg < -0.4 else "⚖️ Neutral"
        st.markdown(f"**Bias:** {bias}")
    with c2:
        vix = market_df[market_df['Symbol'] == '^VIX']['Price'].values[0] if '^VIX' in market_df['Symbol'].values else 20
        st.metric("VIX", f"{vix:.2f}")
    with c3:
        st.metric("S&P 500", f"{spy_chg}%")

tabs = st.tabs(["📊 Overview", "🎯 Themes", "⚖️ Alpha Delta", "📰 Finnhub News", "📰 Finviz 24h News", "📊 GEX", "💼 Portfolio"])

with tabs[0]:
    st.dataframe(market_df[market_df['Symbol'].isin(GLOBAL_TICKERS.values())].style.background_gradient(cmap='RdYlGn', subset=['Change %']), hide_index=True, use_container_width=True)

with tabs[1]:
    t_cols = st.columns(len(TRADING_THEMES))
    for i, (name, syms) in enumerate(TRADING_THEMES.items()):
        with t_cols[i]:
            st.markdown(f"**{name}**")
            theme_view = market_df[market_df['Symbol'].isin([s.upper() for s in syms])][['Symbol', 'Change %']]
            st.dataframe(theme_view.style.background_gradient(cmap='RdYlGn'), hide_index=True)

with tabs[2]:
    market_df['Alpha'] = market_df['Change %'] - spy_chg
    fig_rs = px.bar(market_df[market_df['Symbol'].isin([s for t in TRADING_THEMES.values() for s in t])].sort_values('Alpha'), 
                    x='Symbol', y='Alpha', color='Alpha', color_continuous_scale='RdYlGn', title="Relative Strength vs SPY")
    st.plotly_chart(fig_rs, use_container_width=True)

with tabs[3]:
    st.subheader("📰 Finnhub Live Wire (Last 24h)")
    if raw_news:
        all_news = [item for sublist in raw_news if sublist for item in sublist]
        sorted_news = sorted(all_news, key=lambda x: x['datetime'], reverse=True)
        for item in sorted_news[:20]:
            with st.container(border=True):
                h = item['headline'].lower()
                sentiment = "🟢" if any(w in h for w in ['surge', 'buy', 'beat', 'growth', 'upgrade']) else "🔴" if any(w in h for w in ['slump', 'miss', 'fall', 'cut', 'downgrade']) else "⚪"
                st.markdown(f"{sentiment} **{item['related']}** | {datetime.datetime.fromtimestamp(item['datetime']).strftime('%H:%M')} | *{item['source']}*")
                st.markdown(f"#### [{item['headline']}]({item['url']})")

with tabs[4]:
    st.subheader("📰 Finviz 24-Hour News Sentiment")
    st.caption("Stock-specific • Only news from the last 24 hours • Sorted by strongest sentiment")
    if not finviz_news_df.empty:
        for _, row in finviz_news_df.iterrows():
            emoji = "🟢" if "Bull" in row['Sentiment'] else "🔴" if "Bear" in row['Sentiment'] else "⚪"
            with st.expander(f"{emoji} {row['Sentiment']} | {row['Asset']} | {row['Title'][:92]}{'...' if len(row['Title']) > 92 else ''} • {row['Time']}"):
                st.write(f"[🔗 Read full story]({row['URL']})")
    else:
        st.info("No news in last 24 hours or still loading...")

with tabs[5]:
    st.subheader("Options Gamma Profile")
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

with tabs[6]:
    st.subheader("💼 Paper Trading Simulator")
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

st_autorefresh(interval=30000, key="terminal_refresh")
