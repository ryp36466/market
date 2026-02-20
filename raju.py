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

# ────────────────────────────────────────────────
#  PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ────────────────────────────────────────────────
#  TICKER CONFIGS
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "S&P 500 (ES)": "ES=F", "Nasdaq (NQ)": "NQ=F", "Dow (YM)": "YM=F",
    "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "10Y Yield": "^TNX",
    "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
}
SECTOR_TICKERS = {
    "Tech (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV", "Disc (XLY)": "XLY", "Indus (XLI)": "XLI",
    "Utils (XLU)": "XLU", "RE": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"
}
MAG7_TICKERS = {
    "Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN",
    "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"
}
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **MAG7_TICKERS}

# Huge-cap filter for earnings
HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO'
}

# Tier-1 analyst firms
TIER1_FIRMS = {
    'Goldman Sachs', 'Morgan Stanley', 'JPMorgan', 'Bank of America', 'Citigroup', 'Barclays',
    'Evercore', 'UBS', 'Jefferies', 'RBC Capital', 'Deutsche Bank', 'Wells Fargo',
    'BofA Securities', 'Credit Suisse', 'Bernstein', 'Piper Sandler', 'Oppenheimer',
    'Wedbush', 'Stifel', 'Wolfe Research'
}

# ────────────────────────────────────────────────
#  HELPERS
# ────────────────────────────────────────────────

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

# ────────────────────────────────────────────────
#  EARNINGS – FINNHUB (replace key!)
# ────────────────────────────────────────────────
def get_earnings_calendar_finnhub(date_str):
    API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"  # ←←← PUT YOUR REAL KEY HERE
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={date_str}&to={date_str}&token={API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        filtered = []
        fallback = []
        for item in data.get('earningsCalendar', []):
            symbol = item.get('symbol', '').upper()
            entry = {
                "When": "",
                "Symbol": symbol,
                "Company": symbol,
                "EPS Est": item.get('epsEstimate'),
                "EPS Act": item.get('epsActual'),
                "Rev Est (B)": item.get('revenueEstimate') / 1e9 if item.get('revenueEstimate') else None,
                "Rev Act (B)": item.get('revenueActual') / 1e9 if item.get('revenueActual') else None,
            }
            entry["EPS Beat"] = "✅ Beat" if (entry["EPS Act"] or 0) > (entry["EPS Est"] or 0) else "❌ Miss" if entry["EPS Act"] is not None else "—"
            entry["Rev Beat"] = "✅ Beat" if (entry["Rev Act (B)"] or 0) > (entry["Rev Est (B)"] or 0) else "❌ Miss" if entry["Rev Act (B)"] is not None else "—"
            fallback.append(entry)
            if symbol in HUGE_CAP_SYMBOLS:
                filtered.append(entry)
        return filtered if filtered else fallback
    except Exception as e:
        st.error(f"Finnhub earnings error: {e}")
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

# ────────────────────────────────────────────────
#  TIER 1 ANALYST CHANGES – LAST 3 DAYS
# ────────────────────────────────────────────────
@st.cache_data(ttl=900)  # 15 min
def get_tier1_analyst_changes(days_back=3):
    start_date = datetime.date.today() - datetime.timedelta(days=days_back)

    urls = [
        "https://www.marketbeat.com/ratings/upgrades/",
        "https://www.marketbeat.com/ratings/downgrades/"
    ]

    changes = []

    for url in urls:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=12)
            soup = BeautifulSoup(r.text, 'html.parser')

            table = soup.find('table')
            if not table:
                continue

            rows = table.find_all('tr')[1:40]  # recent items

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 6:
                    continue

                date_str = cols[0].get_text(strip=True)
                try:
                    dt = datetime.datetime.strptime(date_str.split()[0], '%m/%d/%Y').date()
                    if dt < start_date:
                        continue
                except:
                    continue

                ticker = cols[1].get_text(strip=True)
                company = cols[2].get_text(strip=True)
                firm = cols[3].get_text(strip=True)
                action = cols[4].get_text(strip=True)
                rating = cols[5].get_text(strip=True)

                if firm not in TIER1_FIRMS:
                    continue

                try:
                    tk = yf.Ticker(ticker)
                    mcap = tk.info.get('marketCap', 0) / 1_000_000_000
                    if mcap < 1:
                        continue
                except:
                    continue

                changes.append({
                    "Date": date_str,
                    "Symbol": ticker,
                    "Company": company,
                    "Firm": firm,
                    "Action": action,
                    "Rating Change": rating,
                    "Market Cap (B)": round(mcap, 1) if mcap else "—"
                })
        except:
            continue

    df = pd.DataFrame(changes)
    if not df.empty:
        df = df.sort_values("Date", ascending=False).reset_index(drop=True)
    return df

