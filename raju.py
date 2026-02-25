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

# Build symbol → label mapping
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

HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO',
    'HD', 'COST', 'NFLX', 'DIS', 'PFE', 'MRK', 'LLY', 'AVGO'
}

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
# PARALLEL FINVIZ NEWS SCRAPER (Major Speed Boost)
# ================================================
def scrape_single_finviz_news(sym: str, max_news: int = 8) -> list:
    try:
        f_sym = "BTC" if sym == "BTC-USD" else sym.split("=")[0]
        url = f"https://finviz.com/quote.ashx?t={f_sym.upper()}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", class_="news-table")
        if not table:
            return []
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
            if not link.startswith("http"):
                link = "https://finviz.com" + link
            label, sent_score = get_sentiment_score(title)
            imp_score = impact_score(title)
            items.append({
                "Asset": symbol_to_label.get(sym, sym),
                "Symbol": sym,
                "Title": title,
                "URL": link,
                "Source": "Finviz",
                "Sentiment": label,
                "Score": sent_score,
                "Impact": imp_score,
                "Time": time_str
            })
        return items
    except:
        return []

@st.cache_data(ttl=180)
def get_finviz_news_bulk(symbols: list, max_stocks: int = 30, max_news_per_stock: int = 8):
    news_items = []
    symbols_to_scrape = symbols[:max_stocks]
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_sym = {executor.submit(scrape_single_finviz_news, sym, max_news_per_stock): sym 
                         for sym in symbols_to_scrape}
        for future in as_completed(future_to_sym):
            news_items.extend(future.result())
    df = pd.DataFrame(news_items)
    if not df.empty:
        df = df.sort_values(by=["Impact", "Score"], ascending=False).drop_duplicates(subset=["Title"])
    return df

