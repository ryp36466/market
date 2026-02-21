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
import concurrent.futures
from typing import Optional, Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# ────────────────────────────────────────────────
#  PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Alpha Terminal Pro - Day Trader", 
    page_icon="🏛️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ────────────────────────────────────────────────
#  CONSTANTS & CONFIGURATION
# ────────────────────────────────────────────────
# Initialize session state
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.datetime.now()
if 'watchlist_data' not in st.session_state:
    st.session_state.watchlist_data = {}

# Configuration
MAX_WORKERS = 10
REQUEST_TIMEOUT = 10
FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"  # Consider moving to secrets

# Timezone
EST = pytz.timezone('US/Eastern')

# Your existing ticker dictionaries (keeping them exactly as you had)
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

# Build symbol mappings
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

TIER1_FIRMS = {
    'Goldman Sachs', 'Morgan Stanley', 'JPMorgan', 'Bank of America', 'Citigroup', 'Barclays',
    'Evercore', 'UBS', 'Jefferies', 'RBC Capital', 'Deutsche Bank', 'Wells Fargo',
    'BofA Securities', 'Credit Suisse', 'Bernstein', 'Piper Sandler', 'Oppenheimer',
    'Wedbush', 'Stifel', 'Wolfe Research'
}

# ────────────────────────────────────────────────
#  OPTIMIZED HELPER FUNCTIONS
# ────────────────────────────────────────────────

def safe_divide(numerator, denominator, default=0):
    """Safe division to avoid division by zero."""
    return numerator / denominator if denominator != 0 else default

def get_market_status() -> Tuple[str, str]:
    """Get current market status and time."""
    now = datetime.datetime.now(EST)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    if now < market_open:
        status = "🌅 Pre-Market"
    elif now > market_close:
        status = "🌙 After-Hours"
    else:
        status = "⚡ Regular Trading"
    
    return status, now.strftime('%H:%M:%S ET')

def calc_gamma_vectorized(S, strikes, dtes, ivs, r, q, types, ois):
    """Vectorized gamma calculation optimized for speed."""
    gamma = np.zeros_like(strikes)
    mask = (dtes > 0) & (ivs > 0) & (ois > 0)
    
    if not np.any(mask):
        return gamma
    
    S_arr = np.full_like(strikes, S)
    d1 = (np.log(S_arr[mask] / strikes[mask]) + (r - q + 0.5 * ivs[mask]**2) * dtes[mask]) / (ivs[mask] * np.sqrt(dtes[mask]))
    gamma[mask] = norm.pdf(d1) / (S_arr[mask] * ivs[mask] * np.sqrt(dtes[mask]))
    
    # Dollar gamma in millions
    dollar_gamma = gamma * (S ** 2) * 100 * ois / 1_000_000
    return dollar_gamma

def get_sentiment_score(text):
    """Enhanced sentiment scoring with word lists."""
    bull_words = ['upbeat', 'growth', 'surge', 'rally', 'beat', 'buy', 'bullish', 
                  'expansion', 'profit', 'gain', 'positive', 'jump', 'upgrade', 
                  'raise', 'strong', 'outperform', 'record', 'soar', 'boom']
    
    bear_words = ['slump', 'drop', 'fall', 'miss', 'sell', 'bearish', 'contraction', 
                  'loss', 'negative', 'inflation', 'fear', 'risk', 'sink', 'downgrade', 
                  'cut', 'weak', 'underperform', 'crash', 'plunge', 'warning']
    
    text_lower = text.lower()
    score = sum(1 for w in bull_words if w in text_lower) - sum(1 for w in bear_words if w in text_lower)
    
    if score > 2: return "🟢 Bullish", score
    if score < -2: return "🔴 Bearish", score
    if score > 0: return "🟡 Mild Bull", score
    if score < 0: return "🟠 Mild Bear", score
    return "⚪ Neutral", 0

# ────────────────────────────────────────────────
#  OPTIMIZED DATA FETCHING FUNCTIONS
# ────────────────────────────────────────────────

