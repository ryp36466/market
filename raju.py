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
from functools import lru_cache
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import concurrent.futures

# ────────────────────────────────────────────────
#  CONFIGURATION & CONSTANTS
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY", "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog")
EST = pytz.timezone('US/Eastern')

# Sentiment keywords
BULL_WORDS = {'upbeat', 'growth', 'surge', 'rally', 'beat', 'buy', 'bullish', 'expansion', 
              'profit', 'gain', 'positive', 'jump', 'upgrade', 'raise', 'strong', 
              'outperform', 'higher', 'rise', 'soar'}
BEAR_WORDS = {'slump', 'drop', 'fall', 'miss', 'sell', 'bearish', 'contraction', 
              'loss', 'negative', 'inflation', 'fear', 'risk', 'sink', 'downgrade', 
              'cut', 'weak', 'underperform', 'lower', 'decline', 'plunge'}

# ────────────────────────────────────────────────
#  TICKER CONFIGURATIONS (Required for references)
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
    "🥇 COMMODITIES/METALS": ["GC=F", "SLV", "AGQ", "ZSL", "ALB", "MP"]
}

ANALYST_SYMBOLS = sorted({sym for syms in TRADING_THEMES.values() for sym in syms})
HUGE_CAP_SYMBOLS = {'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
                   'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
                   'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO',
                   'HD', 'COST', 'NFLX', 'DIS', 'PFE', 'MRK', 'LLY', 'AVGO'}

# Build symbol to label mapping
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

