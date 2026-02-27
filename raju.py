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
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================================================
# PAGE CONFIG
# ================================================
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ================================================
# API KEYS (RECOMMENDATION: Move to st.secrets for production)
# ================================================
FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"
ALPHA_VANTAGE_API_KEY = "Q6Z6I3QPW56O7NWP"

# ================================================
# TICKER CONFIGS + TRADING THEMES
# ================================================
USER_HOT_LIST = [
    "NET", "RDDT", "CRCL", "CRWD", "CRM", "BMNR", "UNH", "SOFI", "APP", "ORCL",
    "RBRK", "MRVL", "ARM", "COIN", "SMCI", "IBM", "AAL", "BA", "SHOP", "LMND",
    "RIVN", "DUOL", "MDB", "HOOD", "TNA", "ADBE", "PLTR", "NOW", "PANW", "GS",
    "SNDK", "OXY", "ALB", "KO", "LLY", "BABA", "GOOGL", "CRWV", "LULU", "ALAB",
    "AVGO", "IREN", "MU", "BIDU", "OKLO", "DELL", "TSM", "RKLB", "MP", "COST",
    "CYNA", "QBTS", "QUBT", "RGTI", "QCOM", "BE", "RBLX", "CIFR", "IBIT", "ASTS",
    "CAT", "FDX", "XOM", "WDC", "SLV", "ZSL", "TQQQ", "STX"
]

GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES (S&P 500 Fut)": "ES=F", "NQ (Nasdaq Fut)": "NQ=F",
    "YM (Dow Fut)": "YM=F", "RTY (Russell 2000)": "RTY=F",
    "SPY": "SPY", "QQQ": "QQQ", "10Y Yield": "^TNX",
    "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
}

SECTOR_TICKERS = {
    "Tech (XLK)": "XLK", "Software (IGV)": "IGV", "Semiconductor (SMH)": "SMH",
    "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV",
    "Disc (XLY)": "XLY", "Indus (XLI)": "XLI", "Utils (XLU)": "XLU",
    "RE": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"
}

NEO_CLOUD_TICKERS = {
    "Nebius": "NBIS", "Vertiv": "VRT", "Arista": "ANET",
    "Supermicro": "SMCI", "Dell": "DELL", "Palantir": "PLTR"
}

MAG7_TICKERS = {
    "Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN",
    "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"
}

TRADING_THEMES = {
    "🔵 SEMICONDUCTORS": ["SMH", "SOXL", "NVDA", "AMD", "AVGO", "QCOM", "INTC", "MU", "MRVL", "TSM", "ARM", "SMCI", "WDC", "ALAB"],
    "🟣 SOFTWARE / SaaS": ["IGV", "MSFT", "CRM", "NOW", "ADBE", "CRWD", "MDB", "PLTR", "RBRK", "ORCL", "IBM"],
    "🟢 NEO CLOUD / AI INFRA": ["CRWD", "NBIS", "APP", "ALAB", "RBRK", "PLTR", "SMCI", "DELL"],
    "🟡 MEGA CAP TECH": ["QQQ", "META", "GOOGL", "AAPL", "AMZN", "MSFT", "NVDA", "TSLA"],
    "🟠 CRYPTO / BTC": ["BTC-USD", "IBIT", "MSTR", "COIN", "CIFR", "IREN", "BMNR", "CRCL"],
    "🟤 SMALL CAPS": ["IWM", "TNA", "QBTS", "RGTI", "ASTS", "OKLO", "TEM"],
    "🔴 CONSUMER / HIGH BETA": ["AMZN", "TSLA", "RBLX", "CVNA", "RIVN", "LULU", "NKE", "DUOL", "AAL"],
    "🏦 FINANCIALS": ["JPM", "SOFI", "HOOD", "LMND", "UNH"],
    "⚡ ENERGY": ["XOM", "OXY", "BE", "OKLO"],
    "🏗️ INDUSTRIALS/SPACE": ["CAT", "BA", "RKLB", "ASTS", "FDX"],
    "🏥 HEALTHCARE": ["LLY", "UNH", "TEM"],
    "🥇 COMMODITIES/METALS": ["GC=F", "SLV", "AGQ", "ZSL", "ALB", "MP"],
    "🔥 USER HOT LIST": USER_HOT_LIST
}

