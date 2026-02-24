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

# ================================================
# PAGE CONFIG
# ================================================
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ================================================
# API KEYS
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

@st.cache_data(ttl=20)
def fetch_market_snapshot():
    hist_data = yf.download(ALL_SYMBOLS, period="10d", interval="1d", progress=False)
    intra = yf.download(ALL_SYMBOLS, period="2d", interval="5m", prepost=True, progress=False)
    rows = []
    for sym in ALL_SYMBOLS:
        label = symbol_to_label.get(sym, sym)
        try:
            tk = yf.Ticker(sym)
            fast = tk.fast_info
            price = fast.get('lastPrice') or fast.get('regularMarketPrice') or fast.get('previousClose')
            prev_close = fast.get('regularMarketPreviousClose') or fast.get('previousClose')
            if price is None or prev_close is None or prev_close <= 0: continue
            price = float(price)
            prev_close = float(prev_close)
            change = ((price - prev_close) / prev_close * 100)
            try:
                open_series = intra['Open'][sym].dropna()
                today_open = open_series.iloc[0] if not open_series.empty else price
                gap_pct = ((today_open - prev_close) / prev_close * 100)
            except:
                gap_pct = 0.0
            try:
                today_vol = intra['Volume'][sym].sum()
                avg_vol = hist_data['Volume'][sym].iloc[-8:-1].mean() if len(hist_data['Volume'][sym]) >= 8 else 1.0
                rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            except:
                rvol = 1.0
            rows.append({
                "Asset": label, "Symbol": sym, "Price": round(price, 4),
                "Gap %": round(gap_pct, 2), "Change %": round(change, 2), "RVOL": round(rvol, 2)
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

def get_earnings_calendar_finnhub(date_str):
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={date_str}&to={date_str}&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=10); r.raise_for_status()
        data = r.json()
        filtered = []; fallback = []
        for item in data.get('earningsCalendar', []):
            symbol = item.get('symbol', '').upper()
            eps_est = item.get('epsEstimate')
            eps_act = item.get('epsActual')
            rev_est = item.get('revenueEstimate')
            rev_act = item.get('revenueActual')
            eps_beat = "—"
            if eps_act is not None and eps_est is not None:
                eps_beat = "✅ Beat" if eps_act > eps_est else "❌ Miss" if eps_act < eps_est else "Met"
            rev_beat = "—"
            if rev_act is not None and rev_est is not None:
                rev_beat = "✅ Beat" if rev_act > rev_est else "❌ Miss" if rev_act < rev_est else "Met"
            entry = {"When": "", "Symbol": symbol, "Company": symbol,
                     "EPS Est": eps_est if eps_est is not None else "—",
                     "EPS Act": eps_act if eps_act is not None else "—",
                     "Rev Est (B)": round(rev_est / 1e9, 2) if rev_est else "—",
                     "Rev Act (B)": round(rev_act / 1e9, 2) if rev_act else "—",
                     "EPS Beat": eps_beat, "Rev Beat": rev_beat}
            fallback.append(entry)
            if symbol in HUGE_CAP_SYMBOLS:
                filtered.append(entry)
        return filtered if filtered else fallback
    except:
        return []

def get_todays_earnings(): 
    today = datetime.datetime.now(pytz.timezone('US/Eastern')).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(today)
    for d in data: d["When"] = "Today"
    return data

def get_yesterdays_earnings():
    yest = (datetime.datetime.now(pytz.timezone('US/Eastern')) - datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(yest)
    for d in data: d["When"] = "Yesterday"
    return data

def get_tomorrows_earnings():
    tom = (datetime.datetime.now(pytz.timezone('US/Eastern')) + datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(tom)
    for d in data: d["When"] = "Tomorrow"
    return data

def get_pcr_data():
    targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ"}
    results = []
    for label, sym in targets.items():
        try:
            tk = yf.Ticker(sym)
            opts = tk.options
            if opts:
                cv = pv = 0
                for exp in opts[:2]:
                    ch = tk.option_chain(exp)
                    cv += ch.calls['volume'].sum()
                    pv += ch.puts['volume'].sum()
                pcr = pv / cv if cv > 0 else 0
                results.append({"Asset": label, "PCR": round(pcr, 2),
                                "Sentiment": "🐂 Bull" if pcr < 0.85 else "🐻 Bear" if pcr > 1.15 else "⚖️ Neu"})
        except:
            continue
    return pd.DataFrame(results)

def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365.0)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = gamma * OI * 100 * S
    return np.where(types == 'call', val, -val)

@st.cache_data(ttl=180)
def get_theme_stock_news(max_stocks=30):
    news_items = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for sym in ANALYST_SYMBOLS[:max_stocks]:
        try:
            f_sym = "BTC" if sym == "BTC-USD" else sym.split("=")[0]
            url = f"https://finviz.com/quote.ashx?t={f_sym.upper()}"
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", class_="news-table")
            if not table: continue
            for row in table.find_all("tr")[:8]:
                tds = row.find_all("td")
                if len(tds) < 2: continue
                time_str = tds[0].text.strip()
                a_tag = tds[1].find("a")
                if not a_tag: continue
                title = a_tag.text.strip()
                if len(title) < 25: continue
                if not is_high_impact(title): continue
                link = a_tag.get("href")
                if not link.startswith("http"): link = "https://finviz.com" + link
                label, sent_score = get_sentiment_score(title)
                imp_score = impact_score(title)
                news_items.append({
                    "Asset": symbol_to_label.get(sym, sym), "Symbol": sym, "Title": title,
                    "URL": link, "Source": "Finviz", "Sentiment": label,
                    "Score": sent_score, "Impact": imp_score, "Time": time_str
                })
        except:
            continue
    df = pd.DataFrame(news_items)
    if not df.empty:
        df = df.sort_values(by=["Impact", "Score"], ascending=False).drop_duplicates(subset=["Title"])
    return df

@st.cache_data(ttl=180)
def get_mag7_hot_news():
    news_items = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for sym in MAG7_HOT_SYMBOLS:
        try:
            f_sym = "BTC" if sym == "BTC-USD" else sym.split("=")[0]
            url = f"https://finviz.com/quote.ashx?t={f_sym.upper()}"
            r = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", class_="news-table")
            if not table: continue
            for row in table.find_all("tr")[:10]:
                tds = row.find_all("td")
                if len(tds) < 2: continue
                time_str = tds[0].text.strip()
                a_tag = tds[1].find("a")
                if not a_tag: continue
                title = a_tag.text.strip()
                if len(title) < 25: continue
                if not is_high_impact(title): continue
                link = a_tag.get("href")
                if not link.startswith("http"): link = "https://finviz.com" + link
                label, sent_score = get_sentiment_score(title)
                imp_score = impact_score(title)
                news_items.append({
                    "Asset": symbol_to_label.get(sym, sym), "Symbol": sym, "Title": title,
                    "URL": link, "Source": "Finviz", "Sentiment": label,
                    "Score": sent_score, "Impact": imp_score, "Time": time_str
                })
        except:
            continue
    df = pd.DataFrame(news_items)
    if not df.empty:
        df = df.sort_values(by=["Impact", "Score"], ascending=False).drop_duplicates(subset=["Title"])
    return df

@st.cache_data(ttl=300)
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

@st.cache_data(ttl=3600)
def get_alphavantage_analyst_ratings():
    ratings = []
    for sym in ANALYST_SYMBOLS[:60]:
        try:
            url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={sym}&apikey={ALPHA_VANTAGE_API_KEY}"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            if "AnalystRatingStrongBuy" not in data: continue

            strong_buy = int(data.get("AnalystRatingStrongBuy", 0))
            buy = int(data.get("AnalystRatingBuy", 0))
            hold = int(data.get("AnalystRatingHold", 0))
            sell = int(data.get("AnalystRatingSell", 0))
            strong_sell = int(data.get("AnalystRatingStrongSell", 0))
            total = strong_buy + buy + hold + sell + strong_sell
            if total == 0: continue

            score = (strong_buy*5 + buy*4 + hold*3 + sell*2 + strong_sell*1) / total
            if score >= 4.5:
                consensus = "🚀 Strong Buy"
                bull_score = 5
            elif score >= 3.5:
                consensus = "🟢 Buy"
                bull_score = 4
            elif score >= 2.5:
                consensus = "⚖️ Hold"
                bull_score = 3
            elif score >= 1.5:
                consensus = "🔴 Sell"
                bull_score = 2
            else:
                consensus = "💥 Strong Sell"
                bull_score = 1

            target_mean = float(data.get("AnalystTargetPrice", 0)) if data.get("AnalystTargetPrice") else None
            current_price = market_df[market_df["Symbol"] == sym]["Price"].iloc[0] if not market_df[market_df["Symbol"] == sym].empty else None
            upside = ((target_mean - current_price) / current_price * 100) if target_mean and current_price and current_price > 0 else None

            ratings.append({
                "Asset": symbol_to_label.get(sym, sym),
                "Symbol": sym,
                "Consensus": consensus,
                "Bull Score": bull_score,
                "Strong Buy": strong_buy,
                "Buy": buy,
                "Hold": hold,
                "Sell": sell,
                "Strong Sell": strong_sell,
                "Total Analysts": int(data.get("NumberOfAnalystOpinions", total)),
                "Target Mean": target_mean,
                "Current Price": current_price,
                "Upside %": round(upside, 1) if upside is not None else None
            })
        except:
            continue
    return pd.DataFrame(ratings)

@st.cache_data(ttl=60)
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

# ================================================
# MAIN APP
# ================================================
market_df, intra_data, hist_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Data as of {datetime.date.today()} | Day-Trader Edition with Macro Pulse")

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
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ────────────────────────────────────────────────
#  TABS
# ────────────────────────────────────────────────
tab_premarket, tab_overview, tab_sectors, tab_themes, tab_rel_strength, tab_gex, tab_options, tab_earnings, tab_analyst, tab_macro, tab_finnhub, tab_news, tab_bias = st.tabs([
    "🌅 Premarket Pulse", "📈 Market Overview", "🔥 Alpha Sectors", "🎯 Trading Themes",
    "⚖️ Relative Strength", "📊 GEX + Gamma Flip", "🐳 Options", "🎯 Earnings",
    "📊 Analyst Ratings", "🌍 Macro News", "🌐 Finnhub Daily Pulse",
    "📰 High-Impact News", "🔍 Bias & Regime"
])

with tab_premarket:
    st.subheader("🌡️ Market Sentiment Gauges")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("#### ETF & Crypto Mood")
        sent_df = get_etf_crypto_sentiment()
        if not sent_df.empty:
            st.dataframe(sent_df, hide_index=True, use_container_width=True)
    with col2:
        st.markdown("#### 📡 Active Macro Drivers")
        macro_df = get_macro_drivers()
        if not macro_df.empty:
            for _, row in macro_df.iterrows():
                with st.expander(f"{row['Sentiment']} | {row['Headline'][:80]}..."):
                    st.write(f"Impact: {row['Impact']}")
                    st.write(f"[Read full story]({row['URL']})")
        else:
            st.info("No high-impact macro news detected.")
    st.markdown("---")
    st.subheader("📅 High-Impact Data (Today)")
    econ_df = get_finnhub_econ_calendar()
    if econ_df.empty or econ_df.shape[0] == 0:
        st.info("No major 🔴 HIGH impact releases scheduled today.")
    else:
        high_impact = econ_df[econ_df['Impact'].str.contains("HIGH", na=False)]
        if not high_impact.empty:
            st.dataframe(high_impact.style.background_gradient(cmap='Reds', subset=['Impact']), hide_index=True, use_container_width=True)
        else:
            st.info("No major 🔴 HIGH impact releases scheduled today.")

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
    st.subheader("⚖️ Sector Strength vs SPY")
    st.caption("**1-Day** Cumulative Performance normalized to 0%")   # ← changed
    try:
        benchmark = "SPY"
        sector_symbols = list(SECTOR_TICKERS.values())
        plot_df = hist_data['Close'][[benchmark] + sector_symbols].dropna(how='all').tail(2)  # ← now 1-day
        normalized_df = (plot_df / plot_df.iloc[0] - 1) * 100
        melt_df = normalized_df.reset_index()
        melt_df = melt_df.rename(columns={melt_df.columns[0]: 'Date'})
        fig = px.line(melt_df.melt(id_vars='Date', var_name='Ticker', value_name='Perf %'),
                      x='Date', y='Perf %', color='Ticker', template="plotly_dark", height=500)
        fig.update_traces(patch={"line": {"width": 4, "dash": "dot"}}, selector={"legendgroup": "SPY"})
        st.plotly_chart(fig, use_container_width=True)
        st.write("### Alpha Delta (Current vs SPY)")
        current_perf = normalized_df.iloc[-1]
        rel_perf = (current_perf - current_perf[benchmark]).round(2).reset_index()
        rel_perf.columns = ['Ticker', 'vs SPY (%)']
        st.dataframe(rel_perf.sort_values('vs SPY (%)', ascending=False).style.background_gradient(cmap='RdYlGn'),
                     hide_index=True, use_container_width=True)
    except Exception as e: 
        st.error(f"RS Error: {e}")

    st.subheader("⚖️ Mag7 Strength vs QQQ")
    st.caption("**1-Day** Cumulative Performance normalized to 0%")   # ← changed
    try:
        benchmark = "QQQ"
        mag7_symbols = list(MAG7_TICKERS.values())
        plot_df = hist_data['Close'][[benchmark] + mag7_symbols].dropna(how='all').tail(2)  # ← now 1-day
        normalized_df = (plot_df / plot_df.iloc[0] - 1) * 100
        melt_df = normalized_df.reset_index()
        melt_df = melt_df.rename(columns={melt_df.columns[0]: 'Date'})
        fig = px.line(melt_df.melt(id_vars='Date', var_name='Ticker', value_name='Perf %'),
                      x='Date', y='Perf %', color='Ticker', template="plotly_dark", height=500)
        fig.update_traces(patch={"line": {"width": 4, "dash": "dot"}}, selector={"legendgroup": "QQQ"})
        st.plotly_chart(fig, use_container_width=True)
        st.write("### Alpha Delta (Current vs QQQ)")
        current_perf = normalized_df.iloc[-1]
        rel_perf = (current_perf - current_perf[benchmark]).round(2).reset_index()
        rel_perf.columns = ['Ticker', 'vs QQQ (%)']
        st.dataframe(rel_perf.sort_values('vs QQQ (%)', ascending=False).style.background_gradient(cmap='RdYlGn'),
                     hide_index=True, use_container_width=True)
    except Exception as e: 
        st.error(f"Mag7 RS Error: {e}")


with tab_gex:
    st.subheader("📊 Gamma Exposure (GEX) + Gamma Flip Level")
    st.caption("Front 3 expirations • Green = Long Gamma (stabilizing) • Red = Short Gamma (amplifying) • Yellow line = **Gamma Flip**")
    user_ticker = st.text_input("Enter Ticker for GEX Analysis", value="SPY").upper().strip()
    if user_ticker:
        try:
            tk = yf.Ticker(user_ticker)
            options = tk.options
            if not options:
                st.warning("No options data found.")
            else:
                spot = round(tk.history(period="1d")['Close'].iloc[-1], 2)
                all_chains = []
                for exp in options[:3]:
                    ch = tk.option_chain(exp)
                    all_chains.extend([ch.calls.assign(type='call', exp=exp), ch.puts.assign(type='put', exp=exp)])
                df_g = pd.concat(all_chains, ignore_index=True)
                df_g['impliedVolatility'] = df_g['impliedVolatility'].fillna(0.01)
                df_g['impliedVolatility'] = np.clip(df_g['impliedVolatility'], 0.01, 3.0)
                df_g['openInterest'] = df_g['openInterest'].fillna(0)
                now = datetime.datetime.now(datetime.timezone.utc)
                exp_datetime = pd.to_datetime(df_g['exp']).dt.tz_localize('UTC') + pd.Timedelta(hours=16)
                df_g['dte'] = (exp_datetime - now).dt.total_seconds() / (365 * 24 * 3600)
                df_g['dte'] = np.maximum(df_g['dte'], 1/365.0)
                df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'].values, df_g['dte'].values,
                                                    df_g['impliedVolatility'].values, 0.04, 0.01,
                                                    df_g['type'].values, df_g['openInterest'].values)
                df_agg = (df_g.groupby('strike')['GEX'].sum() / 1e6).sort_index()
                strikes = np.asarray(df_agg.index)
                gex_vals = np.asarray(df_agg.values)
                flip_level = spot
                sign_changes = np.where(np.sign(gex_vals[:-1]) != np.sign(gex_vals[1:]))[0]
                if len(sign_changes) > 0:
                    i = sign_changes[0]
                    x1, y1 = strikes[i], gex_vals[i]
                    x2, y2 = strikes[i+1], gex_vals[i+1]
                    flip_level = x1 - y1 * (x2 - x1) / (y2 - y1) if y2 != y1 else x1
                flip_level = round(flip_level)
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(label="🔄 **Gamma Flip Level**", value=f"${flip_level:,}",
                              delta=f"Spot is {((spot - flip_level)/flip_level*100):+.1f}% above flip")
                with col2:
                    total_gex = round(df_agg.sum(), 1)
                    st.metric(label="Net GEX", value=f"{total_gex}M",
                              delta="🟢 Long Gamma (pinning likely)" if total_gex > 0 else "🔴 Short Gamma (volatile)")
                with col3:
                    st.metric("Current Spot", f"${spot:,.2f}")
                st.caption("**Gamma Flip** = first strike where net GEX changes sign.")
                fig = go.Figure()
                fig.add_trace(go.Bar(x=df_agg.index, y=df_agg.values,
                                     marker_color=['#00ff88' if x > 0 else '#ff4444' for x in df_agg.values], name="GEX ($M)"))
                fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text=f"Spot ${spot}", annotation_position="top")
                fig.add_vline(x=flip_level, line_dash="dot", line_color="#ffd700", line_width=3,
                              annotation_text=f"🔄 GAMMA FLIP ${flip_level}",
                              annotation_position="bottom right" if flip_level < spot else "top left")
                fig.update_layout(template="plotly_dark", title=f"{user_ticker} Net Gamma Exposure + Gamma Flip Level",
                                  height=560, xaxis_title="Strike Price", yaxis_title="Gamma Exposure ($ Millions)", hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"GEX Error: {e}")