# ────────────────────────────────────────────────
#  NEWS – FINVIZ
# ────────────────────────────────────────────────
def get_finviz_news_stable():
    try:
        return News().get_news()['news'].head(15).to_dict('records')
    except:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            r = requests.get("https://finviz.com/news.ashx", headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", id="news-table")
            if not table:
                return []
            news_list = []
            for row in table.find_all("tr")[:15]:
                cells = row.find_all("td")
                if len(cells) != 2:
                    continue
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

# ────────────────────────────────────────────────
#  MAIN UI
# ────────────────────────────────────────────────
market_df, intra_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Data as of {datetime.date.today()}")

tab_overview, tab_sectors, tab_gex, tab_options, tab_earnings, tab_analyst, tab_extremes, tab_news = st.tabs([
    "📈 Market Overview", "🔥 Alpha Sectors", "📊 GEX", "🐳 Options",
    "🎯 Earnings", "📊 Tier 1 Analyst Changes", "🔥 ATH/ATL Plays", "📰 News Wire"
])

with tab_overview:
    st.subheader("🗝️ Key Indices")
    key_df = market_df[market_df['Asset'].isin(["S&P 500", "SPY", "QQQ"])][['Asset', 'Price', 'Change %', 'RVOL']].round(2)
    st.dataframe(key_df.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)

    st.subheader("🚀 Magnificent 7")
    mag7_df = market_df[market_df['Asset'].isin(MAG7_TICKERS.keys())].copy().sort_values('Change %', ascending=False)
    spy_change = mag7_df[mag7_df['Asset'] == "SPY"]['Change %'].iloc[0] if not mag7_df[mag7_df['Asset'] == "SPY"].empty else 0
    mag7_df['vs SPY (%)'] = (mag7_df['Change %'] - spy_change).round(2)
    st.dataframe(mag7_df[['Asset', 'Price', 'Change %', 'vs SPY (%)', 'RVOL']].round(2)
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'vs SPY (%)', 'RVOL']),
                 hide_index=True, use_container_width=True)

with tab_sectors:
    sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    st.dataframe(sect_data[['Asset', 'Price', 'Change %', 'RVOL']]
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']),
                 hide_index=True, use_container_width=True)

with tab_gex:
    st.subheader("📊 Gamma Exposure (GEX) Analysis")
    user_ticker = st.text_input("Enter Ticker for GEX", value="SPY").upper().strip()
    if user_ticker:
        try:
            tk = yf.Ticker(user_ticker)
            options = tk.options
            if not options:
                st.warning("No options chain found.")
            else:
                spot = round(tk.history(period="1d")['Close'].iloc[-1], 2)
                st.write(f"**Current Price:** ${spot}")
                all_chains = []
                for exp in options[:3]:
                    ch = tk.option_chain(exp)
                    c = ch.calls.assign(type='call', exp=exp)
                    p = ch.puts.assign(type='put', exp=exp)
                    all_chains.extend([c, p])
                df_g = pd.concat(all_chains, ignore_index=True)
                df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365.0
                df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'].values, df_g['dte'].values,
                                                    df_g['impliedVolatility'].values, 0.04, 0.01,
                                                    df_g['type'].values, df_g['openInterest'].values)
                df_agg = (df_g.groupby('strike')['GEX'].sum() / 1e6).sort_index()
                df_agg = df_agg[df_agg.abs() > 0.01]
                fig = go.Figure(go.Bar(x=df_agg.index, y=df_agg.values,
                                       marker_color=['green' if x > 0 else 'red' for x in df_agg.values]))
                fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text=f"Spot ${spot}")
                fig.update_layout(template="plotly_dark", title=f"{user_ticker} Net Gamma Exposure", height=600)
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {str(e)}")

with tab_options:
    st.subheader("🐳 Put/Call Volume Ratio")
    pcr_df = get_pcr_data()
    if not pcr_df.empty:
        st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True, use_container_width=True)
    else:
        st.info("Gathering options flow...")

with tab_earnings:
    st.subheader("🎯 Earnings Calendar – Finnhub Powered")
    st.caption("Priority: Huge-cap stocks • If none reporting, shows all for that day • Revenue in $B")

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
                         .format(precision=2, na_rep="—", subset=['EPS Est', 'EPS Act', 'Rev Est (B)', 'Rev Act (B)'])

        st.dataframe(styled, hide_index=True, use_container_width=True)

        st.metric("Reports Shown", f"Today: {len(today_data)} | Yest: {len(yest_data)} | Tom: {len(tomorrow_data)}")
    else:
        st.info("No earnings data fetched (check Finnhub API key).")

with tab_analyst:
    st.subheader("📊 Tier 1 Analyst Upgrades / Downgrades – Last 3 Days")
    st.caption("Tier-1 firms only • Stocks with market cap > $1 billion • Sourced from MarketBeat")

    with st.spinner("Loading recent analyst actions..."):
        analyst_df = get_tier1_analyst_changes(days_back=5)

    if not analyst_df.empty:
        def highlight_action(val):
            if "Upgrade" in val:
                return 'background-color: #00cc66; color: black; font-weight: bold;'
            if "Downgrade" in val:
                return 'background-color: #ff4d4d; color: white; font-weight: bold;'
            return ''

        styled = analyst_df.style.applymap(highlight_action, subset=['Action']) \
                                .format(precision=1, na_rep="—", subset=['Market Cap (B)'])

        st.dataframe(styled, hide_index=True, use_container_width=True)

        st.success(f"Found {len(analyst_df)} qualifying changes")
    else:
        st.info("No recent Tier-1 analyst changes found for billion-dollar+ stocks (or data fetch issue).")

with tab_extremes:
    st.info("ATH/ATL scanner – coming soon")

with tab_news:
    st.subheader("📰 Market News & Sentiment")
    headlines = get_finviz_news_stable()
    if headlines:
        total_score = 0
        for item in headlines:
            title = item.get('Title') or item.get('title') or "No title"
            url = item.get('URL') or item.get('Link') or "#"
            source = item.get('Source') or "Finviz"
            label, score = get_sentiment_score(title)
            total_score += score
            with st.expander(f"{label} | {title}"):
                st.write(f"**Source:** {source}")
                st.write(f"[Full Story]({url})")
        st.sidebar.metric("Sentiment Pulse", total_score, delta="Positive" if total_score >= 0 else "Negative")
    else:
        st.error("News feed currently unavailable.")

st_autorefresh(interval=300000, key="global_refresh")  # 5 min