symbol_to_label = {}
for d in [GLOBAL_TICKERS, SECTOR_TICKERS, NEO_CLOUD_TICKERS, MAG7_TICKERS]:
    for label, sym in d.items():
        if sym not in symbol_to_label:
            symbol_to_label[sym] = label
for sublist in TRADING_THEMES.values():
    for sym in sublist:
        if sym not in symbol_to_label:
            symbol_to_label[sym] = sym

ALL_SYMBOLS = list(symbol_to_label.keys())
ANALYST_SYMBOLS = sorted({sym for sublist in TRADING_THEMES.values() for sym in sublist})
MAG7_HOT_SYMBOLS = list(MAG7_TICKERS.values()) + ["SPY", "QQQ"]

# ================================================
# NEWS FILTER + HELPERS
# ================================================
HIGH_IMPACT_KEYWORDS = ["earnings", "eps", "revenue", "guidance", "outlook", "beat", "miss", "raised", "cut", "lowered", "hike", "upgrade", "downgrade", "price target", "pt raised", "pt cut", "acquire", "acquisition", "merger", "buyout", "takeover", "deal", "partnership", "sec", "doj", "lawsuit", "investigation", "probe", "settlement", "antitrust", "sued", "fed", "inflation", "tariff", "sanctions", "regulation", "surge", "plunge", "soar", "collapse", "spike", "jump", "tumble", "slump", "crash", "%"]
LOW_IMPACT_KEYWORDS = ["interview", "opinion", "watch", "preview", "recap", "morning brief", "analysis", "blog", "commentary", "podcast", "video", "roundup", "exclusive"]

def is_high_impact(title):
    t = title.lower()
    if any(kw in t for kw in LOW_IMPACT_KEYWORDS): return False
    if any(kw in t for kw in HIGH_IMPACT_KEYWORDS): return True
    return False

def impact_score(title):
    t = title.lower()
    score = 0
    if any(k in t for k in ["earnings", "eps", "revenue", "guidance"]): score += 5
    if any(k in t for k in ["upgrade", "downgrade", "price target"]): score += 4
    if any(k in t for k in ["acquisition", "merger", "buyout"]): score += 4
    if any(k in t for k in ["lawsuit", "sec", "investigation"]): score += 4
    if "%" in t: score += 3
    if any(k in t for k in ["fed", "inflation", "tariff"]): score += 2
    return score

def get_sentiment_score(text):
    bull = ['upbeat','growth','surge','rally','beat','buy','bullish','expansion','profit','gain','positive','jump','upgrade','raise','strong','outperform','higher','rise','soar']
    bear = ['slump','drop','fall','miss','sell','bearish','contraction','loss','negative','inflation','fear','risk','sink','downgrade','cut','weak','underperform','lower','decline','plunge']
    score = sum(1 for w in bull if w in text.lower()) - sum(1 for w in bear if w in text.lower())
    if score > 2: return "🟢 Bullish", score
    if score < -2: return "🔴 Bearish", score
    if score > 0: return "🟡 Mild Bull", score
    if score < 0: return "🟠 Mild Bear", score
    return "⚪ Neutral", 0

# ================================================
# PARALLEL FINVIZ NEWS SCRAPER
# ================================================
def scrape_single_finviz_news(sym: str, max_news: int = 8) -> list:
    try:
        f_sym = "BTC" if sym == "BTC-USD" else sym.split("=")[0]
        url = f"https://finviz.com/quote.ashx?t={f_sym.upper()}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", class_="news-table")
        if not table: return []
        items = []
        for row in table.find_all("tr")[:max_news]:
            tds = row.find_all("td")
            if len(tds) < 2: continue
            time_str = tds[0].text.strip()
            a_tag = tds[1].find("a")
            if not a_tag or len(a_tag.text.strip()) < 25: continue
            title = a_tag.text.strip()
            if not is_high_impact(title): continue
            link = a_tag.get("href")
            if not link.startswith("http"): link = "https://finviz.com" + link
            label, sent_score = get_sentiment_score(title)
            imp_score = impact_score(title)
            items.append({
                "Asset": symbol_to_label.get(sym, sym),
                "Symbol": sym, "Title": title, "URL": link,
                "Source": "Finviz", "Sentiment": label, "Score": sent_score,
                "Impact": imp_score, "Time": time_str
            })
        return items
    except: return []

