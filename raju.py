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
import time

# ────────────────────────────────────────────────
#  PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro - Day Trader Edition", page_icon="🏛️", layout="wide")

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

# Combine all symbols for quick lookups
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

# Analyst + News Symbols (ALL Trading Themes stocks)
ANALYST_SYMBOLS = sorted({sym for sublist in TRADING_THEMES.values() for sym in sublist})

HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO',
    'HD', 'COST', 'NFLX', 'DIS', 'PFE', 'MRK', 'LLY', 'AVGO'
}

TIER1_FIRMS = {
    'Goldman Sachs', 'Morgan Stanley', 'JPMorgan', 'Bank of America', 'Citigroup', 'Barclays',
    'Evercore', 'UBS', 'Jefferies', 'RBC Capital', 'Deutsche Bank', 'Wells Fargo',
    'BofA Securities', 'Credit Suisse', 'Bernstein', 'Piper Sandler', 'Oppenheimer',
    'Wedbush', 'Stifel', 'Wolfe Research'
}

FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"  # Replace with your own if needed

# ────────────────────────────────────────────────
#  HELPER FUNCTIONS (Gamma, Sentiment, etc.)
# ────────────────────────────────────────────────

def black_scholes_gamma(S, K, T, r, sigma, option_type='call'):
    """Gamma of a single option (Black-Scholes)."""
    if T <= 0 or sigma <= 0:
        return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

def calc_gamma_vectorized(S, strikes, dtes, ivs, r, q, types, ois):
    """
    Vectorized gamma calculation.
    S: current spot price
    strikes: array of strikes
    dtes: time to expiry in years
    ivs: implied volatilities
    r: risk-free rate
    q: dividend yield (simplified to 0 here)
    types: 'call' or 'put'
    ois: open interest
    Returns gamma * oi * 100 * spot (dollar gamma per option)
    """
    gamma = np.zeros_like(strikes)
    mask = (dtes > 0) & (ivs > 0) & (ois > 0)
    if not np.any(mask):
        return gamma
    S_arr = np.full_like(strikes, S)
    d1 = (np.log(S_arr[mask] / strikes[mask]) + (r - q + 0.5 * ivs[mask]**2) * dtes[mask]) / (ivs[mask] * np.sqrt(dtes[mask]))
    gamma[mask] = norm.pdf(d1) / (S_arr[mask] * ivs[mask] * np.sqrt(dtes[mask]))
    # Dollar gamma per contract = gamma * spot^2 * 100 (each option controls 100 shares)
    dollar_gamma = gamma * (S ** 2) * 100 * ois / 1_000_000  # in millions
    return dollar_gamma

def get_sentiment_score(text):
    bull = ['upbeat','growth','surge','rally','beat','buy','bullish','expansion','profit','gain','positive','jump','beat','upgrade','raise','strong','outperform']
    bear = ['slump','drop','fall','miss','sell','bearish','contraction','loss','negative','inflation','fear','risk','sink','downgrade','cut','weak','underperform']
    score = sum(1 for w in bull if w in text.lower()) - sum(1 for w in bear if w in text.lower())
    if score > 2: return "🟢 Bullish", score
    if score < -2: return "🔴 Bearish", score
    if score > 0: return "🟡 Mild Bull", score
    if score < 0: return "🟠 Mild Bear", score
    return "⚪ Neutral", 0

# ────────────────────────────────────────────────
#  DATA FETCH FUNCTIONS (with caching)
# ────────────────────────────────────────────────