# ────────────────────────────────────────────────
#  CACHED DATA FETCHERS
# ────────────────────────────────────────────────
@st.cache_data(ttl=45)
def fetch_market_snapshot() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fetch market data with parallel downloads."""
    with st.spinner("Fetching market data..."):
        hist_data = yf.download(ALL_SYMBOLS, period="5d", interval="1d", progress=False, threads=True)
        intra = yf.download(ALL_SYMBOLS, period="1d", interval="5m", prepost=True, progress=False, threads=True)
    
    rows = []
    for sym in ALL_SYMBOLS:
        try:
            price = intra['Close'][sym].dropna().iloc[-1]
            prev_close = hist_data['Close'][sym].iloc[-2]
            change = (price / prev_close - 1) * 100
            today_vol = intra['Volume'][sym].sum()
            avg_vol = hist_data['Volume'][sym].iloc[-5:-1].mean()
            
            rows.append({
                "Asset": symbol_to_label[sym],
                "Symbol": sym,
                "Price": price,
                "Change %": change,
                "RVOL": today_vol / avg_vol if avg_vol > 0 else 1.0
            })
        except Exception:
            continue
    
    return pd.DataFrame(rows), intra, hist_data

@st.cache_data(ttl=300)
def get_earnings_calendar(date_str: str) -> List[Dict]:
    """Fetch earnings with optimized filtering."""
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={date_str}&to={date_str}&token={FINNHUB_API_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json().get('earningsCalendar', [])
        
        results = []
        fallback = []
        
        for item in data:
            symbol = item.get('symbol', '').upper()
            eps_est, eps_act = item.get('epsEstimate'), item.get('epsActual')
            rev_est, rev_act = item.get('revenueEstimate'), item.get('revenueActual')
            
            def check_beat(actual, estimate):
                if actual is None or estimate is None:
                    return "—"
                return "✅ Beat" if actual > estimate else "❌ Miss" if actual < estimate else "Met"
            
            entry = {
                "Symbol": symbol,
                "Company": symbol,
                "EPS Est": eps_est if eps_est is not None else "—",
                "EPS Act": eps_act if eps_act is not None else "—",
                "Rev Est (B)": round(rev_est / 1e9, 2) if rev_est else "—",
                "Rev Act (B)": round(rev_act / 1e9, 2) if rev_act else "—",
                "EPS Beat": check_beat(eps_act, eps_est),
                "Rev Beat": check_beat(rev_act, rev_est)
            }
            
            (fallback if symbol not in HUGE_CAP_SYMBOLS else results).append(entry)
        
        return results if results else fallback
    except Exception:
        return []

def get_earnings_for_day(offset: int = 0) -> List[Dict]:
    """Get earnings for today (0), yesterday (-1), or tomorrow (1)."""
    target_date = (datetime.datetime.now(EST) + datetime.timedelta(days=offset)).date()
    data = get_earnings_calendar(target_date.strftime('%Y-%m-%d'))
    when = {0: "Today", -1: "Yesterday", 1: "Tomorrow"}.get(offset, "Other")
    for d in data:
        d["When"] = when
    return data

@st.cache_data(ttl=180)
def get_pcr_data() -> pd.DataFrame:
    """Calculate Put/Call ratios efficiently."""
    targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ"}
    
    results = []
    for label, symbol in targets.items():
        try:
            tk = yf.Ticker(symbol)
            if not tk.options:
                continue
            
            total_calls = total_puts = 0
            for exp in tk.options[:2]:
                chain = tk.option_chain(exp)
                total_calls += chain.calls['volume'].sum()
                total_puts += chain.puts['volume'].sum()
            
            if total_calls > 0:
                pcr = total_puts / total_calls
                sentiment = "🐂 Bull" if pcr < 0.85 else "🐻 Bear" if pcr > 1.15 else "⚖️ Neu"
                results.append({"Asset": label, "PCR": round(pcr, 2), "Sentiment": sentiment})
        except Exception:
            continue
    
    return pd.DataFrame(results)

def get_sentiment_score(text: str) -> Tuple[str, int]:
    """Optimized sentiment scoring using set intersection."""
    words = set(text.lower().split())
    bull_count = len(words & BULL_WORDS)
    bear_count = len(words & BEAR_WORDS)
    score = bull_count - bear_count
    
    if score > 2: return "🟢 Bullish", score
    if score < -2: return "🔴 Bearish", score
    if score > 0: return "🟡 Mild Bull", score
    if score < 0: return "🟠 Mild Bear", score
    return "⚪ Neutral", 0

def calc_gamma_vectorized(S: float, K: np.ndarray, T: np.ndarray, v: np.ndarray, 
                          r: float, q: float, types: np.ndarray, OI: np.ndarray) -> np.ndarray:
    """Vectorized Gamma calculation."""
    T = np.maximum(T, 1/365)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return np.where(types == 'call', val, -val)

@st.cache_data(ttl=600)
def get_theme_stock_news(max_stocks: int = 30) -> pd.DataFrame:
    """Fetch news with concurrent requests."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    news_items = []
    
    def fetch_single_news(sym: str) -> List[Dict]:
        try:
            f_sym = "BTC" if sym == "BTC-USD" else sym.split("=")[0]
            url = f"https://finviz.com/quote.ashx?t={f_sym.upper()}"
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", class_="news-table")
            
            if not table:
                return []
            
            items = []
            for row in table.find_all("tr")[:6]:
                tds = row.find_all("td")
                if len(tds) < 2:
                    continue
                time_str = tds[0].text.strip()
                a_tag = tds[1].find("a")
                if not a_tag or len(a_tag.text.strip()) < 20:
                    continue
                
                title = a_tag.text.strip()
                link = a_tag.get("href")
                if not link.startswith("http"):
                    link = "https://finviz.com" + link
                
                label, score = get_sentiment_score(title)
                items.append({
                    "Asset": symbol_to_label.get(sym, sym),
                    "Symbol": sym,
                    "Title": title,
                    "URL": link,
                    "Source": "Finviz",
                    "Sentiment": label,
                    "Score": score,
                    "Time": time_str
                })
            return items
        except Exception:
            return []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_single_news, sym): sym for sym in ANALYST_SYMBOLS[:max_stocks]}
        for future in concurrent.futures.as_completed(futures):
            news_items.extend(future.result())
    
    df = pd.DataFrame(news_items)
    if not df.empty:
        df = df.sort_values(by="Score", ascending=False).drop_duplicates(subset=["Title"])
    return df

