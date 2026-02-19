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

# ========================== PASSWORD PROTECTION ==========================
def check_password():
    if st.session_state.get("password_correct"): return True
    def password_entered():
        if st.session_state["password"] == "Pratimap9!@":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.title("🔐 Pro Market Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Access Denied")
        return False
    return True

if not check_password(): st.stop()

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
        except: continue
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
        except: continue
    return pd.DataFrame(rows), intra

# ========================== EARNINGS (MAG7 + TODAY) ==========================
@st.cache_data(ttl=3600)
def get_earnings_data(ticker_dict: dict):
    earnings_list = []
    est = pytz.timezone('US/Eastern')
    now = datetime.datetime.now(est)
    today_str = now.strftime('%Y-%m-%d')
    for label, sym in ticker_dict.items():
        try:
            tk = yf.Ticker(sym)
            hist = tk.get_earnings_dates(limit=12)
            next_date = "TBD"
            latest_eps = "N/A"
            surprise_pct = 0.0
            status = "—"
            is_today = False
            if hist is not None and not hist.empty:
                future = hist[hist.index > now]
                if not future.empty:
                    next_date = future.index[0].strftime('%Y-%m-%d')
                    if next_date == today_str: is_today = True
                reported = hist.dropna(subset=['Reported EPS'])
                if not reported.empty:
                    recent = reported.iloc[0]
                    latest_eps = round(recent['Reported EPS'], 2)
                    if 'Surprise(%)' in recent:
                        surprise_pct = round(recent['Surprise(%)'], 2)
                        status = "✅ Beat" if surprise_pct > 0 else "❌ Miss" if surprise_pct < 0 else "Met"
            earnings_list.append({
                "Asset": label, "Next Date": next_date, "Last EPS": latest_eps,
                "Surprise (%)": surprise_pct, "Status": status,
                "Today?": "📢 TODAY" if is_today else ""
            })
        except: continue
    return pd.DataFrame(earnings_list)

def get_todays_earnings():
    est = pytz.timezone('US/Eastern')
    today = datetime.datetime.now(est).date().strftime('%Y-%m-%d')
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={today}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nasdaq.com/"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get('data', {}).get('rows'):
            return [{"Asset": row.get('companyName', row['symbol']), "Symbol": row['symbol']}
                    for row in data['data']['rows'][:30]]
        return []
    except: return []

# ========================== NEW: YESTERDAY ATH/ATL PLAYS ==========================
def get_yesterdays_earnings():
    est = pytz.timezone('US/Eastern')
    yesterday = (datetime.datetime.now(est) - datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={yesterday}"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nasdaq.com/"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get('data', {}).get('rows'):
            return [{"Asset": row.get('companyName', row['symbol']), "Symbol": row['symbol']}
                    for row in data['data']['rows'][:40]]
        return []
    except: return []

def get_ath_atl_earnings_plays():
    yest = get_yesterdays_earnings()
    results = []
    for item in yest:
        sym = item["Symbol"]
        try:
            tk = yf.Ticker(sym)
            info = tk.info
            price = info.get('currentPrice') or info.get('regularMarketPrice') or tk.history(period="1d")['Close'].iloc[-1]
            ath = info.get('fiftyTwoWeekHigh')
            atl = info.get('fiftyTwoWeekLow')
            if not ath or not atl: continue

            dist_ath = round((ath - price) / ath * 100, 2)
            dist_atl = round((price - atl) / atl * 100, 2)
            if dist_ath > 5 and dist_atl > 5: continue

            roe = info.get('returnOnEquity', 0)
            debt_eq = info.get('debtToEquity', 999)
            profit_m = info.get('profitMargins', 0)

            if roe > 0.15 and debt_eq < 0.8 and profit_m > 0.15:
                near = "ATH" if dist_ath <= 5 else "ATL"
                dist = dist_ath if near == "ATH" else dist_atl
                results.append({
                    "Ticker": sym,
                    "Company": item["Asset"][:40],
                    "Price": round(price, 2),
                    "Near": near,
                    "Dist %": dist,
                    "ROE %": round(roe * 100, 1),
                    "Debt/Eq": round(debt_eq, 2),
                    "Profit Margin %": round(profit_m * 100, 1)
                })
        except: continue
    return pd.DataFrame(results)

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
        except: return []

# ========================== MAIN UI ==========================
market_df, intra_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Performance: STABLE")

tab_overview, tab_sectors, tab_gex, tab_options, tab_earnings, tab_extremes, tab_news = st.tabs([
    "📈 Market Overview", "🔥 Alpha Sectors", "📊 GEX", "🐳 Options",
    "🎯 Earnings", "🔥 ATH/ATL Plays", "📰 News Wire"
])

# ==================== OVERVIEW ====================
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

# ==================== SECTORS ====================
with tab_sectors:
    sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    st.dataframe(sect_data[['Asset', 'Price', 'Change %', 'RVOL']]
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']),
                 hide_index=True, use_container_width=True)

# ==================== GEX ====================
with tab_gex:
    st.subheader("📊 Gamma Exposure (GEX) Analysis")
    user_ticker = st.text_input("Enter Ticker for GEX", value="SPY", help="SPY, QQQ, NVDA...").upper().strip()
    if user_ticker:
        try:
            tk = yf.Ticker(user_ticker)
            options = tk.options
            if not options: st.warning("No options chain found."); st.stop()
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

# ==================== OPTIONS ====================
with tab_options:
    st.subheader("🐳 Put/Call Volume Ratio")
    pcr_df = get_pcr_data()
    if not pcr_df.empty:
        st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True, use_container_width=True)
    else:
        st.info("Gathering options flow...")