@st.cache_data(ttl=30)  # Refresh every 30 seconds
def fetch_market_snapshot():
    """Get current prices, changes, RVOL for all symbols."""
    # Use 1d interval for current day's data (includes pre-market if available)
    intra = yf.download(ALL_SYMBOLS, period="1d", interval="5m", prepost=True, progress=False, group_by='ticker')
    # Use 5d for previous close
    hist = yf.download(ALL_SYMBOLS, period="5d", interval="1d", progress=False, group_by='ticker')
    
    rows = []
    for sym in ALL_SYMBOLS:
        label = symbol_to_label.get(sym, sym)
        try:
            # Get latest price from intraday data
            if sym in intra and not intra[sym].empty:
                price = intra[sym]['Close'].dropna().iloc[-1]
            else:
                # fallback to last close from hist
                price = hist[sym]['Close'].iloc[-1]
            prev_close = hist[sym]['Close'].iloc[-2] if len(hist[sym]) >= 2 else price
            change = ((price - prev_close) / prev_close) * 100
            # Volume today (intraday cumulative)
            if sym in intra and not intra[sym].empty:
                today_vol = intra[sym]['Volume'].sum()
            else:
                today_vol = hist[sym]['Volume'].iloc[-1] if len(hist[sym]) >= 1 else 0
            avg_vol = hist[sym]['Volume'].iloc[-5:-1].mean() if len(hist[sym]) >= 5 else today_vol
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            rows.append({"Asset": label, "Symbol": sym, "Price": price, "Change %": change, "RVOL": rvol})
        except Exception as e:
            # st.write(f"Error {sym}: {e}")  # too noisy
            continue
    return pd.DataFrame(rows)

@st.cache_data(ttl=60)
def get_premarket_movers():
    """Identify stocks gapping up/down in pre-market."""
    # Fetch current day's 1m data to get pre-market prices (before 9:30 ET)
    est = pytz.timezone('US/Eastern')
    now = datetime.datetime.now(est)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now < market_open:
        # Still pre-market
        pre_end = now
    else:
        pre_end = market_open  # after open, we use pre-market data from earlier
    # Download 1m data for all symbols (limited to reduce calls)
    # We'll focus on ANALYST_SYMBOLS for speed
    tickers_to_check = ANALYST_SYMBOLS[:50]  # limit to first 50 for performance
    data = yf.download(tickers_to_check, period="1d", interval="1m", prepost=True, progress=False, group_by='ticker')
    movers = []
    for sym in tickers_to_check:
        try:
            if sym not in data or data[sym].empty:
                continue
            df = data[sym]
            # Pre-market data is before 9:30
            pre_df = df[df.index.time < datetime.time(9, 30)]
            if pre_df.empty:
                continue
            pre_close = pre_df['Close'].iloc[-1]  # last pre-market price
            # Previous close from yesterday
            hist = yf.download(sym, period="2d", interval="1d", progress=False)
            if hist.empty or len(hist) < 2:
                continue
            prev_close = hist['Close'].iloc[-2]
            gap_pct = (pre_close - prev_close) / prev_close * 100
            if abs(gap_pct) > 1.0:  # only show >1% gaps
                movers.append({
                    "Symbol": sym,
                    "Asset": symbol_to_label.get(sym, sym),
                    "Pre-market Price": round(pre_close, 2),
                    "Previous Close": round(prev_close, 2),
                    "Gap %": round(gap_pct, 2)
                })
        except Exception as e:
            continue
    df = pd.DataFrame(movers).sort_values("Gap %", ascending=False)
    return df

@st.cache_data(ttl=300)
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
            entry = {
                "When": "", "Symbol": symbol, "Company": symbol,
                "EPS Est": eps_est if eps_est is not None else "—",
                "EPS Act": eps_act if eps_act is not None else "—",
                "Rev Est (B)": round(rev_est / 1e9, 2) if rev_est else "—",
                "Rev Act (B)": round(rev_act / 1e9, 2) if rev_act else "—",
                "EPS Beat": eps_beat, "Rev Beat": rev_beat
            }
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

@st.cache_data(ttl=900)
def get_analyst_changes_yfinance(days_back=10):
    symbols_to_check = ANALYST_SYMBOLS
    all_changes = []
    for symbol in symbols_to_check:
        try:
            tk = yf.Ticker(symbol)
            rec = tk.recommendations
            if rec is None or rec.empty: continue
            rec = rec[rec.index >= pd.Timestamp.now() - pd.Timedelta(days=days_back)]
            for idx, row in rec.iterrows():
                firm = row.get('Firm', 'Unknown')
                if firm not in TIER1_FIRMS and 'Unknown' not in firm: continue
                all_changes.append({
                    "Date": idx.strftime('%Y-%m-%d'),
                    "Symbol": symbol,
                    "Asset": symbol_to_label.get(symbol, symbol),
                    "Firm": firm,
                    "Action": row.get('Action', 'Change'),
                    "From": row.get('From Grade', '—'),
                    "To": row.get('To Grade', '—')
                })
        except:
            continue
    df = pd.DataFrame(all_changes)
    if not df.empty:
        df = df.sort_values("Date", ascending=False).drop_duplicates(subset=["Date", "Symbol", "Firm", "To"])
    return df