@st.cache_data(ttl=180)
def get_finviz_news_bulk(symbols: list, max_stocks: int = 30, max_news_per_stock: int = 8):
    news_items = []
    symbols_to_scrape = symbols[:max_stocks]
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_sym = {executor.submit(scrape_single_finviz_news, sym, max_news_per_stock): sym for sym in symbols_to_scrape}
        for future in as_completed(future_to_sym):
            news_items.extend(future.result())
    df = pd.DataFrame(news_items)
    if not df.empty:
        df = df.sort_values(by=["Impact", "Score"], ascending=False).drop_duplicates(subset=["Title"])
    return df

# ================================================
# CACHED DATA FUNCTIONS
# ================================================
@st.cache_data(ttl=300)
def get_etf_crypto_sentiment():
    proxies = {"S&P 500 (SPY)": "SPY", "Nasdaq (QQQ)": "QQQ", "Bitcoin": "BINANCE:BTCUSDT"}
    results = []
    for name, sym in proxies.items():
        try:
            url = f"https://finnhub.io/api/v1/news-sentiment?symbol={sym}&token={FINNHUB_API_KEY}"
            data = requests.get(url).json()
            bull_pct = data['sentiment']['bullishPercent'] * 100
            buzz = data['buzz']['buzz']
            results.append({
                "Asset": name, "Mood": "🐂 Bullish" if bull_pct > 60 else "🐻 Bearish" if bull_pct < 40 else "⚖️ Neutral",
                "Bullish %": f"{bull_pct:.1f}%", "Buzz": round(buzz, 2)
            })
        except: continue
    return pd.DataFrame(results)

@st.cache_data(ttl=300)
def get_macro_drivers():
    url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
    macro_keywords = ['fed', 'inflation', 'cpi', 'ppi', 'tariff', 'treasury', 'yield', 'geopolitical', 'rate hike']
    drivers = []
    try:
        news_list = requests.get(url).json()
        for item in news_list[:40]:
            title = item.get('headline', '')
            if any(k in title.lower() for k in macro_keywords):
                label, score = get_sentiment_score(title)
                drivers.append({
                    "Headline": title, "Sentiment": label,
                    "Impact": "🔴 High" if score < -1 or score > 1 else "🟡 Mid",
                    "URL": item.get('url')
                })
    except: pass
    return pd.DataFrame(drivers)

@st.cache_data(ttl=15)
def fetch_market_snapshot():
    est = pytz.timezone('US/Eastern')
    now_est = datetime.datetime.now(est)
    today_date = now_est.date()
    
    # Download data with MultiIndex flattening logic to fix KeyError
    hist_data = yf.download(ALL_SYMBOLS, period="10d", interval="1d", progress=False, auto_adjust=True)
    intra = yf.download(ALL_SYMBOLS, period="2d", interval="5m", prepost=True, progress=False, auto_adjust=True)

    if intra.index.tz is None:
        intra = intra.tz_localize('UTC').tz_convert('US/Eastern')
    else:
        intra = intra.tz_convert('US/Eastern')
    
    intra_today = intra[intra.index.date == today_date]
    
    rows = []
    for sym in ALL_SYMBOLS:
        label = symbol_to_label.get(sym, sym)
        try:
            # Check for column existence in MultiIndex structure
            if ('Close', sym) not in intra.columns or ('Close', sym) not in hist_data.columns:
                continue
            
            price = intra[('Close', sym)].dropna().iloc[-1]
            prev_close = hist_data[('Close', sym)].dropna().iloc[-1]
            
            if pd.isna(price) or pd.isna(prev_close) or prev_close <= 0:
                continue
            
            change = ((price - prev_close) / prev_close * 100)
            
            today_vol = intra_today.get(('Volume', sym), pd.Series(dtype=float)).sum()
            avg_vol = hist_data.get(('Volume', sym), pd.Series(dtype=float)).iloc[-8:-1].mean()
            rvol = today_vol / avg_vol if avg_vol and avg_vol > 0 else 1.0
            
            today_open = intra_today.get(('Open', sym), pd.Series(dtype=float)).iloc[0] if not intra_today.get(('Open', sym), pd.Series(dtype=float)).empty else price
            gap_pct = ((today_open - prev_close) / prev_close * 100)
            
            prev_day_change = 0.0
            vol_ratio = 1.0
            close_series = hist_data[('Close', sym)].dropna()
            if len(close_series) >= 3:
                prev_day_change = ((close_series.iloc[-1] - close_series.iloc[-2]) / close_series.iloc[-2] * 100)
                prev_vol = hist_data.get(('Volume', sym), pd.Series(dtype=float)).iloc[-1]
                vol_ratio = today_vol / prev_vol if prev_vol > 0 else 1.0

            rows.append({
                "Asset": label, "Symbol": sym, "Price": round(price, 4),
                "Gap %": round(gap_pct, 2), "Change %": round(change, 2), "RVOL": round(rvol, 2),
                "Prev Day Change %": round(prev_day_change, 2), "Vol Ratio (Today/Prev)": round(vol_ratio, 1)
            })
        except: continue
        
    market_df = pd.DataFrame(rows)
    if market_df.empty:
        # Prevent app crash by returning a valid empty DF with correct columns
        market_df = pd.DataFrame(columns=["Asset", "Symbol", "Price", "Gap %", "Change %", "RVOL", "Prev Day Change %", "Vol Ratio (Today/Prev)"])
        
    return market_df, intra, hist_data