# ==================== EARNINGS (MAG7 + TODAY) ====================
with tab_earnings:
    st.subheader("🎯 Earnings Intelligence")
    st.caption("Magnificent 7 (always tracked) + Major stocks reporting TODAY (auto-added)")

    ticker_dict = MAG7_TICKERS.copy()
    seen = set(MAG7_TICKERS.values())
    for item in get_todays_earnings():
        sym = item["Symbol"]
        if sym and sym not in seen:
            seen.add(sym)
            ticker_dict[item["Asset"]] = sym

    earn_df = get_earnings_data(ticker_dict)

    if not earn_df.empty:
        today_list = earn_df[earn_df["Today?"] == "📢 TODAY"]["Asset"].tolist()
        if today_list:
            st.success(f"📢 **Reporting TODAY:** {', '.join(today_list)}")

        earn_df['parsed'] = pd.to_datetime(earn_df['Next Date'], errors='coerce')
        earn_df = earn_df.sort_values('parsed').reset_index(drop=True)

        upcoming = earn_df[earn_df['parsed'].notna()]
        if not upcoming.empty:
            next_up = upcoming.iloc[0]
            days_left = (next_up['parsed'].date() - datetime.datetime.now(pytz.timezone('US/Eastern')).date()).days
            day_text = "TODAY" if days_left == 0 else "tomorrow" if days_left == 1 else f"in {days_left} days" if days_left > 0 else f"{abs(days_left)} days ago"
            st.info(f"🚀 **Next Catalyst:** {next_up['Asset']} on **{next_up['Next Date']}** ({day_text})")

        display_df = earn_df.drop(columns=["Today?", "parsed"])
        styled = display_df.style\
            .background_gradient(cmap='RdYlGn', subset=['Surprise (%)'])\
            .applymap(lambda x: 'color:#00ff00;font-weight:bold' if x == "✅ Beat" else
                              'color:#ff4b4b;font-weight:bold' if x == "❌ Miss" else '', subset=['Status'])\
            .applymap(lambda x: 'background-color:#ffff99;font-weight:bold' 
                      if pd.to_datetime(x, errors='coerce') == pd.Timestamp.today().normalize() else '', subset=['Next Date'])
        st.dataframe(styled, hide_index=True, use_container_width=True)
    else:
        st.warning("Earnings data temporarily unavailable.")

# ==================== NEW: ATH/ATL YESTERDAY EARNINGS PLAYS ====================
with tab_extremes:
    st.subheader("🔥 Yesterday's Earnings Near All-Time High / Low")
    st.caption("Reported earnings **1 day ago** • Within 5% of 52-week high/low • Strong fundamentals (ROE>15%, Debt/Eq<0.8, Profit Margin>15%)")

    df_plays = get_ath_atl_earnings_plays()

    if not df_plays.empty:
        df_plays = df_plays.sort_values("Dist %")
        styled = df_plays.style\
            .background_gradient(cmap='RdYlGn', subset=['ROE %', 'Profit Margin %'])\
            .background_gradient(cmap='RdYlGn_r', subset=['Debt/Eq'])\
            .format({"Price": "${:.2f}", "Dist %": "{:.2f}%"})
        st.dataframe(styled, hide_index=True, use_container_width=True)
        st.success(f"Found **{len(df_plays)}** high-conviction setups from yesterday's earnings!")
    else:
        st.info("No strong fundamental stocks near 52-week extremes reported earnings yesterday.")

# ==================== NEWS ====================
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
        st.sidebar.divider()
        st.sidebar.metric("Sentiment Pulse", total_score, delta="Positive" if total_score >= 0 else "Negative")
    else:
        st.error("News feed currently unavailable.")

st_autorefresh(interval=30000, key="global_refresh")