# ================================================
# CACHED DATA FUNCTIONS (Optimized)
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
                "Asset": name,
                "Mood": "🐂 Bullish" if bull_pct > 60 else "🐻 Bearish" if bull_pct < 40 else "⚖️ Neutral",
                "Bullish %": f"{bull_pct:.1f}%",
                "Buzz": round(buzz, 2)
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
                    "Headline": title,
                    "Sentiment": label,
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
            tk = yf.Ticker(sym)
            fast = tk.fast_info
            price = fast.get('lastPrice') or fast.get('regularMarketPrice') or fast.get('previousClose')
            prev_close = fast.get('regularMarketPreviousClose') or fast.get('previousClose')
            if price is None or prev_close is None or prev_close <= 0:
                continue
            price = float(price)
            prev_close = float(prev_close)
            change = ((price - prev_close) / prev_close * 100)
            
            vol_col = ('Volume', sym)
            today_vol_series = intra_today.get(vol_col, pd.Series(dtype=float))
            today_vol = today_vol_series.sum() if not today_vol_series.empty else 0.0
            
            hist_vol_series = hist_data.get(('Volume', sym), pd.Series(dtype=float))
            avg_vol = hist_vol_series.iloc[-8:-1].mean() if len(hist_vol_series) >= 8 else 1.0
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            
            open_col = ('Open', sym)
            open_series = intra_today.get(open_col, pd.Series(dtype=float))
            today_open = open_series.iloc[0] if not open_series.empty else price
            gap_pct = ((today_open - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

            # Previous day price action & volume
            close_series = hist_data.get(('Close', sym), pd.Series(dtype=float))
            vol_series = hist_data.get(('Volume', sym), pd.Series(dtype=float))
            prev_day_change = 0.0
            prev_vol = 1.0
            vol_ratio = 1.0
            if len(close_series) >= 2:
                p_close = close_series.iloc[-2]
                pp_close = close_series.iloc[-3] if len(close_series) >= 3 else p_close
                prev_day_change = ((p_close - pp_close) / pp_close * 100) if pp_close > 0 else 0.0
            if len(vol_series) >= 1:
                prev_vol = vol_series.iloc[-1]
            vol_ratio = today_vol / prev_vol if prev_vol > 0 else 1.0

            rows.append({
                "Asset": label, "Symbol": sym, "Price": round(price, 4),
                "Gap %": round(gap_pct, 2), "Change %": round(change, 2), "RVOL": round(rvol, 2),
                "Prev Day Change %": round(prev_day_change, 2),
                "Vol Ratio (Today/Prev)": round(vol_ratio, 1)
            })
        except:
            continue
    return pd.DataFrame(rows), intra, hist_data

@st.cache_data(ttl=180)
def get_finnhub_econ_calendar():
    today = datetime.datetime.now(pytz.timezone('US/Eastern')).date().strftime('%Y-%m-%d')
    url = f"https://finnhub.io/api/v1/calendar/economic?from={today}&to={today}&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        events = r.json().get('economicCalendar', [])
        items = []
        high_keywords = ['cpi', 'ppi', 'gdp', 'nfp', 'payroll', 'unemployment', 'fomc', 'fed', 'rate decision', 'inflation']
        for e in events:
            event_name = e.get('event', '').lower()
            impact = "🔴 HIGH" if any(k in event_name for k in high_keywords) else "🟡 Medium" if e.get('estimate') else "⚪ Low"
            items.append({
                "Time (ET)": e.get('time', '—'), "Event": e.get('event', '—'),
                "Actual": e.get('actual', '—'), "Estimate": e.get('estimate', '—'),
                "Previous": e.get('previous', '—'), "Country": e.get('country', '—'),
                "Impact": impact
            })
        df = pd.DataFrame(items)
        if df.empty:
            return pd.DataFrame(columns=["Time (ET)", "Event", "Actual", "Estimate", "Previous", "Country", "Impact"])
        return df.sort_values('Time (ET)')
    except:
        return pd.DataFrame(columns=["Time (ET)", "Event", "Actual", "Estimate", "Previous", "Country", "Impact"])

@st.cache_data(ttl=300)
def get_finnhub_general_news():
    url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        news_list = r.json()[:40]
        items = []
        for item in news_list:
            title = item.get('headline', '')
            if len(title) < 20 or not is_high_impact(title): continue
            dt = datetime.datetime.fromtimestamp(item.get('datetime', 0), tz=pytz.UTC)
            est_time = dt.astimezone(pytz.timezone('US/Eastern')).strftime('%H:%M')
            label, score = get_sentiment_score(title)
            items.append({
                "Time": est_time, "Title": title, "Source": item.get('source', 'Finnhub'),
                "URL": item.get('url', ''), "Sentiment": label, "Score": score
            })
        df = pd.DataFrame(items)
        if not df.empty:
            df = df.sort_values('Score', ascending=False)
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=900)
def get_macro_news():
    try:
        return News().get_news()['news'].head(25).to_dict('records')
    except:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get("https://finviz.com/news.ashx", headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", id="news-table")
            if not table: return []
            news_list = []
            for row in table.find_all("tr")[:25]:
                cells = row.find_all("td")
                if len(cells) != 2: continue
                a = cells[1].find("a", class_="tab-link-news")
                if a:
                    news_list.append({"Title": a.text.strip(), "URL": a["href"], "Source": "Finviz", "Date": cells[0].text.strip()})
            return news_list
        except:
            return []

# ================================================
# MAIN APP
# ================================================
market_df, intra_data, hist_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Data as of {datetime.date.today()} | Day-Trader Edition with Macro Pulse | Last refreshed: {datetime.datetime.now(est).strftime('%H:%M:%S')}")

# ────────────────────────────────────────────────
#  SIDEBAR VOLUME SURGE ALERT
# ────────────────────────────────────────────────
st.sidebar.title("🚨 LIVE VOLUME SURGE ALERTS")
threshold = st.sidebar.slider("RVOL Surge Threshold (x)", 1.5, 10.0, 3.0, 0.5)

alert_df = market_df[(market_df['Symbol'].isin(USER_HOT_LIST)) & (market_df['RVOL'] >= threshold)].copy()

if not alert_df.empty:
    alert_df = alert_df.sort_values('RVOL', ascending=False)
    st.sidebar.success(f"🔥 {len(alert_df)} STOCKS SURGING!")
    st.sidebar.dataframe(
        alert_df[['Asset', 'Symbol', 'Price', 'Change %', 'RVOL']]
        .style.background_gradient(cmap='Reds', subset=['RVOL'])
        .format({"Price": "${:,.2f}", "Change %": "{:+.2f}%", "RVOL": "{:.1f}x"}),
        hide_index=True, use_container_width=True
    )
else:
    st.sidebar.info("✅ No high-volume surges right now")

st.sidebar.markdown("---")

col_refresh = st.columns([7, 1])
with col_refresh[1]:
    if st.button("🔄 Refresh Live Data", use_container_width=True):
        fetch_market_snapshot.clear()
        get_finviz_news_bulk.clear()
        st.rerun()

# ────────────────────────────────────────────────
#  TABS (GEX, Options, Earnings, Analyst Ratings removed)
# ────────────────────────────────────────────────
tab_premarket, tab_overview, tab_sectors, tab_themes, tab_rel_strength, tab_macro, tab_finnhub, tab_news, tab_bias = st.tabs([
    "🌅 Premarket Pulse", "📈 Market Overview", "🔥 Alpha Sectors", "🎯 Trading Themes",
    "⚖️ Relative Strength", "🌍 Macro News", "🌐 Finnhub Daily Pulse",
    "📰 High-Impact News", "🔍 Bias & Regime"
])

with tab_premarket:
    st.subheader("🌡️ Premarket Pulse — Major Indices & Market Sentiment")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("#### 📊 Major Indices Snapshot + Relative Strength")
        major_symbols = ["SPY", "QQQ", "IWM", "^VIX", "BTC-USD"]
        major_df = market_df[market_df['Symbol'].isin(major_symbols)].copy()
        
        spy_chg = major_df[major_df['Symbol'] == "SPY"]['Change %'].iloc[0] if not major_df[major_df['Symbol'] == "SPY"].empty else 0
        major_df['Rel Strength vs SPY'] = (major_df['Change %'] - spy_chg).round(2)
        
        st.dataframe(
            major_df[['Asset', 'Price', 'Gap %', 'Change %', 'Rel Strength vs SPY', 'RVOL', 'Prev Day Change %', 'Vol Ratio (Today/Prev)']]
            .style
            .background_gradient(cmap='RdYlGn', subset=['Change %', 'Rel Strength vs SPY', 'RVOL'])
            .format({"Price": "${:,.2f}", "Gap %": "{:+.2f}%", "Change %": "{:+.2f}%", "Rel Strength vs SPY": "{:+.2f}%", "Prev Day Change %": "{:+.2f}%", "Vol Ratio (Today/Prev)": "{:.1f}x"}),
            hide_index=True, use_container_width=True
        )

    with col2:
        st.markdown("#### 🪙 Bitcoin + VIX Market Sentiment")
        sent_df = get_etf_crypto_sentiment()
        st.dataframe(sent_df, hide_index=True, use_container_width=True)

        vix_row = market_df[market_df['Symbol'] == "^VIX"]
        if not vix_row.empty:
            vix_level = vix_row['Price'].iloc[0]
            vix_sent = "🔴 HIGH FEAR" if vix_level > 30 else "🟠 Elevated Fear" if vix_level > 20 else "🟢 Low Fear / Complacent"
            st.metric("VIX Sentiment", vix_sent, f"Level {vix_level:.1f}")

        btc_row = market_df[market_df['Symbol'] == "BTC-USD"]
        if not btc_row.empty:
            st.metric("Bitcoin Strength", f"{btc_row['RVOL'].iloc[0]:.1f}x RVOL", f"{btc_row['Change %'].iloc[0]:+.2f}%")

    st.markdown("---")
    st.subheader("📰 Market Sentiments Based on News (Major Indices)")
    fn_news = get_finnhub_general_news()
    index_keywords = ['s&p', 'spx', 'nasdaq', 'dow', 'vix', 'bitcoin', 'btc']
    index_news = fn_news[fn_news['Title'].str.lower().str.contains('|'.join(index_keywords), na=False)]
    if not index_news.empty:
        for _, row in index_news.head(6).iterrows():
            emoji = "🔥" if row['Score'] >= 2 else "📈"
            with st.expander(f"{emoji} {row['Sentiment']} | {row['Time']} | {row['Title'][:90]}..."):
                st.write(f"**Source:** {row['Source']}")
                if row['URL']:
                    st.write(f"[🔗 Read full story]({row['URL']})")
    else:
        st.info("No major index-specific news right now.")

    st.markdown("---")
    st.subheader("📈 Today vs Previous Day Volume & Price Action")
    st.caption("Compares current premarket session vs the most recent full trading day")
    comp_df = major_df[['Asset', 'Change %', 'Prev Day Change %', 'Vol Ratio (Today/Prev)', 'RVOL']]
    st.dataframe(
        comp_df.style
        .background_gradient(cmap='RdYlGn', subset=['Change %', 'Prev Day Change %'])
        .background_gradient(cmap='Reds', subset=['Vol Ratio (Today/Prev)'])
        .format({"Change %": "{:+.2f}%", "Prev Day Change %": "{:+.2f}%", "Vol Ratio (Today/Prev)": "{:.1f}x"}),
        hide_index=True, use_container_width=True
    )

    st.markdown("---")
    st.subheader("🌍 Macro News Impacting the Market Right Now")
    macro_df = get_macro_drivers()
    if not macro_df.empty:
        for _, row in macro_df.iterrows():
            with st.expander(f"{row['Sentiment']} | {row['Headline'][:80]}..."):
                st.write(f"**Impact:** {row['Impact']}")
                st.write(f"[Read full story]({row['URL']})")
    else:
        st.info("No high-impact macro drivers detected yet.")

with tab_overview:
    st.subheader("🗝️ Key Indices & Futures")
    key_assets = ["VIX", "ES (S&P 500 Fut)", "NQ (Nasdaq Fut)", "YM (Dow Fut)", "RTY (Russell 2000)", "SPY", "QQQ", "S&P 500"]
    key_df = market_df[market_df['Asset'].isin(key_assets)][['Asset', 'Price', 'Gap %', 'Change %', 'RVOL']].round(2)
    st.dataframe(key_df.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'Gap %', 'RVOL']), hide_index=True, use_container_width=True)

    st.subheader("🚀 Magnificent 7")
    mag7_df = market_df[market_df['Asset'].isin(MAG7_TICKERS.keys())].copy().sort_values('Change %', ascending=False)
    spy_change = mag7_df[mag7_df['Asset'] == "SPY"]['Change %'].iloc[0] if not mag7_df[mag7_df['Asset'] == "SPY"].empty else 0
    mag7_df['vs SPY (%)'] = (mag7_df['Change %'] - spy_change).round(2)
    st.dataframe(mag7_df[['Asset', 'Price', 'Change %', 'vs SPY (%)', 'RVOL']].round(2)
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'vs SPY (%)', 'RVOL']),
                 hide_index=True, use_container_width=True)