@st.cache_data(ttl=3600)
def get_marketbeat_ratings() -> pd.DataFrame:
    """Scrape analyst ratings with optimized regex."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    ratings = []
    
    patterns = {
        'consensus': re.compile(r'Consensus Rating\s*([A-Za-z ]+)'),
        'target': re.compile(r'(?:Average )?Price Target\s*\$?([\d,]+\.?\d*)'),
        'upside': re.compile(r'Potential Upside/Downside\s*([+-]?\d+\.?\d*)%')
    }
    
    for sym in ANALYST_SYMBOLS:
        try:
            ticker = sym.replace("^", "").replace("=F", "").lower()
            for exchange in ["nasdaq", "nyse", "nyseamerican", "amex"]:
                url = f"https://www.marketbeat.com/stocks/{exchange}/{ticker}/"
                response = requests.get(url, headers=headers, timeout=12)
                
                if response.status_code != 200:
                    continue
                
                text = response.text
                consensus = patterns['consensus'].search(text)
                target = patterns['target'].search(text)
                upside = patterns['upside'].search(text)
                
                if consensus or target:
                    ratings.append({
                        "Asset": symbol_to_label.get(sym, sym),
                        "Symbol": sym,
                        "Consensus": consensus.group(1).strip() if consensus else "—",
                        "Target Price": target.group(1).replace(",", "") if target else "—",
                        "Upside %": upside.group(1) if upside else "—"
                    })
                    break
        except Exception:
            continue
    
    return pd.DataFrame(ratings)

@st.cache_data(ttl=300)
def get_macro_news() -> List[Dict]:
    """Fetch macro news with fallback."""
    try:
        return News().get_news()['news'].head(25).to_dict('records')
    except Exception:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get("https://finviz.com/news.ashx", headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", id="news-table")
            
            if not table:
                return []
            
            news_list = []
            for row in table.find_all("tr")[:25]:
                cells = row.find_all("td")
                if len(cells) != 2:
                    continue
                a = cells[1].find("a", class_="tab-link-news")
                if a:
                    news_list.append({
                        "Title": a.text.strip(),
                        "URL": a["href"],
                        "Source": "Finviz",
                        "Date": cells[0].text.strip()
                    })
            return news_list
        except Exception:
            return []

# ────────────────────────────────────────────────
#  UI COMPONENTS
# ────────────────────────────────────────────────
def render_dataframe(df: pd.DataFrame, columns: List[str], sort_by: Optional[str] = None):
    """Helper to render styled dataframes consistently."""
    if df.empty:
        st.warning("No data available")
        return
    
    display_df = df[columns].copy()
    if sort_by and sort_by in display_df.columns:
        display_df = display_df.sort_values(sort_by, ascending=False)
    
    numeric_cols = display_df.select_dtypes(include=[np.number]).columns
    st.dataframe(
        display_df.style.background_gradient(cmap='RdYlGn', subset=numeric_cols),
        hide_index=True,
        use_container_width=True
    )

def plot_relative_strength(hist_data: pd.DataFrame, benchmark: str, symbols: List[str], title: str):
    """Generate relative strength plot."""
    try:
        available_symbols = [s for s in ([benchmark] + symbols) if s in hist_data.columns]
        if len(available_symbols) < 2:
            st.error(f"Insufficient data for {title}")
            return
            
        plot_df = hist_data[available_symbols].dropna()
        normalized = (plot_df / plot_df.iloc[0] - 1) * 100
        
        fig = px.line(
            normalized.reset_index().melt(id_vars='Date', var_name='Ticker', value_name='Perf %'),
            x='Date', y='Perf %', color='Ticker', template="plotly_dark", height=500
        )
        fig.update_traces(patch={"line": {"width": 4, "dash": "dot"}}, selector={"name": benchmark})
        st.plotly_chart(fig, use_container_width=True)
        
        current_perf = normalized.iloc[-1]
        delta = (current_perf - current_perf[benchmark]).round(2).reset_index()
        delta.columns = ['Ticker', f'vs {benchmark} (%)']
        st.dataframe(delta.sort_values(f'vs {benchmark} (%)', ascending=False)
                    .style.background_gradient(cmap='RdYlGn'), hide_index=True, use_container_width=True)
    except Exception as e:
        st.error(f"RS Error: {e}")

def render_gex_analysis():
    """Gamma Exposure analysis component."""
    st.subheader("📊 Gamma Exposure (GEX) + Gamma Flip Level")
    st.caption("Front 3 expirations • Green = Long Gamma • Red = Short Gamma • Yellow = Gamma Flip")
    
    user_ticker = st.text_input("Enter Ticker for GEX Analysis", value="SPY").upper().strip()
    if not user_ticker:
        return
    
    try:
        tk = yf.Ticker(user_ticker)
        if not tk.options:
            st.warning("No options data found.")
            return
        
        spot = round(tk.history(period="1d")['Close'].iloc[-1], 2)
        
        chains = []
        for exp in tk.options[:3]:
            chain = tk.option_chain(exp)
            chains.extend([
                chain.calls.assign(type='call', exp=exp),
                chain.puts.assign(type='put', exp=exp)
            ])
        
        df_g = pd.concat(chains, ignore_index=True)
        df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365.0
        
        df_g['GEX'] = calc_gamma_vectorized(
            spot, df_g['strike'].values, df_g['dte'].values,
            df_g['impliedVolatility'].values, 0.04, 0.01,
            df_g['type'].values, df_g['openInterest'].values
        )
        
        df_agg = (df_g.groupby('strike')['GEX'].sum() / 1e6).sort_index()
        strikes, gex_vals = df_agg.index.values, df_agg.values
        
        flip_level = spot
        neg_mask = gex_vals < 0
        pos_mask = gex_vals > 0
        
        if np.any(neg_mask) and np.any(pos_mask):
            zero_crossings = np.where(np.diff(np.sign(gex_vals)))[0]
            if len(zero_crossings) > 0:
                i = zero_crossings[0]
                x1, y1 = strikes[i], gex_vals[i]
                x2, y2 = strikes[i+1], gex_vals[i+1]
                if y2 != y1:
                    flip_level = x1 - y1 * (x2 - x1) / (y2 - y1)
        
        flip_level = round(flip_level)
        total_gex = round(df_agg.sum(), 1)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("🔄 Gamma Flip Level", f"${flip_level:,}", 
                 f"{((spot - flip_level)/flip_level*100):+.1f}% vs spot")
        c2.metric("Net GEX", f"{total_gex}M", 
                 "🟢 Long Gamma" if total_gex > 0 else "🔴 Short Gamma")
        c3.metric("Current Spot", f"${spot:,.2f}")
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_agg.index, y=df_agg.values,
            marker_color=['#00ff88' if x > 0 else '#ff4444' for x in df_agg.values],
            name="GEX ($M)"
        ))
        fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text=f"Spot ${spot}")
        fig.add_vline(x=flip_level, line_dash="dot", line_color="#ffd700", line_width=3,
                     annotation_text=f"🔄 FLIP ${flip_level}")
        fig.update_layout(template="plotly_dark", height=560, xaxis_title="Strike", 
                         yaxis_title="GEX ($M)", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"GEX Error: {e}")

# ────────────────────────────────────────────────
#  MAIN APP
# ────────────────────────────────────────────────
def main():
    market_df, intra_data, hist_data = fetch_market_snapshot()
    time_now = datetime.datetime.now(EST).strftime('%H:%M:%S')
    
    st.title("🏛️ Alpha Terminal Pro")
    st.caption(f"EST {time_now} | Data as of {datetime.date.today()}")
    
    tabs = st.tabs([
        "📈 Market Overview", "🔥 Sectors", "🎯 Themes", "⚖️ Rel Strength",
        "📊 GEX", "🐳 Options", "🎯 Earnings", "📊 Analyst Ratings",
        "🌍 Macro", "🔥 Extremes", "📰 News"
    ])
    
    with tabs[0]:  # Market Overview
        st.subheader("🗝️ Key Indices")
        key_df = market_df[market_df['Asset'].isin(["S&P 500", "SPY", "QQQ"])]
        render_dataframe(key_df, ['Asset', 'Price', 'Change %', 'RVOL'], 'Change %')
        
        st.subheader("🚀 Magnificent 7")
        mag7_df = market_df[market_df['Symbol'].isin(list(MAG7_TICKERS.values()))].copy()
        spy_row = market_df[market_df['Symbol'] == 'SPY']
        spy_change = spy_row['Change %'].iloc[0] if not spy_row.empty else 0
        mag7_df['vs SPY (%)'] = (mag7_df['Change %'] - spy_change).round(2)
        render_dataframe(mag7_df, ['Asset', 'Price', 'Change %', 'vs SPY (%)', 'RVOL'], 'Change %')
    
    with tabs[1]:  # Sectors
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Major ETFs")
            sect_df = market_df[market_df['Symbol'].isin(list(SECTOR_TICKERS.values()))]
            render_dataframe(sect_df, ['Asset', 'Price', 'Change %', 'RVOL'])
        with c2:
            st.subheader("☁️ Neo Clouds")
            neo_df = market_df[market_df['Symbol'].isin(list(NEO_CLOUD_TICKERS.values()))]
            render_dataframe(neo_df, ['Asset', 'Price', 'Change %', 'RVOL'])
    
    with tabs[2]:  # Themes
        st.subheader("🎯 Active Trading Themes")
        cols = st.columns(2)
        for i, (theme, tickers) in enumerate(TRADING_THEMES.items()):
            with cols[i % 2]:
                st.markdown(f"**{theme}**")
                theme_df = market_df[market_df['Symbol'].isin(tickers)]
                if not theme_df.empty:
                    render_dataframe(theme_df, ['Asset', 'Price', 'Change %', 'RVOL'], 'Change %')
                else:
                    st.warning(f"No data for {theme}")
    
    with tabs[3]:  # Relative Strength
        st.subheader("⚖️ Sector Strength vs SPY")
        plot_relative_strength(hist_data['Close'], "SPY", list(SECTOR_TICKERS.values()), "Sectors vs SPY")
        
        st.subheader("⚖️ Mag7 Strength vs QQQ")
        plot_relative_strength(hist_data['Close'], "QQQ", list(MAG7_TICKERS.values()), "Mag7 vs QQQ")
    
    with tabs[4]:  # GEX
        render_gex_analysis()
    
    with tabs[5]:  # Options
        st.subheader("🐳 Put/Call Volume Ratio")
        pcr_df = get_pcr_data()
        if not pcr_df.empty:
            st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), 
                        hide_index=True, use_container_width=True)
    
    with tabs[6]:  # Earnings
        st.subheader("🎯 Earnings Calendar")
        all_earnings = get_earnings_for_day(-1) + get_earnings_for_day(0) + get_earnings_for_day(1)
        if all_earnings:
            df = pd.DataFrame(all_earnings)
            
            def highlight_beats(val):
                if val == "✅ Beat":
                    return 'background-color: #00cc66; color: black; font-weight: bold;'
                elif val == "❌ Miss":
                    return 'background-color: #ff4d4d; color: white; font-weight: bold;'
                return ''
            
            st.dataframe(df.style.applymap(highlight_beats, subset=['EPS Beat', 'Rev Beat']),
                        hide_index=True, use_container_width=True)
    
    with tabs[7]:  # Analyst
        st.subheader("📊 Analyst Ratings (MarketBeat)")
        analyst_df = get_marketbeat_ratings()
        if not analyst_df.empty:
            price_map = market_df.set_index('Symbol')['Price'].to_dict()
            analyst_df['Current Price'] = analyst_df['Symbol'].map(price_map)
            analyst_df['Target Price'] = pd.to_numeric(analyst_df['Target Price'], errors='coerce')
            analyst_df['Current Price'] = pd.to_numeric(analyst_df['Current Price'], errors='coerce')
            analyst_df['Upside %'] = ((analyst_df['Target Price'] - analyst_df['Current Price']) / 
                                     analyst_df['Current Price'] * 100).round(1)
            
            def rating_color(val):
                val_str = str(val)
                if "Strong Buy" in val_str or "Buy" in val_str:
                    return 'background-color: #00cc66; color: black; font-weight: bold;'
                if "Hold" in val_str:
                    return 'background-color: #ffcc66; color: black;'
                if "Sell" in val_str:
                    return 'background-color: #ff6666; color: white;'
                return ''
            
            st.dataframe(
                analyst_df[['Asset', 'Symbol', 'Consensus', 'Target Price', 'Current Price', 'Upside %']]
                .style.applymap(rating_color, subset=['Consensus'])
                .background_gradient(cmap='RdYlGn', subset=['Upside %'])
                .format({"Target Price": "${:,.2f}", "Current Price": "${:,.2f}", "Upside %": "{:+.1f}%"}),
                hide_index=True,
                use_container_width=True
            )
    
    with tabs[8]:  # Macro
        st.subheader("🌍 Macro & Market-Moving News")
        macro_news = get_macro_news()
        if macro_news:
            total_score = 0
            keywords = {'trump', 'president', 'white house', 'tariff', 'election', 'fed', 'inflation'}
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### 📈 All Macro Headlines")
                for item in macro_news[:15]:
                    label, score = get_sentiment_score(item.get('Title', ''))
                    total_score += score
                    title = item.get('Title', '')
                    with st.expander(f"{label} | {title[:85]}{'...' if len(title) > 85 else ''}"):
                        st.write(f"**Source:** {item.get('Source')} | {item.get('Date')}")
                        st.write(f"[🔗 Read]({item.get('URL')})")
            
            with c2:
                st.markdown("### 🇺🇸 Political Impact")
                trump_news = [n for n in macro_news if any(k in n.get('Title', '').lower() for k in keywords)]
                if trump_news:
                    for item in trump_news[:10]:
                        label, _ = get_sentiment_score(item.get('Title', ''))
                        title = item.get('Title', '')
                        with st.expander(f"{label} | {title[:80]}{'...' if len(title) > 80 else ''}"):
                            st.write(f"[🔗 Read]({item.get('URL')})")
                else:
                    st.info("No major political headlines")
            
            st.sidebar.metric("Macro Sentiment", total_score,
                            delta="Bullish" if total_score >= 0 else "Bearish")
    
    with tabs[9]:  # Extremes
        st.info("ATH/ATL scanner – coming soon")
    
    with tabs[10]:  # News
        st.subheader("📰 Theme Stocks News")
        news_df = get_theme_stock_news()
        if not news_df.empty:
            total_score = news_df['Score'].sum()
            st.sidebar.metric("Theme Sentiment", total_score,
                            delta="Positive" if total_score >= 0 else "Negative")
            
            for _, row in news_df.iterrows():
                title = row['Title']
                with st.expander(f"{row['Sentiment']} {row['Asset']} | {title[:88]}{'...' if len(title) > 88 else ''} • {row['Time']}"):
                    st.write(f"[🔗 Read]({row['URL']})")

if __name__ == "__main__":
    main()
    st_autorefresh(interval=300000, key="global_refresh")