@st.cache_data(ttl=30, show_spinner=False)
def fetch_market_snapshot():
    """Optimized market snapshot with batching."""
    try:
        # Split symbols into chunks to avoid rate limits
        chunk_size = 50
        symbol_chunks = [ALL_SYMBOLS[i:i + chunk_size] for i in range(0, len(ALL_SYMBOLS), chunk_size)]
        
        all_rows = []
        for chunk in symbol_chunks:
            # Fetch data for chunk
            intra = yf.download(chunk, period="1d", interval="5m", prepost=True, progress=False, group_by='ticker')
            hist = yf.download(chunk, period="5d", interval="1d", progress=False, group_by='ticker')
            
            for sym in chunk:
                try:
                    label = symbol_to_label.get(sym, sym)
                    
                    # Get price
                    if sym in intra and not intra[sym].empty:
                        price = intra[sym]['Close'].dropna().iloc[-1]
                    else:
                        price = hist[sym]['Close'].iloc[-1] if sym in hist else np.nan
                    
                    # Get previous close
                    if sym in hist and len(hist[sym]) >= 2:
                        prev_close = hist[sym]['Close'].iloc[-2]
                    else:
                        prev_close = price
                    
                    change = safe_divide(price - prev_close, prev_close) * 100
                    
                    # Calculate volume
                    if sym in intra and not intra[sym].empty:
                        today_vol = intra[sym]['Volume'].sum()
                    else:
                        today_vol = hist[sym]['Volume'].iloc[-1] if sym in hist else 0
                    
                    if sym in hist and len(hist[sym]) >= 5:
                        avg_vol = hist[sym]['Volume'].iloc[-5:-1].mean()
                    else:
                        avg_vol = today_vol
                    
                    rvol = safe_divide(today_vol, avg_vol, 1.0)
                    
                    all_rows.append({
                        "Asset": label,
                        "Symbol": sym,
                        "Price": round(price, 2) if not np.isnan(price) else 0,
                        "Change %": round(change, 2),
                        "RVOL": round(rvol, 2)
                    })
                except Exception:
                    continue
            
            time.sleep(0.5)  # Rate limiting between chunks
        
        return pd.DataFrame(all_rows)
    except Exception as e:
        st.error(f"Error fetching market data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def get_premarket_movers():
    """Optimized pre-market movers with multithreading."""
    try:
        tickers_to_check = ANALYST_SYMBOLS[:30]  # Limit for performance
        
        def fetch_premarket_data(sym):
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="2d", interval="1d")
                if len(hist) < 2:
                    return None
                
                prev_close = hist['Close'].iloc[-2]
                
                # Get pre-market data
                intra = ticker.history(period="1d", interval="1m", prepost=True)
                if intra.empty:
                    return None
                
                pre_data = intra.between_time('04:00', '09:30')
                if pre_data.empty:
                    return None
                
                pre_price = pre_data['Close'].iloc[-1]
                pre_volume = pre_data['Volume'].sum()
                gap_pct = safe_divide(pre_price - prev_close, prev_close) * 100
                
                if abs(gap_pct) > 0.5:  # Lower threshold to catch more movers
                    return {
                        "Symbol": sym,
                        "Asset": symbol_to_label.get(sym, sym),
                        "Pre-price": round(pre_price, 2),
                        "Prev Close": round(prev_close, 2),
                        "Gap %": round(gap_pct, 2),
                        "Pre Vol": int(pre_volume)
                    }
            except Exception:
                return None
            return None
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            results = list(executor.map(fetch_premarket_data, tickers_to_check))
        
        df = pd.DataFrame([r for r in results if r is not None])
        if not df.empty:
            df = df.sort_values("Gap %", ascending=False)
        return df
    except Exception as e:
        st.error(f"Error fetching pre-market: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def get_earnings_calendar_finnhub(date_str):
    """Enhanced earnings calendar with better error handling."""
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={date_str}&to={date_str}&token={FINNHUB_API_KEY}"
    
    try:
        with requests.Session() as session:
            r = session.get(url, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        
        earnings = []
        for item in data.get('earningsCalendar', []):
            symbol = item.get('symbol', '').upper()
            if not symbol:
                continue
                
            eps_est = item.get('epsEstimate')
            eps_act = item.get('epsActual')
            rev_est = item.get('revenueEstimate')
            rev_act = item.get('revenueActual')
            
            # Determine beats/misses
            if eps_act is not None and eps_est is not None:
                eps_result = "✅ Beat" if eps_act > eps_est else "❌ Miss" if eps_act < eps_est else "⚖️ Inline"
            else:
                eps_result = "—"
            
            if rev_act is not None and rev_est is not None:
                rev_result = "✅ Beat" if rev_act > rev_est else "❌ Miss" if rev_act < rev_est else "⚖️ Inline"
            else:
                rev_result = "—"
            
            earnings.append({
                "Symbol": symbol,
                "Company": item.get('name', symbol),
                "EPS Est": f"{eps_est:.2f}" if eps_est else "—",
                "EPS Act": f"{eps_act:.2f}" if eps_act else "—",
                "EPS": eps_result,
                "Rev Est (M)": f"{rev_est/1e6:.1f}" if rev_est else "—",
                "Rev Act (M)": f"{rev_act/1e6:.1f}" if rev_act else "—",
                "Rev": rev_result
            })
        
        return earnings
    except Exception as e:
        st.error(f"Error fetching earnings: {e}")
        return []

def get_todays_earnings():
    today = datetime.datetime.now(EST).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(today)
    for d in data: d["When"] = "Today"
    return data

def get_yesterdays_earnings():
    yest = (datetime.datetime.now(EST) - datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(yest)
    for d in data: d["When"] = "Yesterday"
    return data

def get_tomorrows_earnings():
    tom = (datetime.datetime.now(EST) + datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(tom)
    for d in data: d["When"] = "Tomorrow"
    return data

@st.cache_data(ttl=900, show_spinner=False)
def get_analyst_changes_yfinance(days_back=7):
    """Optimized analyst changes with multithreading."""
    all_changes = []
    
    def fetch_analyst_for_symbol(symbol):
        local_changes = []
        try:
            tk = yf.Ticker(symbol)
            rec = tk.recommendations
            if rec is not None and not rec.empty:
                cutoff = pd.Timestamp.now() - pd.Timedelta(days=days_back)
                recent = rec[rec.index >= cutoff]
                
                for idx, row in recent.iterrows():
                    firm = str(row.get('Firm', 'Unknown'))
                    # Check if firm is in tier1 list (partial match)
                    if any(tier1 in firm for tier1 in TIER1_FIRMS) or firm == 'Unknown':
                        local_changes.append({
                            "Date": idx.strftime('%Y-%m-%d'),
                            "Symbol": symbol,
                            "Asset": symbol_to_label.get(symbol, symbol),
                            "Firm": firm[:25],  # Truncate
                            "Action": row.get('Action', 'Change'),
                            "From": str(row.get('From Grade', '—'))[:15],
                            "To": str(row.get('To Grade', '—'))[:15]
                        })
        except Exception:
            pass
        return local_changes
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = executor.map(fetch_analyst_for_symbol, ANALYST_SYMBOLS)
        for res in results:
            all_changes.extend(res)
    
    df = pd.DataFrame(all_changes)
    if not df.empty:
        df = df.sort_values("Date", ascending=False).drop_duplicates(subset=["Date", "Symbol", "Firm", "To"])
    return df

@st.cache_data(ttl=300, show_spinner=False)
def get_pcr_data():
    """Enhanced put/call ratio with more symbols."""
    targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "TLT": "TLT"}
    results = []
    
    for label, sym in targets.items():
        try:
            tk = yf.Ticker(sym)
            opts = tk.options
            if opts:
                call_vol = put_vol = 0
                for exp in opts[:2]:  # Front 2 expirations
                    chain = tk.option_chain(exp)
                    call_vol += chain.calls['volume'].sum()
                    put_vol += chain.puts['volume'].sum()
                
                pcr = safe_divide(put_vol, call_vol)
                
                # Determine sentiment
                if pcr < 0.7:
                    sentiment = "🐂 Very Bull"
                elif pcr < 0.85:
                    sentiment = "🟢 Bull"
                elif pcr < 1.15:
                    sentiment = "⚖️ Neutral"
                elif pcr < 1.3:
                    sentiment = "🟠 Bear"
                else:
                    sentiment = "🐻 Very Bear"
                
                results.append({
                    "Asset": label,
                    "PCR": round(pcr, 2),
                    "Call Vol": int(call_vol),
                    "Put Vol": int(put_vol),
                    "Sentiment": sentiment
                })
        except Exception:
            continue
    
    return pd.DataFrame(results)

@st.cache_data(ttl=180, show_spinner=False)
def get_theme_stock_news(max_stocks=25):
    """Optimized news fetching with multithreading."""
    news_items = []
    
    def fetch_news_for_symbol(sym):
        local_news = []
        try:
            tk = yf.Ticker(sym)
            for n in tk.news[:3]:  # Limit to 3 per symbol
                title = n.get('title', '')
                if not title or len(title) < 10:  # Skip very short titles
                    continue
                
                sentiment, score = get_sentiment_score(title)
                local_news.append({
                    "Asset": symbol_to_label.get(sym, sym),
                    "Symbol": sym,
                    "Title": title[:150],  # Truncate long titles
                    "URL": n.get('link', ''),
                    "Source": n.get('publisher', 'Yahoo'),
                    "Sentiment": sentiment,
                    "Score": score,
                    "Time": datetime.datetime.fromtimestamp(n.get('providerPublishTime', 0)).strftime('%H:%M')
                })
        except Exception:
            pass
        return local_news
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = executor.map(fetch_news_for_symbol, ANALYST_SYMBOLS[:max_stocks])
        for res in results:
            news_items.extend(res)
    
    df = pd.DataFrame(news_items)
    if not df.empty:
        df = df.sort_values(by=['Score', 'Time'], ascending=[False, False]).drop_duplicates(subset=['Title'])
    return df

@st.cache_data(ttl=300, show_spinner=False)
def get_unusual_options_flow():
    """Enhanced unusual options flow scanner."""
    targets = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
    unusual = []
    
    for sym in targets:
        try:
            tk = yf.Ticker(sym)
            expirations = tk.options
            if not expirations:
                continue
            
            for exp in expirations[:2]:  # Front 2 expirations
                chain = tk.option_chain(exp)
                
                for opt_type, df in [('call', chain.calls), ('put', chain.puts)]:
                    for _, row in df.iterrows():
                        oi = row['openInterest']
                        vol = row['volume']
                        if oi > 10 and vol > oi * 1.5:  # Volume > 1.5x OI
                            unusual.append({
                                "Symbol": sym,
                                "Exp": exp[-5:],  # Short date
                                "Type": opt_type.upper(),
                                "Strike": row['strike'],
                                "Vol": int(vol),
                                "OI": int(oi),
                                "Vol/OI": round(safe_divide(vol, oi), 2),
                                "Premium": round(vol * row['lastPrice'] * 100 / 1_000_000, 1)  # Premium in millions
                            })
        except Exception:
            continue
    
    df = pd.DataFrame(unusual)
    if not df.empty:
        df = df.sort_values("Vol/OI", ascending=False)
    return df

@st.cache_data(ttl=300, show_spinner=False)
def get_gappers():
    """Enhanced gapper scanner with more metrics."""
    tickers = ANALYST_SYMBOLS[:75]  # Moderate limit
    
    def fetch_gap_data(sym):
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="2d", interval="1d")
            if len(hist) < 2:
                return None
            
            prev_close = hist['Close'].iloc[-2]
            today_open = hist['Open'].iloc[-1]
            gap_pct = safe_divide(today_open - prev_close, prev_close) * 100
            
            if abs(gap_pct) > 1.0:
                # Get current price
                current = ticker.history(period="1d", interval="1m")
                if not current.empty:
                    current_price = current['Close'].iloc[-1]
                    change_from_open = safe_divide(current_price - today_open, today_open) * 100
                    
                    # Calculate gap fill percentage
                    if gap_pct > 0:  # Gap up
                        filled = max(0, min(100, (current_price - today_open) / (prev_close * gap_pct/100) * 100))
                    else:  # Gap down
                        filled = max(0, min(100, (today_open - current_price) / (abs(prev_close * gap_pct/100)) * 100))
                    
                    return {
                        "Symbol": sym,
                        "Asset": symbol_to_label.get(sym, sym),
                        "Gap %": round(gap_pct, 2),
                        "Open": round(today_open, 2),
                        "Current": round(current_price, 2),
                        "Change": round(change_from_open, 2),
                        "Fill %": round(filled, 1)
                    }
        except Exception:
            return None
        return None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(fetch_gap_data, tickers))
    
    df = pd.DataFrame([r for r in results if r is not None])
    if not df.empty:
        df = df.sort_values("Gap %", ascending=False)
    return df

@st.cache_data(ttl=300, show_spinner=False)
def get_ath_atl():
    """Enhanced 52-week high/low scanner."""
    tickers = ANALYST_SYMBOLS[:75]
    records = []
    
    def check_extreme(sym):
        try:
            tk = yf.Ticker(sym)
            info = tk.info
            if not info:
                return None
            
            current = info.get('regularMarketPrice', 0)
            if current == 0:
                return None
            
            fifty_two_high = info.get('fiftyTwoWeekHigh', 0)
            fifty_two_low = info.get('fiftyTwoWeekLow', 0)
            
            if current >= fifty_two_high * 0.995:
                pct_from_high = safe_divide(current - fifty_two_high, fifty_two_high) * 100
                return {
                    "Symbol": sym,
                    "Asset": symbol_to_label.get(sym, sym),
                    "Price": round(current, 2),
                    "52W High": round(fifty_two_high, 2),
                    "From High %": round(pct_from_high, 1),
                    "Status": "🔥 NEW HIGH" if current >= fifty_two_high else "🟡 Near High"
                }
            elif current <= fifty_two_low * 1.005:
                pct_from_low = safe_divide(current - fifty_two_low, fifty_two_low) * 100
                return {
                    "Symbol": sym,
                    "Asset": symbol_to_label.get(sym, sym),
                    "Price": round(current, 2),
                    "52W Low": round(fifty_two_low, 2),
                    "From Low %": round(pct_from_low, 1),
                    "Status": "💧 NEW LOW" if current <= fifty_two_low else "🔵 Near Low"
                }
        except Exception:
            return None
        return None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(check_extreme, tickers))
    
    df = pd.DataFrame([r for r in results if r is not None])
    return df