with tab_sectors:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Major ETFs")
        sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
        st.dataframe(sect_data[['Asset', 'Price', 'Change %', 'RVOL']].style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)
    with col_b:
        st.subheader("☁️ Neo Clouds (AI Infrastructure)")
        neo_data = market_df[market_df['Asset'].isin(NEO_CLOUD_TICKERS.keys())].copy()
        st.dataframe(neo_data[['Asset', 'Price', 'Change %', 'RVOL']].style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)

with tab_themes:
    st.subheader("🎯 Active Trading Themes")
    st.caption("Categorized buckets to identify leading/lagging sectors at the open.")
    cols = st.columns(2)
    for i, (theme, tickers) in enumerate(TRADING_THEMES.items()):
        with cols[i % 2]:
            st.markdown(f"#### {theme}")
            theme_df = market_df[market_df['Symbol'].isin(tickers)].copy()
            if not theme_df.empty:
                theme_df = theme_df.sort_values('Change %', ascending=False)
                st.dataframe(
                    theme_df[['Asset', 'Price', 'Change %', 'RVOL']]
                    .style.background_gradient(cmap='RdYlGn', subset=['Change %'])
                    .format({"Price": "${:,.2f}", "Change %": "{:+.2f}%", "RVOL": "{:.2f}x"}),
                    hide_index=True, use_container_width=True
                )
            else:
                st.warning(f"No data for {theme}")