@st.cache_data(ttl=300)
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

@st.cache_data(ttl=180)
def get_theme_stock_news(max_stocks=35):
    news_items = []
    for sym in ANALYST_SYMBOLS[:max_stocks]:
        try:
            tk = yf.Ticker(sym)
            for n in tk.news[:5]:
                title = n.get('title', '')
                if not title: continue
                url = n.get('link', '')
                source = n.get('publisher', 'Yahoo')
                label, score = get_sentiment_score(title)
                news_items.append({
                    "Asset": symbol_to_label.get(sym, sym),
                    "Symbol": sym,
                    "Title": title,
                    "URL": url,
                    "Source": source,
                    "Sentiment": label,
                    "Score": score
                })
        except:
            continue
    df = pd.DataFrame(news_items)
    if not df.empty:
        df = df.sort_values(by=['Score', 'Title'], ascending=[False, True]).drop_duplicates(subset=['Title'])
    return df

@st.cache_data(ttl=300)
def get_unusual_options_flow():
    """Scan for options with unusual volume (volume > OI * 2) in near-term expirations."""
    # Focus on high-liquidity names from MAG7 and SPY/QQQ
    targets = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
    unusual = []
    for sym in targets:
        try:
            tk = yf.Ticker(sym)
            expirations = tk.options
            if not expirations:
                continue
            # Look at nearest 2 expirations
            for exp in expirations[:2]:
                chain = tk.option_chain(exp)
                calls = chain.calls
                puts = chain.puts
                for opt in [calls, puts]:
                    opt_type = 'call' if opt is calls else 'put'
                    for _, row in opt.iterrows():
                        oi = row['openInterest']
                        vol = row['volume']
                        if oi > 0 and vol > oi * 2:  # volume > 2x OI
                            unusual.append({
                                "Symbol": sym,
                                "Expiration": exp,
                                "Type": opt_type,
                                "Strike": row['strike'],
                                "Volume": vol,
                                "Open Interest": oi,
                                "Vol/OI": round(vol/oi, 2)
                            })
        except:
            continue
    df = pd.DataFrame(unusual)
    if not df.empty:
        df = df.sort_values("Vol/OI", ascending=False)
    return df

@st.cache_data(ttl=300)
def get_gappers():
    """Stocks that gapped up/down at market open (using open vs previous close)."""
    # Use 1d data for all symbols, but we'll limit to ANALYST_SYMBOLS
    tickers = ANALYST_SYMBOLS[:100]
    data = yf.download(tickers, period="2d", interval="1d", progress=False, group_by='ticker')
    gaps = []
    for sym in tickers:
        try:
            if sym not in data or data[sym].empty or len(data[sym]) < 2:
                continue
            df = data[sym]
            prev_close = df['Close'].iloc[-2]
            today_open = df['Open'].iloc[-1]
            gap_pct = (today_open - prev_close) / prev_close * 100
            if abs(gap_pct) > 1.5:
                # Get current price
                ticker = yf.Ticker(sym)
                current = ticker.history(period="1d")['Close'].iloc[-1]
                gaps.append({
                    "Symbol": sym,
                    "Asset": symbol_to_label.get(sym, sym),
                    "Gap %": round(gap_pct, 2),
                    "Open": round(today_open, 2),
                    "Current": round(current, 2),
                    "Change from Open": round((current - today_open) / today_open * 100, 2)
                })
        except:
            continue
    df = pd.DataFrame(gaps).sort_values("Gap %", ascending=False)
    return df