def calculate_gamma_exposure(ticker: str) -> Tuple[pd.Series, float, float]:
    """Calculate gamma exposure with proper error handling."""
    try:
        tk = yf.Ticker(ticker)
        options = tk.options
        if not options:
            return pd.Series(), 0, 0
        
        spot = tk.history(period="1d")['Close'].iloc[-1]
        
        # Get options data
        all_options = []
        for exp in options[:3]:
            chain = tk.option_chain(exp)
            for opt_type in ['calls', 'puts']:
                df = getattr(chain, opt_type).copy()
                if not df.empty:
                    df['type'] = opt_type[:-1]
                    df['exp'] = exp
                    all_options.append(df)
        
        if not all_options:
            return pd.Series(), spot, spot
        
        df = pd.concat(all_options, ignore_index=True)
        
        # Calculate DTE
        exp_dates = pd.to_datetime(df['exp'])
        now = pd.Timestamp.now()
        df['dte'] = (exp_dates - now).dt.days / 365.0
        df = df[df['dte'] > 0].copy()
        
        if df.empty:
            return pd.Series(), spot, spot
        
        # Calculate GEX
        df['GEX'] = calc_gamma_vectorized(
            spot, 
            df['strike'].values, 
            df['dte'].values,
            df['impliedVolatility'].values, 
            0.04, 0.00,
            df['type'].values, 
            df['openInterest'].values
        )
        
        # Aggregate by strike
        gex_by_strike = df.groupby('strike')['GEX'].sum().sort_index()
        
        # Find gamma flip
        strikes = gex_by_strike.index.values
        values = gex_by_strike.values
        flip_level = spot
        
        for i in range(1, len(strikes)):
            if values[i-1] <= 0 and values[i] > 0:
                # Linear interpolation
                flip_level = strikes[i-1] + (0 - values[i-1]) * (strikes[i] - strikes[i-1]) / (values[i] - values[i-1])
                break
        
        return gex_by_strike, spot, flip_level
    except Exception as e:
        st.error(f"GEX calculation error: {e}")
        return pd.Series(), 0, 0