with tab_rel_strength:
    st.subheader("⚖️ Sector Current Day Strength vs SPY")
    st.caption("Today's performance relative to SPY (since previous close) • Strongest at top")

    try:
        spy_row = market_df[market_df['Asset'] == "SPY"]
        spy_change = spy_row['Change %'].iloc[0] if not spy_row.empty else 0.0

        sector_symbols = list(SECTOR_TICKERS.values())
        sector_df = market_df[market_df['Symbol'].isin(sector_symbols)].copy()
        sector_df['vs SPY (%)'] = (sector_df['Change %'] - spy_change).round(2)

        df_plot = sector_df.sort_values('vs SPY (%)', ascending=False)
        fig = px.bar(
            df_plot,
            x='vs SPY (%)',
            y='Asset',
            orientation='h',
            color='vs SPY (%)',
            color_continuous_scale='RdYlGn',
            title="Sectors Current Day Strength vs SPY",
            template="plotly_dark",
            height=520
        )
        fig.update_layout(
            xaxis_title="Relative Strength vs SPY (%)",
            yaxis_title="",
            xaxis=dict(tickformat=".1f")
        )
        st.plotly_chart(fig, use_container_width=True)

        st.write("### Alpha Delta (Today vs SPY)")
        st.dataframe(
            sector_df[['Asset', 'Price', 'Change %', 'vs SPY (%)', 'RVOL']]
            .sort_values('vs SPY (%)', ascending=False)
            .style.background_gradient(cmap='RdYlGn', subset=['vs SPY (%)', 'Change %'])
            .format({"Price": "${:,.2f}", "Change %": "{:+.2f}%", "vs SPY (%)": "{:+.2f}%", "RVOL": "{:.2f}x"}),
            hide_index=True,
            use_container_width=True
        )
    except Exception as e:
        st.error(f"Sector RS Error: {e}")

    st.markdown("---")

    st.subheader("⚖️ Mag7 Current Day Strength vs QQQ")
    st.caption("Today's performance relative to QQQ • Strongest at top")

    try:
        qqq_row = market_df[market_df['Asset'] == "QQQ"]
        qqq_change = qqq_row['Change %'].iloc[0] if not qqq_row.empty else 0.0

        mag7_symbols = list(MAG7_TICKERS.values())
        mag7_df = market_df[market_df['Symbol'].isin(mag7_symbols)].copy()
        mag7_df['vs QQQ (%)'] = (mag7_df['Change %'] - qqq_change).round(2)

        df_plot = mag7_df.sort_values('vs QQQ (%)', ascending=False)
        fig = px.bar(
            df_plot,
            x='vs QQQ (%)',
            y='Asset',
            orientation='h',
            color='vs QQQ (%)',
            color_continuous_scale='RdYlGn',
            title="Mag7 Current Day Strength vs QQQ",
            template="plotly_dark",
            height=520
        )
        fig.update_layout(
            xaxis_title="Relative Strength vs QQQ (%)",
            yaxis_title="",
            xaxis=dict(tickformat=".1f")
        )
        st.plotly_chart(fig, use_container_width=True)

        st.write("### Alpha Delta (Today vs QQQ)")
        st.dataframe(
            mag7_df[['Asset', 'Price', 'Change %', 'vs QQQ (%)', 'RVOL']]
            .sort_values('vs QQQ (%)', ascending=False)
            .style.background_gradient(cmap='RdYlGn', subset=['vs QQQ (%)', 'Change %'])
            .format({"Price": "${:,.2f}", "Change %": "{:+.2f}%", "vs QQQ (%)": "{:+.2f}%", "RVOL": "{:.2f}x"}),
            hide_index=True,
            use_container_width=True
        )
    except Exception as e:
        st.error(f"Mag7 RS Error: {e}")

