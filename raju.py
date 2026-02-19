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
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm

# ========================== PAGE CONFIG ==========================
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ========================== PASSWORD PROTECTION ==========================
def check_password():
    if st.session_state.get("password_correct"): return True
    def password_entered():
        if st.session_state["password"] == "Pratimap9!@":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else: st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.title("🔐 Pro Market Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Access Denied")
        return False
    return True

if not check_password(): st.stop()

# ========================== TICKER CONFIGS ==========================
GLOBAL_TICKERS = {"S&P 500 (ES)": "ES=F", "Nasdaq (NQ)": "NQ=F", "Dow (YM)": "YM=F", "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"}
SECTOR_TICKERS = {"Tech (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV", "Disc (XLY)": "XLY", "Indus (XLI)": "XLI", "Utils (XLU)": "XLU", "RE": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"}
MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **MAG7_TICKERS}
TIER_1_BANKS = ["Goldman Sachs", "Morgan Stanley", "JPMorgan", "Bank of America", "Citigroup", "Barclays", "UBS", "Wells Fargo", "Deutsche Bank"]

# ========================== STABLE PCR FETCH (NO THREADING) ==========================
def get_pcr_data():
    targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ"}
    results = []
    for label, sym in targets.items():
        try:
            tk = yf.Ticker(sym)
            cv = pv = 0
            opts = tk.options
            if opts:
                for exp in opts[:2]:
                    ch = tk.option_chain(exp)
                    cv += ch.calls['volume'].sum()
                    pv += ch.puts['volume'].sum()
                pcr = pv / cv if cv > 0 else 0
                results.append({
                    "Asset": label, 
                    "PCR": round(pcr, 2), 
                    "Sentiment": "🐂 Bull" if pcr < 0.85 else "🐻 Bear" if pcr > 1.15 else "⚖️ Neu"
                })
        except: continue
    return pd.DataFrame(results)

# ========================== SENTIMENT ENGINE ==========================
def get_sentiment_score(text):
    bull_words = ['upbeat', 'growth', 'surge', 'rally', 'beat', 'buy', 'bullish', 'expansion', 'profit', 'gain', 'positive', 'jump']
    bear_words = ['slump', 'drop', 'fall', 'miss', 'sell', 'bearish', 'contraction', 'loss', 'negative', 'inflation', 'fear', 'risk', 'sink']
    score = 0
    text = text.lower()
    for word in bull_words:
        if word in text: score += 1
    for word in bear_words:
        if word in text: score -= 1
    if score > 0: return "🟢 Bullish", score
    if score < 0: return "🔴 Bearish", score
    return "⚪ Neutral", 0

# ========================== MATH HELPERS ==========================
def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return np.where(types == 'call', val, -val)

@st.cache_data(ttl=45)
def fetch_market_snapshot():
    symbols = list(ALL_TICKERS.values())
    data = yf.download(symbols, period="5d", interval="1d", progress=False)
    intra = yf.download(symbols, period="1d", interval="5m", prepost=True, progress=False)
    rows = []
    for label, sym in ALL_TICKERS.items():
        try:
            price = intra['Close'][sym].dropna().iloc[-1]
            prev_close = data['Close'][sym].iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            today_vol = intra['Volume'][sym].sum()
            avg_vol = data['Volume'][sym].iloc[-5:-1].mean()
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            rows.append({"Asset": label, "Symbol": sym, "Price": price, "Change %": change, "RVOL": rvol})
        except: continue
    return pd.DataFrame(rows)

# ========================== IMPROVED NEWS ENGINE ==========================
def get_finviz_news_stable():
    """Fetches news from Finviz using the library with a custom scraper fallback."""
    try:
        # Attempt 1: Using the finvizfinance library
        f_news = News().get_news()
        return f_news['news'][:15]
    except Exception:
        # Attempt 2: Direct Scraper Fallback if library fails
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            url = "https://finviz.com/news.ashx"
            response = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            news_list = []
            # Find the news table (class is often 'news')
            rows = soup.find_all('tr', class_='nn')
            for row in rows[:15]:
                link_tag = row.find('a', class_='nn-tab-link')
                source_tag = row.find('td', class_='nn-date') # often contains source/time
                if link_tag:
                    news_list.append({
                        'Title': link_tag.text,
                        'URL': link_tag['href'],
                        'Source': source_tag.text if source_tag else "Finviz",
                        'Date': "Live"
                    })
            return news_list
        except:
            return []