@st.cache_data(ttl=300)
def get_ath_atl():
    """Find stocks making new 52-week highs or lows today."""
    # We'll use yfinance info to get 52-week range
    tickers = ANALYST_SYMBOLS[:100]  # limit for speed
    records = []
    for sym in tickers:
        try:
            tk = yf.Ticker(sym)
            info = tk.info
            if not info:
                continue
            current = info.get('regularMarketPrice', 0)
            fifty_two_high = info.get('fiftyTwoWeekHigh', 0)
            fifty_two_low = info.get('fiftyTwoWeekLow', 0)
            if current >= fifty_two_high * 0.995:  # within 0.5% of high
                status = "🔥 ATH" if current >= fifty_two_high else "Near High"
                records.append({"Symbol": sym, "Asset": symbol_to_label.get(sym, sym), "Price": current, "52W High": fifty_two_high, "Status": status})
            elif current <= fifty_two_low * 1.005:
                status = "💧 ATL" if current <= fifty_two_low else "Near Low"
                records.append({"Symbol": sym, "Asset": symbol_to_label.get(sym, sym), "Price": current, "52W Low": fifty_two_low, "Status": status})
        except:
            continue
    return pd.DataFrame(records)

# ────────────────────────────────────────────────
#  MAIN UI
# ────────────────────────────────────────────────
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')
st.title("🏛️ Alpha Terminal Pro - Day Trader Edition")
st.caption(f"EST {time_now} | Refreshes every 60s | Real-time data for day trading")

# Sidebar for quick watchlist and controls
with st.sidebar:
    st.header("⚙️ Controls")
    refresh_rate = st.slider("Refresh rate (seconds)", 30, 300, 60, 5)
    st_autorefresh(interval=refresh_rate*1000, key="global_refresh")
    
    st.header("📌 My Watchlist")
    watchlist_input = st.text_area("Enter symbols (comma separated)", value="SPY, QQQ, NVDA, TSLA, AAPL")
    watchlist = [s.strip().upper() for s in watchlist_input.split(',') if s.strip()]
    
    if st.button("Refresh Now"):
        st.cache_data.clear()
        st.rerun()
    
    st.header("📈 Market Pulse")
    # We'll show some summary metrics
    try:
        spy = yf.Ticker("SPY").history(period="1d")['Close'].iloc[-1]
        vix = yf.Ticker("^VIX").history(period="1d")['Close'].iloc[-1]
        st.metric("SPY", f"${spy:.2f}")
        st.metric("VIX", f"{vix:.2f}")
    except:
        pass

# Main tabs
tab_overview, tab_premarket, tab_gappers, tab_themes, tab_gex, tab_options_flow, tab_earnings, tab_analyst, tab_extremes, tab_news = st.tabs([
    "📈 Overview", "🌅 Pre-Market", "🚀 Gappers", "🎯 Themes",
    "📊 GEX + Gamma Flip", "🐳 Unusual Options", "🎯 Earnings", "📊 Analyst", "🔥 ATH/ATL", "📰 News"
])

# ────────────────────────────────────────────────
#  TAB: MARKET OVERVIEW
# ────────────────────────────────────────────────
with tab_overview:
    market_df = fetch_market_snapshot()
    
    st.subheader("🗝️ Key Indices")
    key_indices = ["S&P 500", "SPY", "QQQ", "^VIX", "10Y Yield", "DXY"]
    key_df = market_df[market_df['Asset'].isin(key_indices)][['Asset', 'Price', 'Change %', 'RVOL']].round(2)
    st.dataframe(key_df.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)

    st.subheader("🚀 Magnificent 7")
    mag7_df = market_df[market_df['Asset'].isin(MAG7_TICKERS.keys())].copy().sort_values('Change %', ascending=False)
    spy_change = mag7_df[mag7_df['Asset'] == "SPY"]['Change %'].iloc[0] if not mag7_df[mag7_df['Asset'] == "SPY"].empty else 0
    mag7_df['vs SPY (%)'] = (mag7_df['Change %'] - spy_change).round(2)
    st.dataframe(mag7_df[['Asset', 'Price', 'Change %', 'vs SPY (%)', 'RVOL']].round(2)
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'vs SPY (%)', 'RVOL']),
                 hide_index=True, use_container_width=True)

    st.subheader("🔥 Alpha Sectors")
    sector_df = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    st.dataframe(sector_df[['Asset', 'Price', 'Change %', 'RVOL']]
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']),
                 hide_index=True, use_container_width=True)

