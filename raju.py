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

# ========================== PAGE CONFIG ==========================
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ========================== TICKER CONFIGS ==========================
GLOBAL_TICKERS = {
    "S&P 500 (ES)": "ES=F", "Nasdaq (NQ)": "NQ=F", "Dow (YM)": "YM=F",
    "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "10Y Yield": "^TNX",
    "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
}
SECTOR_TICKERS = {"Tech (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE",
                  "Healthcare (XLV)": "XLV", "Disc (XLY)": "XLY", "Indus (XLI)": "XLI",
                  "Utils (XLU)": "XLU", "RE": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"}
MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN",
                "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **MAG7_TICKERS}

# Huge / large-cap filter
HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO'
    # Add more mega-caps as needed
}

# ========================== CORE HELPERS ==========================
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
                results.append({"Asset": label, "PCR": round(pcr, 2),
                                "Sentiment": "🐂 Bull" if pcr < 0.85 else "🐻 Bear" if pcr > 1.15 else "⚖️ Neu"})
        except:
            continue
    return pd.DataFrame(results)

def get_sentiment_score(text):
    bull = ['upbeat','growth','surge','rally','beat','buy','bullish','expansion','profit','gain','positive','jump']
    bear = ['slump','drop','fall','miss','sell','bearish','contraction','loss','negative','inflation','fear','risk','sink']
    score = sum(1 for w in bull if w in text.lower()) - sum(1 for w in bear if w in text.lower())
    if score > 0: return "🟢 Bullish", score
    if score < 0: return "🔴 Bearish", score
    return "⚪ Neutral", 0

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
        except:
            continue
    return pd.DataFrame(rows), intra

# ========================== YOUR IMPROVED EARNINGS FUNCTION ==========================
def get_earnings_for_date(date_str):
    # Standardizing headers to mimic a modern browser
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/"
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        all_rows = []
        filtered_rows = []
        
        payload = data.get('data')
        if payload and payload.get('rows'):
            for row in payload['rows']:
                symbol = row.get('symbol', '').upper()
                
                # Helper to clean currency strings into floats
                def to_f(val):
                    try:
                        return float(val.replace('$', '').replace(',', '')) if val else None
                    except:
                        return None

                # Constructing the standardized data object
                entry = {
                    "When": "",
                    "Symbol": symbol,
                    "Company": row.get('companyName', symbol),
                    "EPS Est": to_f(row.get('epsForecast')),
                    "EPS Act": to_f(row.get('epsActual')),
                    "Rev Est (B)": to_f(row.get('revenueForecast')) / 1e9 if to_f(row.get('revenueForecast')) else None,
                    "Rev Act (B)": to_f(row.get('revenueActual')) / 1e9 if to_f(row.get('revenueActual')) else None,
                }

                # Calculate Beats
                entry["EPS Beat"] = "✅ Beat" if (entry["EPS Act"] or 0) > (entry["EPS Est"] or 0) else "❌ Miss" if entry["EPS Act"] is not None else "—"
                entry["Rev Beat"] = "✅ Beat" if (entry["Rev Act (B)"] or 0) > (entry["Rev Est (B)"] or 0) else "❌ Miss" if entry["Rev Act (B)"] is not None else "—"

                all_rows.append(entry)
                if symbol in HUGE_CAP_SYMBOLS:
                    filtered_rows.append(entry)

        # FALLBACK: If no Huge Cap stocks found, return all available stocks for that day
        return filtered_rows if filtered_rows else all_rows
        
    except Exception as e:
        st.error(f"Error fetching data for {date_str}: {e}")
        return []

def get_todays_earnings():
    est = pytz.timezone('US/Eastern')
    today = datetime.datetime.now(est).date().strftime('%Y-%m-%d')
    data = get_earnings_for_date(today)
    for d in data: d["When"] = "Today"
    return data