def get_sentiment_score(text):
    bull_words = ['upbeat', 'growth', 'surge', 'rally', 'beat', 'buy', 'bullish', 'expansion', 'profit', 'gain', 'positive', 'jump']
    bear_words = ['slump', 'drop', 'fall', 'miss', 'sell', 'bearish', 'contraction', 'loss', 'negative', 'inflation', 'fear', 'risk', 'sink']
    score = 0
    text = text.lower()
    for word in bull_words:
        if word in text: score += 1
    for word in bear_words:
        if word in text: score -= 1
    
    if score > 0: return "🟢 Bullish", score
    if score < 0: return "🔴 Bearish", score
    return "⚪ Neutral", 0

# ========================== UPDATED TAB 5 ==========================
with tab5:
    st.subheader("📰 Market News & Sentiment")
    
    # Use the stable fetcher
    headlines = get_finviz_news_stable()
    
    if headlines:
        total_score = 0
        for item in headlines:
            label, score = get_sentiment_score(item['Title'])
            total_score += score
            
            with st.expander(f"{label} | {item['Title']}"):
                st.write(f"**Source:** {item.get('Source', 'Finviz')}")
                st.write(f"[Full Story]({item['URL']})")
        
        # Sidebar pulse update
        st.sidebar.divider()
        st.sidebar.metric("Sentiment Pulse", total_score, 
                          delta="Positive" if total_score >= 0 else "Negative")
    else:
        st.error("News feed currently unavailable. Finviz might be limiting requests.")

# ... [Keep rest of the GEX and Alpha Sector code] ...

# ========================== MAIN UI ==========================
market_df = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Performance: STABLE")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔥 Alpha Sectors", "📊 GEX", "🐳 Options", "🎯 Institutional", "📰 News Wire"])

with tab1:
    sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    st.dataframe(sect_data[['Asset', 'Price', 'Change %', 'RVOL']].style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)

with tab2:
    gex_ticker = st.selectbox("Analyze GEX", ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"])
    tk = yf.Ticker(gex_ticker)
    spot = tk.history(period="1d")['Close'].iloc[-1]
    all_chains = []
    for exp in tk.options[:2]:
        try:
            ch = tk.option_chain(exp)
            c, p = ch.calls, ch.puts
            c['type'], p['type'], c['exp'], p['exp'] = 'call', 'put', exp, exp
            all_chains.extend([c, p])
        except: continue
    if all_chains:
        df_g = pd.concat(all_chains)
        df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365
        df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'].values, df_g['dte'].values, df_g['impliedVolatility'].values, 0.04, 0.01, df_g['type'].values, df_g['openInterest'].values)
        df_agg = df_g.groupby('strike')['GEX'].sum() / 1e6
        fig_gex = go.Figure(go.Bar(x=df_agg.index, y=df_agg.values, marker_color=['green' if x > 0 else 'red' for x in df_agg.values]))
        fig_gex.add_vline(x=spot, line_dash="dash", line_color="white")
        fig_gex.update_layout(template="plotly_dark", title=f"{gex_ticker} Net Gamma Walls")
        st.plotly_chart(fig_gex, use_container_width=True)

with tab3:
    st.subheader("🐳 Put/Call Volume Ratio")
    pcr_df = get_pcr_data()
    if not pcr_df.empty:
        st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True, use_container_width=True)
    else:
        st.info("Gathering options flow...")

with tab4:
    st.subheader("🎯 Analyst Activity")
    target_analyst = st.selectbox("Analyst Focus", list(MAG7_TICKERS.keys()))
    try:
        recs = yf.Ticker(MAG7_TICKERS[target_analyst]).recommendations
        if recs is not None and not recs.empty:
            st.dataframe(recs.tail(10), use_container_width=True)
    except: st.info("No analyst data.")

with tab5:
    st.subheader("📰 Market News & Sentiment")
    try:
        headlines = News().get_news()['news'][:15]
        total_score = 0
        for item in headlines:
            label, score = get_sentiment_score(item['Title'])
            total_score += score
            with st.expander(f"{label} | {item['Title']}"):
                st.write(f"Source: {item['Source']} | [Full Story]({item['URL']})")
        st.sidebar.metric("Sentiment Pulse", total_score)
    except: st.error("News feed busy.")

st_autorefresh(interval=30000, key="global_refresh")