# ────────────────────────────────────────────────
#  TAB: PRE-MARKET MOVERS
# ────────────────────────────────────────────────
with tab_premarket:
    st.subheader("🌅 Pre-Market Movers (Gaps >1%)")
    prem_df = get_premarket_movers()
    if not prem_df.empty:
        st.dataframe(prem_df.style.background_gradient(cmap='RdYlGn', subset=['Gap %']),
                     hide_index=True, use_container_width=True)
    else:
        st.info("No significant pre-market movers or market is open.")

# ────────────────────────────────────────────────
#  TAB: GAPPERS
# ────────────────────────────────────────────────
with tab_gappers:
    st.subheader("🚀 Stocks Gapping at Open (Gap >1.5%)")
    gappers_df = get_gappers()
    if not gappers_df.empty:
        st.dataframe(gappers_df.style.background_gradient(cmap='RdYlGn', subset=['Gap %', 'Change from Open']),
                     hide_index=True, use_container_width=True)
    else:
        st.info("No significant gappers today.")

# ────────────────────────────────────────────────
#  TAB: TRADING THEMES
# ────────────────────────────────────────────────
with tab_themes:
    st.subheader("🎯 Active Trading Themes")
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
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.warning(f"No data")

# ────────────────────────────────────────────────
#  TAB: GEX + GAMMA FLIP
# ────────────────────────────────────────────────
with tab_gex:
    st.subheader("📊 Gamma Exposure (GEX) + Gamma Flip")
    user_ticker = st.text_input("Enter Ticker for GEX Analysis", value="SPY").upper().strip()
    
    if user_ticker:
        try:
            tk = yf.Ticker(user_ticker)
            options = tk.options
            if not options:
                st.warning("No options data found.")
            else:
                spot = tk.history(period="1d")['Close'].iloc[-1]
                
                all_chains = []
                for exp in options[:3]:
                    ch = tk.option_chain(exp)
                    ch.calls['type'] = 'call'
                    ch.puts['type'] = 'put'
                    ch.calls['exp'] = exp
                    ch.puts['exp'] = exp
                    all_chains.append(ch.calls)
                    all_chains.append(ch.puts)
                df_g = pd.concat(all_chains, ignore_index=True)
                
                df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365.0
                # Filter out invalid data
                df_g = df_g[(df_g['dte'] > 0) & (df_g['impliedVolatility'] > 0) & (df_g['openInterest'] > 0)]
                if df_g.empty:
                    st.warning("No valid options data.")
                else:
                    df_g['GEX'] = calc_gamma_vectorized(
                        spot, df_g['strike'].values, df_g['dte'].values,
                        df_g['impliedVolatility'].values, 0.04, 0.00,
                        df_g['type'].values, df_g['openInterest'].values
                    )
                    
                    df_agg = df_g.groupby('strike')['GEX'].sum().sort_index()
                    
                    strikes = df_agg.index.values
                    gex_vals = df_agg.values
                    flip_level = spot
                    # Find zero crossing (where GEX changes sign)
                    for i in range(1, len(strikes)):
                        if gex_vals[i-1] <= 0 and gex_vals[i] > 0:
                            x1, y1 = strikes[i-1], gex_vals[i-1]
                            x2, y2 = strikes[i], gex_vals[i]
                            flip_level = x1 - y1 * (x2 - x1) / (y2 - y1)
                            break
                    flip_level = round(flip_level, 2)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("🔄 Gamma Flip Level", f"${flip_level:,.2f}",
                                 delta=f"Spot is {((spot - flip_level)/flip_level*100):+.1f}% from flip")
                    with col2:
                        total_gex = round(df_agg.sum(), 1)
                        st.metric("Net GEX (M)", f"{total_gex}",
                                 delta="Long Gamma" if total_gex > 0 else "Short Gamma")
                    with col3:
                        st.metric("Current Spot", f"${spot:,.2f}")
                    
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=df_agg.index,
                        y=df_agg.values,
                        marker_color=['#00ff88' if x > 0 else '#ff4444' for x in df_agg.values],
                        name="GEX ($M)"
                    ))
                    fig.add_vline(x=spot, line_dash="dash", line_color="white",
                                  annotation_text=f"Spot ${spot}", annotation_position="top")
                    fig.add_vline(x=flip_level, line_dash="dot", line_color="#ffd700", line_width=3,
                                  annotation_text=f"🔄 FLIP ${flip_level}",
                                  annotation_position="bottom right" if flip_level < spot else "top left")
                    
                    fig.update_layout(
                        template="plotly_dark",
                        title=f"{user_ticker} Net Gamma Exposure",
                        height=500,
                        xaxis_title="Strike",
                        yaxis_title="Gamma ($M)",
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"GEX Error: {e}")
            st.info("Try SPY, QQQ, NVDA, TSLA — most liquid names work best.")