# ────────────────────────────────────────────────
#  UI COMPONENTS
# ────────────────────────────────────────────────

def render_sidebar():
    """Render enhanced sidebar with real-time data."""
    with st.sidebar:
        st.title("⚙️ Trading Dashboard")
        
        # Market status
        status, current_time = get_market_status()
        st.info(f"**{status}** | {current_time}")
        
        # Refresh controls
        col1, col2 = st.columns(2)
        with col1:
            refresh_rate = st.slider("Refresh (s)", 15, 120, 30, 5)
            st_autorefresh(interval=refresh_rate*1000, key="auto_refresh")
        with col2:
            if st.button("🔄 Refresh Now", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        
        st.divider()
        
        # Quick watchlist
        st.subheader("📌 Quick Watchlist")
        watchlist_input = st.text_area(
            "Enter symbols (comma separated)", 
            value="SPY, QQQ, NVDA, TSLA, AAPL",
            height=68,
            label_visibility="collapsed"
        )
        watchlist = [s.strip().upper() for s in watchlist_input.split(',') if s.strip()]
        
        if watchlist:
            with st.spinner("Loading..."):
                data = []
                for sym in watchlist:
                    try:
                        ticker = yf.Ticker(sym)
                        hist = ticker.history(period="1d")
                        if not hist.empty:
                            price = hist['Close'].iloc[-1]
                            change = safe_divide(price - hist['Open'].iloc[0], hist['Open'].iloc[0]) * 100
                            data.append({
                                "Symbol": sym,
                                "Price": f"${price:.2f}",
                                "Chg": f"{change:+.2f}%"
                            })
                    except:
                        continue
                
                if data:
                    st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)
        
        st.divider()
        
        # Market pulse
        st.subheader("📊 Market Pulse")
        try:
            spy = yf.Ticker("SPY").history(period="1d")['Close'].iloc[-1]
            vix = yf.Ticker("^VIX").history(period="1d")['Close'].iloc[-1]
            dxy = yf.Ticker("DX-Y.NYB").history(period="1d")['Close'].iloc[-1]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("SPY", f"${spy:.2f}")
                st.metric("VIX", f"{vix:.2f}")
            with col2:
                tnx = yf.Ticker("^TNX").history(period="1d")['Close'].iloc[-1]
                st.metric("10Y Yield", f"{tnx:.2f}%")
                st.metric("DXY", f"{dxy:.2f}")
        except:
            st.warning("Market data unavailable")
        
        return refresh_rate

# ────────────────────────────────────────────────
#  MAIN APP
# ────────────────────────────────────────────────

def main():
    # Render sidebar and get refresh rate
    refresh_rate = render_sidebar()
    st.session_state.last_refresh = datetime.datetime.now()
    
    # Main title
    st.title("🏛️ Alpha Terminal Pro - Day Trader Edition")
    st.caption(f"Real-time market data • Tracking {len(ALL_SYMBOLS)} symbols • Updated every {refresh_rate}s")
    
    # Fetch main market data
    with st.spinner("Loading market data..."):
        market_df = fetch_market_snapshot()
    
    if market_df.empty:
        st.error("Failed to load market data. Please refresh.")
        return
    
    # Create tabs
    tabs = st.tabs([
        "📈 Overview", "🌅 Pre-Market", "🚀 Gappers", "🎯 Themes",
        "📊 GEX", "🐳 Options Flow", "🎯 Earnings", "📊 Analyst", 
        "🔥 ATH/ATL", "📰 News", "⚡