@st.cache_data(ttl=180)
def get_finnhub_econ_calendar():
    today = datetime.datetime.now(pytz.timezone('US/Eastern')).date().strftime('%Y-%m-%d')
    url = f"https://finnhub.io/api/v1/calendar/economic?from={today}&to={today}&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        events = r.json().get('economicCalendar', [])
        items = []
        high_keywords = ['cpi', 'ppi', 'gdp', 'nfp', 'payroll', 'unemployment', 'fomc', 'fed', 'rate decision', 'inflation']
        for e in events:
            event_name = e.get('event', '').lower()
            impact = "🔴 HIGH" if any(k in event_name for k in high_keywords) else "🟡 Medium" if e.get('estimate') else "⚪ Low"
            items.append({
                "Time (ET)": e.get('time', '—'), "Event": e.get('event', '—'), "Actual": e.get('actual', '—'),
                "Estimate": e.get('estimate', '—'), "Previous": e.get('previous', '—'), "Country": e.get('country', '—'),
                "Impact": impact
            })
        return pd.DataFrame(items).sort_values('Time (ET)') if items else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def get_finnhub_general_news():
    url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        news_list = r.json()[:40]
        items = []
        for item in news_list:
            title = item.get('headline', '')
            if len(title) < 20 or not is_high_impact(title): continue
            dt = datetime.datetime.fromtimestamp(item.get('datetime', 0), tz=pytz.UTC).astimezone(pytz.timezone('US/Eastern'))
            label, score = get_sentiment_score(title)
            items.append({
                "Time": dt.strftime('%H:%M'), "Title": title, "Source": item.get('source', 'Finnhub'),
                "URL": item.get('url', ''), "Sentiment": label, "Score": score
            })
        return pd.DataFrame(items).sort_values('Score', ascending=False) if items else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=900)
def get_macro_news():
    try: return News().get_news()['news'].head(25).to_dict('records')
    except: return []

# ================================================
# MAIN APP
# ================================================
market_df, intra_data, hist_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Day-Trader Edition | Last refreshed: {time_now}")

# ────────────────────────────────────────────────
#  SIDEBAR
# ────────────────────────────────────────────────
st.sidebar.title("🚨 LIVE VOLUME SURGE ALERTS")
threshold = st.sidebar.slider("RVOL Surge Threshold (x)", 1.5, 10.0, 3.0, 0.5)

if not market_df.empty:
    alert_df = market_df[(market_df['Symbol'].isin(USER_HOT_LIST)) & (market_df['RVOL'] >= threshold)].copy()
    if not alert_df.empty:
        st.sidebar.success(f"🔥 {len(alert_df)} STOCKS SURGING!")
        st.sidebar.dataframe(alert_df[['Asset', 'Symbol', 'Price', 'Change %', 'RVOL']].sort_values('RVOL', ascending=False), hide_index=True)
    else: st.sidebar.info("✅ No high-volume surges")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Refresh Live Data"):
    fetch_market_snapshot.clear()
    st.rerun()