with tab_macro:
    st.subheader("🌍 Macro & Market-Moving News")
    st.caption("High-impact news affecting the broader market")
    macro_news = get_macro_news()
    if macro_news:
        total_score = 0
        trump_news = [item for item in macro_news if any(k in item.get('Title','').lower() for k in ['trump', 'president', 'white house', 'tariff', 'election', 'fed', 'inflation'])]
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 📈 All Macro Headlines")
            for item in macro_news[:15]:
                label, score = get_sentiment_score(item.get('Title', ''))
                total_score += score
                with st.expander(f"{label} | {item.get('Title')[:85]}..."):
                    st.write(f"**Source:** {item.get('Source')} | {item.get('Date')}")
                    st.write(f"[🔗 Read]({item.get('URL')})")
        with col2:
            st.markdown("### 🇺🇸 Trump / Political Impact")
            if trump_news:
                for item in trump_news[:10]:
                    label, score = get_sentiment_score(item.get('Title', ''))
                    with st.expander(f"{label} | {item.get('Title')[:80]}..."):
                        st.write(f"**Source:** {item.get('Source')} | {item.get('Date')}")
                        st.write(f"[🔗 Read]({item.get('URL')})")
        st.sidebar.metric("Macro Sentiment Pulse", total_score, delta="Bullish" if total_score >= 0 else "Bearish")
    else:
        st.info("Fetching macro news...")