def get_yesterdays_earnings():
    est = pytz.timezone('US/Eastern')
    yesterday = (datetime.datetime.now(est) - datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    data = get_earnings_for_date(yesterday)
    for d in data: d["When"] = "Yesterday"
    return data

def get_tomorrows_earnings():
    est = pytz.timezone('US/Eastern')
    tomorrow = (datetime.datetime.now(est) + datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    data = get_earnings_for_date(tomorrow)
    for d in data: d["When"] = "Tomorrow"
    return data

@st.cache_data(ttl=1800)
def get_earnings_data(ticker_dict: dict):
    earnings_list = []
    est = pytz.timezone('US/Eastern')
    now = datetime.datetime.now(est)
    today_str = now.strftime('%Y-%m-%d')

    for label, sym in ticker_dict.items():
        # Define defaults FIRST — prevents UnboundLocalError
        next_date = "TBD"
        latest_eps = "N/A"
        surprise_pct = 0.0
        status = "—"
        is_today = False

        try:
            tk = yf.Ticker(sym)
            hist = tk.get_earnings_dates(limit=12)

            if hist is not None and not hist.empty:
                future = hist[hist.index > now]
                if not future.empty:
                    next_date = future.index[0].strftime('%Y-%m-%d')
                    if next_date == today_str:
                        is_today = True

                reported = hist.dropna(subset=['Reported EPS'])
                if not reported.empty:
                    recent = reported.iloc[0]
                    latest_eps = round(recent['Reported EPS'], 2) if 'Reported EPS' in recent else "N/A"
                    if 'Surprise(%)' in recent:
                        surprise_pct = round(recent['Surprise(%)'], 2)
                        status = "✅ Beat" if surprise_pct > 0 else "❌ Miss" if surprise_pct < 0 else "Met"

        except Exception:
            pass  # keep defaults

        earnings_list.append({
            "Asset": label,
            "Next Date": next_date,
            "Last EPS": latest_eps,
            "Surprise (%)": surprise_pct,
            "Status": status,
            "Today?": "📢 TODAY" if is_today else ""
        })

    return pd.DataFrame(earnings_list)

# ========================== NEWS ==========================
def get_finviz_news_stable():
    try:
        return News().get_news()['news'].head(15).to_dict('records')
    except:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get("https://finviz.com/news.ashx", headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", id="news-table")
            if not table: return []
            news_list = []
            for row in table.find_all("tr")[:15]:
                cells = row.find_all("td")
                if len(cells) != 2: continue
                a = cells[1].find("a", class_="tab-link-news")
                if a:
                    news_list.append({
                        "Title": a.text.strip(),
                        "URL": a["href"],
                        "Source": cells[1].find("div", class_="news-link-right").get_text(strip=True).strip("() ") if cells[1].find("div", class_="news-link-right") else "Finviz",
                        "Date": cells[0].text.strip()
                    })
            return news_list
        except:
            return []

# ========================== MAIN UI ==========================
market_df, intra_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Earnings: Huge-Cap priority + fallback to all if none")

tab_overview, tab_sectors, tab_gex, tab_options, tab_earnings, tab_extremes, tab_news = st.tabs([
    "📈 Market Overview", "🔥 Alpha Sectors", "📊 GEX", "🐳 Options",
    "🎯 Earnings", "🔥 ATH/ATL Plays", "📰 News Wire"
])

# Overview, Sectors, GEX, Options tabs remain unchanged — copy from your previous working version if needed

with tab_earnings:
    st.subheader("🎯 Earnings Calendar – Huge-Cap Priority")
    st.caption("Shows huge-cap stocks first • If none reporting, shows all for that day • Revenue in $B")

    today_data    = get_todays_earnings()
    yest_data     = get_yesterdays_earnings()
    tomorrow_data = get_tomorrows_earnings()

    all_events = today_data + yest_data + tomorrow_data

    if all_events:
        df = pd.DataFrame(all_events)
        
        order = {"Yesterday": 0, "Today": 1, "Tomorrow": 2}
        df['sort_key'] = df['When'].map(order).fillna(999)
        df = df.sort_values(['sort_key', 'Symbol']).drop(columns=['sort_key'])

        def highlight_beats(val):
            if val == "✅ Beat": return 'background-color: #00cc66; color: black; font-weight: bold;'
            if val == "❌ Miss": return 'background-color: #ff4d4d; color: white; font-weight: bold;'
            return ''

        styled = df.style.applymap(highlight_beats, subset=['EPS Beat', 'Rev Beat']) \
                         .format(precision=2, na_rep="—", subset=[
                             'EPS Est', 'EPS Act', 'Rev Est (B)', 'Rev Act (B)'
                         ])

        st.dataframe(styled, hide_index=True, use_container_width=True)

        st.metric("Reports Shown", f"Today: {len(today_data)} | Yest: {len(yest_data)} | Tom: {len(tomorrow_data)}")
    else:
        st.info("No earnings data available right now for today/yesterday/tomorrow (API may be down).")

    # MAG7 upcoming
    mag_next = get_earnings_data(MAG7_TICKERS)

    if not mag_next.empty and 'Next Date' in mag_next.columns:
        upcoming = mag_next[
            mag_next['Next Date'].notna() &
            (mag_next['Next Date'] != "TBD")
        ].copy()

        if not upcoming.empty:
            upcoming['Next Date dt'] = pd.to_datetime(upcoming['Next Date'], errors='coerce')
            upcoming = upcoming.sort_values('Next Date dt').reset_index(drop=True)
            next_c = upcoming.iloc[0]
            days = (next_c['Next Date dt'].date() - datetime.datetime.now(est).date()).days
            day_txt = "TODAY" if days == 0 else "tomorrow" if days == 1 else f"in {days} days" if days > 0 else f"{abs(days)} days ago"
            st.info(f"🚀 **Next MAG7:** {next_c['Asset']} on **{next_c['Next Date']}** ({day_txt})")
        else:
            st.info("No upcoming MAG7 earnings dates right now.")
    else:
        st.info("MAG7 upcoming data unavailable (yfinance issue).")

with tab_extremes:
    st.info("ATH/ATL scanner – coming soon")

with tab_news:
    st.subheader("📰 Market News & Sentiment")
    headlines = get_finviz_news_stable()
    if headlines:
        total_score = 0
        for item in headlines:
            title = item.get('Title') or "No title"
            url = item.get('URL') or "#"
            source = item.get('Source') or "Finviz"
            label, score = get_sentiment_score(title)
            total_score += score
            with st.expander(f"{label} | {title}"):
                st.write(f"**Source:** {source}")
                st.write(f"[Link]({url})")
        st.sidebar.metric("Sentiment Pulse", total_score, delta="Positive" if total_score >= 0 else "Negative")
    else:
        st.error("News feed currently unavailable.")

st_autorefresh(interval=30000, key="global_refresh")