# ────────────────────────────────────────────────
#  TABS
# ────────────────────────────────────────────────
tab_premarket, tab_overview, tab_sectors, tab_themes, tab_rel_strength, tab_macro, tab_finnhub, tab_news, tab_bias = st.tabs([
    "🌅 Premarket Pulse", "📈 Market Overview", "🔥 Alpha Sectors", "🎯 Trading Themes", 
    "⚖️ Relative Strength", "🌍 Macro News", "🌐 Finnhub Daily Pulse", "📰 High-Impact News", "🔍 Bias & Regime"
])

with tab_premarket:
    st.subheader("🌡️ Premarket Pulse")
    major_symbols = ["SPY", "QQQ", "IWM", "^VIX", "BTC-USD"]
    major_df = market_df[market_df['Symbol'].isin(major_symbols)].copy()
    if not major_df.empty:
        spy_chg = major_df[major_df['Symbol'] == "SPY"]['Change %'].iloc[0] if "SPY" in major_df['Symbol'].values else 0
        major_df['Rel Strength vs SPY'] = (major_df['Change %'] - spy_chg).round(2)
        st.dataframe(major_df.style.background_gradient(cmap='RdYlGn', subset=['Change %']), hide_index=True, use_container_width=True)

with tab_overview:
    st.subheader("🗝️ Key Indices & Mag7")
    key_assets = ["VIX", "ES (S&P 500 Fut)", "NQ (Nasdaq Fut)", "SPY", "QQQ"]
    st.dataframe(market_df[market_df['Asset'].isin(key_assets + list(MAG7_TICKERS.keys()))], hide_index=True, use_container_width=True)

with tab_sectors:
    st.subheader("Major ETFs & Neo Clouds")
    col_a, col_b = st.columns(2)
    with col_a: st.dataframe(market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())], hide_index=True)
    with col_b: st.dataframe(market_df[market_df['Asset'].isin(NEO_CLOUD_TICKERS.keys())], hide_index=True)

with tab_themes:
    st.subheader("🎯 Trading Themes")
    cols = st.columns(2)
    for i, (theme, tickers) in enumerate(TRADING_THEMES.items()):
        with cols[i % 2]:
            st.markdown(f"#### {theme}")
            st.dataframe(market_df[market_df['Symbol'].isin(tickers)], hide_index=True)

with tab_rel_strength:
    st.subheader("⚖️ Relative Strength Analysis")
    try:
        spy_chg = market_df[market_df['Symbol'] == "SPY"]['Change %'].iloc[0]
        sect_df = market_df[market_df['Symbol'].isin(SECTOR_TICKERS.values())].copy()
        sect_df['vs SPY'] = sect_df['Change %'] - spy_chg
        fig = px.bar(sect_df.sort_values('vs SPY'), x='vs SPY', y='Asset', orientation='h', template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    except: st.info("Loading relative strength data...")

with tab_macro:
    st.subheader("🌍 Macro Pulse")
    m_news = get_macro_news()
    for item in m_news[:10]:
        with st.expander(item.get('Title')): st.write(f"[Source: {item.get('Source')}]({item.get('URL')})")

with tab_finnhub:
    st.subheader("🌐 Finnhub Pulse")
    col1, col2 = st.columns(2)
    with col1: st.dataframe(get_finnhub_general_news(), hide_index=True)
    with col2: st.dataframe(get_finnhub_econ_calendar(), hide_index=True)

with tab_news:
    st.subheader("📰 Theme News")
    news_df = get_finviz_news_bulk(ANALYST_SYMBOLS, max_stocks=15)
    if not news_df.empty:
        for _, row in news_df.iterrows():
            with st.expander(f"{row['Sentiment']} | {row['Asset']} | {row['Title']}"): st.write(row['URL'])

with tab_bias:
    st.subheader("🔍 Market Bias")
    def get_bias(chg):
        if chg >= 0.6: return "🟢 Bullish"
        if chg <= -0.6: return "🔴 Bearish"
        return "⚖️ Neutral"
    market_df['Bias'] = market_df['Change %'].apply(get_bias)
    st.dataframe(market_df[['Asset', 'Change %', 'Bias']], hide_index=True)

st_autorefresh(interval=45000, key="global_refresh")