with tab_finnhub:
    st.subheader("🌐 Finnhub Daily Pulse")
    st.caption("Live general market news + Today's Economic Calendar")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("### 📈 Finnhub Market News (High Impact)")
        fn_df = get_finnhub_general_news()
        if not fn_df.empty:
            for _, row in fn_df.iterrows():
                emoji = "🔥" if row['Score'] >= 2 else "📈"
                with st.expander(f"{emoji} {row['Sentiment']} | {row['Time']} | {row['Title'][:85]}..."):
                    st.write(f"**Source:** {row['Source']}")
                    if row['URL']:
                        st.write(f"[🔗 Read full story]({row['URL']})")
        else:
            st.info("Fetching high-impact news...")
    with col2:
        st.markdown("### 📅 Economic Calendar (Today)")
        econ_df = get_finnhub_econ_calendar()
        if not econ_df.empty:
            st.dataframe(econ_df.style.background_gradient(cmap='RdYlGn_r', subset=['Impact']), hide_index=True, use_container_width=True)
        else:
            st.info("No events today or fetching data...")

with tab_news:
    st.subheader("🔥 Hot Mag7 + SPY/QQQ News")
    st.caption("Market-moving news for the most important assets")
    hot_df = get_finviz_news_bulk(MAG7_HOT_SYMBOLS, max_stocks=20)
    if not hot_df.empty:
        for _, row in hot_df.iterrows():
            impact_emoji = "🔥" if row['Impact'] >= 5 else "⚡" if row['Impact'] >= 3 else "📈"
            with st.expander(f"{impact_emoji} {row['Sentiment']} | {row['Asset']} | {row['Title'][:92]}... • {row['Time']}"):
                st.write(f"**Source:** {row['Source']} | Impact Score: {row['Impact']}")
                st.write(f"[🔗 Read full story]({row['URL']})")
    st.markdown("---")
    st.subheader("📰 High-Impact Theme Stocks News")
    news_df = get_finviz_news_bulk(ANALYST_SYMBOLS, max_stocks=35)
    if not news_df.empty:
        total_score = news_df['Score'].sum()
        st.sidebar.metric("Theme Sentiment Pulse", total_score, delta="Positive" if total_score >= 0 else "Negative")
        for _, row in news_df.iterrows():
            impact_emoji = "🔥" if row['Impact'] >= 5 else "⚡" if row['Impact'] >= 3 else "📈"
            with st.expander(f"{impact_emoji} {row['Sentiment']} | {row['Asset']} | {row['Title'][:92]}... • {row['Time']}"):
                st.write(f"**Source:** {row['Source']} | Impact Score: {row['Impact']}")
                st.write(f"[🔗 Read full story]({row['URL']})")
    else:
        st.info("Fetching high-impact theme news...")

with tab_bias:
    st.subheader("🔍 Market Bias & Gap Analysis")
    st.caption("Bullish / Bearish / Chop regime based on today's price vs yesterday close")
    key_assets = ["VIX", "ES (S&P 500 Fut)", "NQ (Nasdaq Fut)", "YM (Dow Fut)", 
                  "RTY (Russell 2000)", "SPY", "QQQ", "S&P 500"]
    bias_df = market_df[market_df['Asset'].isin(key_assets + list(MAG7_TICKERS.keys()))].copy()
    def get_bias(chg):
        if chg >= 1.8:   return "🚀 Strong Bullish"
        elif chg >= 0.6: return "🟢 Bullish"
        elif chg >= -0.6:return "⚖️ Chop / Neutral"
        elif chg >= -1.8:return "🔴 Bearish"
        else:            return "💥 Strong Bearish"
    bias_df['Bias'] = bias_df['Change %'].apply(get_bias)
    def style_bias(val):
        if "Strong Bullish" in val or "Bullish" in val:
            return 'background-color: #00cc66; color: black; font-weight: bold'
        if "Strong Bearish" in val or "Bearish" in val:
            return 'background-color: #ff4444; color: white; font-weight: bold'
        if "Chop" in val:
            return 'background-color: #555555; color: white'
        return ''
    st.dataframe(
        bias_df[['Asset', 'Price', 'Gap %', 'Change %', 'Bias', 'RVOL']].round(2)
        .style.applymap(style_bias, subset=['Bias'])
        .background_gradient(cmap='RdYlGn', subset=['Change %', 'Gap %'])
        .format({"Gap %": "{:+.2f}%", "Change %": "{:+.2f}%", "RVOL": "{:.2f}x"}),
        hide_index=True, use_container_width=True
    )

# ────────────────────────────────────────────────
#  AUTO-REFRESH
# ────────────────────────────────────────────────
st_autorefresh(interval=45000, key="global_refresh")