with tab_options:
    st.subheader("🐳 Put/Call Volume Ratio")
    pcr_df = get_pcr_data()
    if not pcr_df.empty:
        st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True, use_container_width=True)

with tab_earnings:
    st.subheader("🎯 Earnings Calendar")
    all_events = get_yesterdays_earnings() + get_todays_earnings() + get_tomorrows_earnings()
    if all_events:
        df = pd.DataFrame(all_events)
        def highlight_beats(val):
            if val == "✅ Beat": return 'background-color: #00cc66; color: black; font-weight: bold;'
            if val == "❌ Miss": return 'background-color: #ff4d4d; color: white; font-weight: bold;'
            return ''
        st.dataframe(df.style.applymap(highlight_beats, subset=['EPS Beat', 'Rev Beat']), hide_index=True, use_container_width=True)

with tab_analyst:
    st.subheader("📊 Analyst Ratings & Price Targets (Alpha Vantage)")
    st.caption("Live consensus + mean price target • Cached 1 hour")
    analyst_df = get_alphavantage_analyst_ratings()
    if not analyst_df.empty:
        analyst_df = analyst_df.sort_values('Bull Score', ascending=False)
        def rating_color(val):
            if "Strong Buy" in val: return 'background-color: #00cc66; color: black; font-weight: bold;'
            if "Buy" in val: return 'background-color: #00cc66; color: black;'
            if "Hold" in val: return 'background-color: #ffcc66; color: black;'
            if "Sell" in val: return 'background-color: #ff6666; color: white;'
            return ''
        st.dataframe(
            analyst_df[[
                "Asset", "Symbol", "Consensus", "Bull Score",
                "Strong Buy", "Buy", "Hold", "Sell", "Strong Sell",
                "Total Analysts", "Target Mean", "Current Price", "Upside %"
            ]]
            .style
            .applymap(rating_color, subset=['Consensus'])
            .background_gradient(cmap='RdYlGn', subset=['Upside %', 'Bull Score'])
            .format({
                "Target Mean": "${:,.2f}",
                "Current Price": "${:,.2f}",
                "Upside %": "{:+.1f}%"
            }),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("Fetching analyst ratings... (Alpha Vantage free tier limit)")

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
    hot_df = get_mag7_hot_news()
    if not hot_df.empty:
        for _, row in hot_df.iterrows():
            impact_emoji = "🔥" if row['Impact'] >= 5 else "⚡" if row['Impact'] >= 3 else "📈"
            with st.expander(f"{impact_emoji} {row['Sentiment']} | {row['Asset']} | {row['Title'][:92]}... • {row['Time']}"):
                st.write(f"**Source:** {row['Source']} | Impact Score: {row['Impact']}")
                st.write(f"[🔗 Read full story]({row['URL']})")
    st.markdown("---")
    st.subheader("📰 High-Impact Theme Stocks News")
    news_df = get_theme_stock_news()
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
