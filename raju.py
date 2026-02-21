import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import re
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
#  PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ────────────────────────────────────────────────
#  TICKER CONFIGS + TRADING THEMES
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "S&P 500 (ES)": "ES=F", "Nasdaq (NQ)": "NQ=F", "Dow (YM)": "YM=F",
    "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "10Y Yield": "^TNX",
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
    "🔵 SEMICONDUCTORS (SMH/SOXL)": ["SMH", "SOXL", "NVDA", "AMD", "AVGO", "QCOM", "INTC", "MU", "MRVL", "TSM", "ARM", "SMCI", "WDC", "ALAB"],
    "🟣 SOFTWARE / SaaS (IGV)": ["IGV", "MSFT", "CRM", "NOW", "ADBE", "CRWD", "MDB", "PLTR", "RBRK", "ORCL", "IBM"],
    "🟢 NEO CLOUD / AI INFRA": ["CRWD", "NBIS", "APP", "ALAB", "RBRK", "PLTR", "SMCI", "DELL"],
    "🟡 MEGA CAP TECH (QQQ)": ["QQQ", "META", "GOOGL", "AAPL", "AMZN", "MSFT", "NVDA", "TSLA"],
    "🟠 CRYPTO / BTC": ["BTC-USD", "IBIT", "MSTR", "COIN", "CIFR", "IREN", "BMNR", "CRCL"],
    "🟤 SMALL CAPS (IWM/TNA)": ["IWM", "TNA", "QBTS", "RGTI", "ASTS", "OKLO", "TEM"],
    "🔴 CONSUMER / HIGH BETA": ["AMZN", "TSLA", "RBLX", "CVNA", "RIVN", "LULU", "NKE", "DUOL", "AAL"],
    "🏦 FINANCIALS": ["JPM", "SOFI", "HOOD", "LMND", "UNH"],
    "⚡ ENERGY": ["XOM", "OXY", "BE", "OKLO"],
    "🏗️ INDUSTRIALS/SPACE": ["CAT", "BA", "RKLB", "ASTS", "FDX"],
    "🏥 HEALTHCARE": ["LLY", "UNH", "TEM"],
    "🥇 COMMODITIES/METALS": ["GC=F", "SLV", "AGQ", "ZSL", "ALB", "MP"]
}

# ────── Single row per symbol (no duplicates) ──────
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

HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO',
    'HD', 'COST', 'NFLX', 'DIS', 'PFE', 'MRK', 'LLY', 'AVGO'
}

FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"

# ────────────────────────────────────────────────
#  DATA HELPERS
# ────────────────────────────────────────────────

@st.cache_data(ttl=45)
def fetch_market_snapshot():
    hist_data = yf.download(ALL_SYMBOLS, period="5d", interval="1d", progress=False)
    intra = yf.download(ALL_SYMBOLS, period="1d", interval="5m", prepost=True, progress=False)
    
    rows = []
    for sym in ALL_SYMBOLS:
        label = symbol_to_label[sym]
        try:
            price = intra['Close'][sym].dropna().iloc[-1]
            prev_close = hist_data['Close'][sym].iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            today_vol = intra['Volume'][sym].sum()
            avg_vol = hist_data['Volume'][sym].iloc[-5:-1].mean()
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            rows.append({"Asset": label, "Symbol": sym, "Price": price, "Change %": change, "RVOL": rvol})
        except:
            continue
    return pd.DataFrame(rows), intra, hist_data


# (Keep all your existing functions: earnings, pcr, sentiment, gamma, theme news, finviz general news)
# Paste them here from your previous working code (they are unchanged)

def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return np.where(types == 'call', val, -val)


def get_sentiment_score(text):
    bull = ['upbeat','growth','surge','rally','beat','buy','bullish','expansion','profit','gain','positive','jump','beat','upgrade','raise','strong','outperform','higher','rise','soar']
    bear = ['slump','drop','fall','miss','sell','bearish','contraction','loss','negative','inflation','fear','risk','sink','downgrade','cut','weak','underperform','lower','decline','plunge']
    score = sum(1 for w in bull if w in text.lower()) - sum(1 for w in bear if w in text.lower())
    if score > 2: return "🟢 Bullish", score
    if score < -2: return "🔴 Bearish", score
    if score > 0: return "🟡 Mild Bull", score
    if score < 0: return "🟠 Mild Bear", score
    return "⚪ Neutral", 0


@st.cache_data(ttl=180)
def get_theme_stock_news(max_stocks=30):
    # Your existing pure Finviz news scraper (unchanged)
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
            
            for row in table.find_all("tr")[:6]:
                tds = row.find_all("td")
                if len(tds) < 2: continue
                time_str = tds[0].text.strip()
                a_tag = tds[1].find("a")
                if not a_tag: continue
                title = a_tag.text.strip()
                if len(title) < 20: continue
                link = a_tag.get("href")
                if not link.startswith("http"): link = "https://finviz.com" + link
                
                label, score = get_sentiment_score(title)
                news_items.append({
                    "Asset": symbol_to_label.get(sym, sym),
                    "Symbol": sym,
                    "Title": title,
                    "URL": link,
                    "Source": "Finviz",
                    "Sentiment": label,
                    "Score": score,
                    "Time": time_str
                })
        except:
            continue
    
    df = pd.DataFrame(news_items)
    if not df.empty:
        df = df.sort_values(by="Score", ascending=False).drop_duplicates(subset=["Title"])
    return df