# ────────────────────────────────────────────────
#  TAB: UNUSUAL OPTIONS FLOW
# ────────────────────────────────────────────────
with tab_options_flow:
    st.subheader("🐳 Unusual Options Flow (Volume > 2x OI)")
    unusual_df = get_unusual_options_flow()
    if not unusual_df.empty:
        st.dataframe(unusual_df.style.background_gradient(cmap='Blues', subset=['Vol/OI']),
                     hide_index=True, use_container_width=True)
    else:
        st.info("No unusual options flow detected in the last scan.")

# ────────────────────────────────────────────────
#  TAB: EARNINGS
# ────────────────────────────────────────────────
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

# ────────────────────────────────────────────────
#  TAB: ANALYST CHANGES
# ────────────────────────────────────────────────
with tab_analyst:
    st.subheader("📊 Recent Analyst Changes (Tier-1 Firms)")
    analyst_df = get_analyst_changes_yfinance()
    if not analyst_df.empty:
        def highlight_action(val):
            if "Upgrade" in str(val): return 'background-color: #00cc66; color: black; font-weight: bold;'
            if "Downgrade" in str(val): return 'background-color: #ff4d4d; color: white; font-weight: bold;'
            return ''
        st.dataframe(
            analyst_df[['Date', 'Asset', 'Symbol', 'Firm', 'Action', 'From', 'To']]
            .style.applymap(highlight_action, subset=['Action'])
            .background_gradient(cmap='RdYlGn', subset=['Date']),
            hide_index=True, use_container_width=True
        )
    else:
        st.info("No recent Tier-1 analyst changes.")

# ────────────────────────────────────────────────
#  TAB: ATH/ATL
# ────────────────────────────────────────────────
with tab_extremes:
    st.subheader("🔥 52-Week Highs/Lows (Today)")
    extremes_df = get_ath_atl()
    if not extremes_df.empty:
        st.dataframe(extremes_df.style.applymap(lambda x: 'color: green' if 'ATH' in str(x) else 'color: red', subset=['Status']),
                     hide_index=True, use_container_width=True)
    else:
        st.info("No new 52-week highs/lows detected among tracked stocks.")

# ────────────────────────────────────────────────
#  TAB: THEME NEWS
# ────────────────────────────────────────────────
with tab_news:
    st.subheader("📰 Trading Themes News (with Sentiment)")
    news_df = get_theme_stock_news()
    if not news_df.empty:
        total_score = news_df['Score'].sum()
        st.sidebar.metric("Theme Sentiment Pulse", total_score,
                         delta="Positive" if total_score >= 0 else "Negative")
        for _, row in news_df.iterrows():
            with st.expander(f"{row['Sentiment']}  {row['Asset']} | {row['Title'][:90]}{'...' if len(row['Title']) > 90 else ''}"):
                st.write(f"**Source:** {row['Source']}")
                st.write(f"[🔗 Read full story]({row['URL']})")
    else:
        st.info("No news found at the moment.")
