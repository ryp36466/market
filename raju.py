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

# Huge / large-cap filter: only show these in earnings table
HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO'
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

# ========================== EARNINGS (huge-cap filter) ==========================
def get_earnings_for_date(date_str):
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_str}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nasdaq.com/"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        rows = []
        if data.get('data', {}).get('rows'):
            for row in data['data']['rows']:
                symbol = row.get('symbol', '').upper()
                if symbol not in HUGE_CAP_SYMBOLS:
                    continue
                
                company = row.get('companyName', symbol)
                
                eps_est = row.get('epsForecast')
                eps_act = row.get('epsActual')
                rev_est = row.get('revenueForecast')
                rev_act = row.get('revenueActual')
                
                try: eps_est = float(eps_est) if eps_est else None
                except: eps_est = None
                try: eps_act = float(eps_act) if eps_act else None
                except: eps_act = None
                try: rev_est = float(rev_est) if rev_est else None
                except: rev_est = None
                try: rev_act = float(rev_act) if rev_act else None
                except: rev_act = None
                
                eps_beat = eps_act > eps_est if eps_act is not None and eps_est is not None else None
                rev_beat = rev_act > rev_est if rev_act is not None and rev_est is not None else None
                
                eps_surprise = round(((eps_act - eps_est) / abs(eps_est) * 100), 2) if eps_act is not None and eps_est and eps_est != 0 else None
                rev_surprise = round(((rev_act - rev_est) / abs(rev_est) * 100), 2) if rev_act is not None and rev_est and rev_est != 0 else None
                
                rows.append({
                    "When": "",
                    "Symbol": symbol,
                    "Company": company,
                    "EPS Est": eps_est,
                    "EPS Act": eps_act,
                    "EPS Surprise %": eps_surprise,
                    "Rev Est (B)": rev_est / 1e9 if rev_est else None,
                    "Rev Act (B)": rev_act / 1e9 if rev_act else None,
                    "Rev Surprise %": rev_surprise,
                    "EPS Beat": "✅ Beat" if eps_beat else "❌ Miss" if eps_beat is False else "—",
                    "Rev Beat": "✅ Beat" if rev_beat else "❌ Miss" if rev_beat is False else "—",
                })
        return rows
    except:
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
                # Future dates
                future = hist[hist.index > now]
                if not future.empty:
                    next_date = future.index[0].strftime('%Y-%m-%d')
                    if next_date == today_str:
                        is_today = True

                # Latest reported
                reported = hist.dropna(subset=['Reported EPS'])
                if not reported.empty:
                    recent = reported.iloc[0]
                    latest_eps = round(recent['Reported EPS'], 2) if 'Reported EPS' in recent else "N/A"
                    if 'Surprise(%)' in recent:
                        surprise_pct = round(recent['Surprise(%)'], 2)
                        status = "✅ Beat" if surprise_pct > 0 else "❌ Miss" if surprise_pct < 0 else "Met"

        except Exception:
            # Silent fail → keep defaults
            pass

        earnings_list.append({
            "Asset": label,
            "Next Date": next_date,
            "Last EPS": latest_eps,
            "Surprise (%)": surprise_pct,
            "Status": status,
            "Today?": "📢 TODAY" if is_today else ""
        })

    df = pd.DataFrame(earnings_list)
    return df

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
st.caption(f"EST {time_now} | Earnings: Huge-Cap / Mega-Cap Only")

tab_overview, tab_sectors, tab_gex, tab_options, tab_earnings, tab_extremes, tab_news = st.tabs([
    "📈 Market Overview", "🔥 Alpha Sectors", "📊 GEX", "🐳 Options",
    "🎯 Earnings", "🔥 ATH/ATL Plays", "📰 News Wire"
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

    st.subheader("📉 Intraday Price Action")
    cols = st.columns(3)
    for i, (ticker, name) in enumerate([('SPY','SPY'), ('QQQ','QQQ'), ('^GSPC','S&P 500')]):
        with cols[i]:
            if ticker in intra_data['Close'].columns:
                fig = px.line(intra_data['Close'][ticker].dropna(), title=name)
                fig.update_layout(template="plotly_dark", height=400)
                st.plotly_chart(fig, use_container_width=True)

    selected_mag = st.selectbox("MAG7 Intraday Detail", list(MAG7_TICKERS.keys()))
    sym = MAG7_TICKERS[selected_mag]
    if sym in intra_data['Close'].columns:
        fig = px.line(intra_data['Close'][sym].dropna(), title=f"{selected_mag} Intraday")
        fig.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)

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
    st.subheader("🎯 Earnings – Mega / Huge-Cap Focus Only")
    st.caption("Showing only major companies (Walmart, Deere, Alibaba, Southern Co., Newmont, Booking + MAG7 when reporting) • Revenue in $B")

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
                             'EPS Est', 'EPS Act', 'EPS Surprise %',
                             'Rev Est (B)', 'Rev Act (B)', 'Rev Surprise %'
                         ])

        st.dataframe(styled, hide_index=True, use_container_width=True)

        st.metric("Reports Summary", f"Today: {len(today_data)} | Yesterday: {len(yest_data)} | Tomorrow: {len(tomorrow_data)}")
    else:
        st.info("No huge-cap earnings found for today/yesterday/tomorrow (or temporary API issue).")

    # MAG7 upcoming – with safety checks
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
            st.info(f"🚀 **Next MAG7 catalyst:** {next_c['Asset']} on **{next_c['Next Date']}** ({day_txt})")
        else:
            st.info("No upcoming MAG7 earnings dates available right now.")
    else:
        st.info("MAG7 upcoming earnings data currently unavailable (yfinance fetch issue).")

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