# ────── NEW: MarketBeat Analyst Ratings Scraper ──────
@st.cache_data(ttl=3600)
def get_marketbeat_ratings():
    ratings = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    for sym in ANALYST_SYMBOLS:
        try:
            ticker = sym.replace("^", "").replace("=F", "").upper().lower()
            # Try NASDAQ first, then NYSE
            for exchange in ["nasdaq", "nyse"]:
                url = f"https://www.marketbeat.com/stocks/{exchange}/{ticker}/"
                r = requests.get(url, headers=headers, timeout=12)
                if r.status_code != 200: continue
                
                text = r.text
                soup = BeautifulSoup(text, "html.parser")
                
                # Consensus Rating
                cons_match = re.search(r'Consensus Rating\s*([A-Za-z ]+)', text)
                consensus = cons_match.group(1).strip() if cons_match else "—"
                
                # Price Target
                target_match = re.search(r'(?:Average )?Price Target\s*\$?([\d,]+\.?\d*)', text)
                target = target_match.group(1).replace(",", "") if target_match else "—"
                
                # Upside %
                upside_match = re.search(r'Potential Upside/Downside\s*([+-]?\d+\.?\d*)%', text)
                upside = upside_match.group(1) if upside_match else "—"
                
                if consensus != "—" or target != "—":
                    ratings.append({
                        "Asset": symbol_to_label.get(sym, sym),
                        "Symbol": sym,
                        "Consensus": consensus,
                        "Target Price": target,
                        "Upside %": upside
                    })
                    break
        except:
            continue
    
    df = pd.DataFrame(ratings)
    return df


# ────────────────────────────────────────────────
#  MAIN UI
# ────────────────────────────────────────────────
market_df, intra_data, hist_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Data as of {datetime.date.today()} | Day-Trader Edition with Gamma Flip")

tab_overview, tab_sectors, tab_themes, tab_rel_strength, tab_gex, tab_options, tab_earnings, tab_analyst, tab_extremes, tab_news = st.tabs([
    "📈 Market Overview", "🔥 Alpha Sectors", "🎯 Trading Themes", "⚖️ Relative Strength",
    "📊 GEX + Gamma Flip", "🐳 Options", "🎯 Earnings", "📊 Analyst Ratings (MarketBeat)",
    "🔥 ATH/ATL Plays", "📰 Theme News"
])

# ... (All your previous tabs: Overview, Sectors, Themes, Relative Strength, GEX, Options, Earnings remain 100% unchanged)

with tab_analyst:
    st.subheader("📊 Analyst Ratings & Price Targets (MarketBeat)")
    st.caption("Live consensus from MarketBeat • Updated hourly")
    
    analyst_df = get_marketbeat_ratings()
    
    if not analyst_df.empty:
        # Merge current price
        price_map = market_df.set_index('Symbol')['Price'].to_dict()
        analyst_df['Current Price'] = analyst_df['Symbol'].map(price_map)
        
        analyst_df['Target Price'] = pd.to_numeric(analyst_df['Target Price'], errors='coerce')
        analyst_df['Current Price'] = pd.to_numeric(analyst_df['Current Price'], errors='coerce')
        analyst_df['Upside %'] = ((analyst_df['Target Price'] - analyst_df['Current Price']) / analyst_df['Current Price'] * 100).round(1)
        
        def rating_color(val):
            if "Strong Buy" in str(val) or "Buy" in str(val): return 'background-color: #00cc66; color: black; font-weight: bold;'
            if "Hold" in str(val): return 'background-color: #ffcc66; color: black;'
            if "Sell" in str(val): return 'background-color: #ff6666; color: white;'
            return ''
        
        st.dataframe(
            analyst_df[['Asset', 'Symbol', 'Consensus', 'Target Price', 'Current Price', 'Upside %']]
            .style.applymap(rating_color, subset=['Consensus'])
            .background_gradient(cmap='RdYlGn', subset=['Upside %'])
            .format({"Target Price": "${:,.2f}", "Current Price": "${:,.2f}", "Upside %": "{:+.1f}%"}),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("Fetching latest analyst data from MarketBeat...")

with tab_news:
    st.subheader("📰 Trading Themes News")
    st.caption("Latest news from **all stocks in your Trading Themes** • Scored live for sentiment")
    
    news_df = get_theme_stock_news()
    
    if not news_df.empty:
        total_score = news_df['Score'].sum()
        st.sidebar.metric("Theme Sentiment Pulse", total_score,
                         delta="Positive" if total_score >= 0 else "Negative")
        
        for _, row in news_df.iterrows():
            with st.expander(f"{row['Sentiment']}  {row['Asset']} | {row['Title'][:88]}{'...' if len(row['Title']) > 88 else ''} • {row['Time']}"):
                st.write(f"**Source:** {row['Source']}")
                st.write(f"[🔗 Read full story]({row['URL']})")
    else:
        st.info("Fetching fresh news from Finviz...")

st_autorefresh(interval=300000, key="global_refresh")
