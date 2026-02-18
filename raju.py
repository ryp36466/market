import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
from finvizfinance.news import News

# ========================== PAGE CONFIG ==========================
st.set_page_config(page_title="Pro Market Terminal", page_icon="🏛️", layout="wide")

def check_password():
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
    else:
        return True

if not check_password():
    st.stop()

# ========================== TICKERS ==========================
GLOBAL_TICKERS = {
    "S&P 500 Futures (ES)": "ES=F", "Nasdaq 100 Futures (NQ)": "NQ=F",
    "Dow Jones Futures (YM)": "YM=F", "SPY (S&P 500 ETF)": "SPY",
    "QQQ (Nasdaq 100 ETF)": "QQQ", "VIX": "^VIX",
    "10Y Yield (^TNX)": "^TNX", "DXY (US Dollar)": "DX-Y.NYB"
}
SECTOR_TICKERS = {
    "Technology (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV", "Consumer Disc (XLY)": "XLY", "Industrials (XLI)": "XLI",
    "Utilities (XLU)": "XLU", "Real Estate (XLRE)": "XLRE", "Consumer Staples (XLP)": "XLP",
    "Materials (XLB)": "XLB"
}
ETF_TICKERS = {
    "Bitcoin ETF (IBIT)": "IBIT", "Gold ETF (GLD)": "GLD", "Silver (SLV)": "SLV",
    "Bonds 20Y+ (TLT)": "TLT", "Semis (SMH)": "SMH", "Ark Innovation (ARKK)": "ARKK"
}
TWENTYFOUR_TICKERS = {
    "Bitcoin 24h (BTC-USD)": "BTC-USD", "Ethereum (ETH-USD)": "ETH-USD",
    "Gold Futures (GC)": "GC=F", "Crude Oil (CL)": "CL=F"
}
MAG7_TICKERS = {
    "Apple (AAPL)": "AAPL", "Microsoft (MSFT)": "MSFT", "Nvidia (NVDA)": "NVDA",
    "Amazon (AMZN)": "AMZN", "Alphabet (GOOGL)": "GOOGL", "Meta (META)": "META", "Tesla (TSLA)": "TSLA"
}
OPTIONS_TICKERS = {**MAG7_TICKERS, "SPY (S&P 500 ETF)": "SPY", "QQQ (Nasdaq 100 ETF)": "QQQ", "VIX": "^VIX"}
TIER_1_BANKS = ["Goldman Sachs", "Morgan Stanley", "JPMorgan Chase", "JP Morgan", "Bank of America", "BofA", "Citigroup", "Barclays", "UBS", "Wells Fargo", "Deutsche Bank"]
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS, **TWENTYFOUR_TICKERS, **MAG7_TICKERS}

# ========================== HELPERS ==========================
def analyze_sentiment(text):
    if not text or not isinstance(text, str): return "⚖️ Neutral"
    bullish = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'growth', 'bull', 'high', 'positive', 'win', 'beat', 'boost', 'strong', 'outperform', 'soar', 'raises', 'upgrade', 'profit', 'dividend']
    bearish = ['fall', 'down', 'drop', 'slump', 'plunge', 'bear', 'low', 'negative', 'loss', 'crash', 'dip', 'cut', 'sink', 'weak', 'miss', 'lowers', 'decline', 'downgrade', 'debt']
    text = text.lower()
    b_score = sum(1 for w in bullish if w in text)
    r_score = sum(1 for w in bearish if w in text)
    if b_score > r_score: return "🐂 Bullish"
    if r_score > b_score: return "🐻 Bearish"
    return "⚖️ Neutral"

@st.cache_data(ttl=45)
def fetch_all_market_data():
    tickers_list = list(ALL_TICKERS.values())
    ticker_to_label = {v: k for k, v in ALL_TICKERS.items()}
    daily = yf.download(tickers=tickers_list, period="60d", interval="1d", progress=False)
    
    try:
        spy_vol_today = daily['Volume']['SPY'].iloc[-1]
        spy_vol_avg = daily['Volume']['SPY'].iloc[-22:-1].mean()
        spy_rvol = spy_vol_today / spy_vol_avg if spy_vol_avg > 0 else 1.0
    except: spy_rvol = 1.0

    rows = []
    for t in tickers_list:
        label = ticker_to_label.get(t, t)
        try:
            closes = daily['Close'][t].dropna()
            price = closes.iloc[-1]
            prev_close = closes.iloc[-2]
            change = (price - prev_close) / prev_close * 100
            
            vols = daily['Volume'][t].dropna()
            rel_vol = vols.iloc[-1] / vols.iloc[-22:-1].mean() if len(vols) > 22 else 1.0
            mkt_rel_vol = rel_vol / spy_rvol if spy_rvol > 0 else 1.0

            rows.append({"Asset": label, "Symbol": t, "Price": price, "Change %": change, "Rel Vol": rel_vol, "Mkt Rel Vol": mkt_rel_vol})
        except:
            rows.append({"Asset": label, "Symbol": t, "Price": np.nan, "Change %": np.nan, "Rel Vol": np.nan, "Mkt Rel Vol": np.nan})
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def get_ticker_news(symbol):
    try:
        data = yf.Ticker(symbol).news
        # Handle different response formats from yfinance
        if isinstance(data, dict) and 'news' in data:
            return data['news'][:3]
        return data[:3] if isinstance(data, list) else []
    except:
        return []

@st.cache_data(ttl=3600)
def fetch_earnings_and_ratings(days_window=7):
    ratings_list, earnings_list = [], []
    today = datetime.date.today()
    for label, symbol in ALL_TICKERS.items():
        try:
            tk = yf.Ticker(symbol)
            recs = tk.recommendations
            if recs is not None and not recs.empty:
                latest = recs.tail(5).copy()
                latest['Symbol'] = symbol
                ratings_list.append(latest[latest['Firm'].str.contains('|'.join(TIER_1_BANKS), case=False, na=False)])
            
            cal = tk.calendar
            if cal is not None and 'Earnings Date' in cal:
                for e_dt in cal['Earnings Date']:
                    e_date = e_dt.date()
                    if abs((e_date - today).days) <= days_window:
                        earnings_list.append({"Asset": label, "Symbol": symbol, "Date": e_date, "Status": "🚀 Upcoming" if e_date >= today else "✅ Reported"})
        except: continue
    return pd.concat(ratings_list) if ratings_list else pd.DataFrame(), pd.DataFrame(earnings_list)

@st.cache_data(ttl=300)
def get_options_pcr():
    res = {}
    for label, sym in OPTIONS_TICKERS.items():
        try:
            tk = yf.Ticker(sym)
            exps = tk.options[:3]
            cv = pv = 0.0
            for exp in exps:
                ch = tk.option_chain(exp)
                cv += ch.calls['volume'].sum()
                pv += ch.puts['volume'].sum()
            pcr = pv / cv if cv > 0 else 0.0
            res[label] = {"pcr": pcr, "call_vol": int(cv), "put_vol": int(pv)}
        except: res[label] = {"error": "N/A"}
    return res

# ========================== STYLING ==========================
def color_pct(val):
    if pd.isna(val): return ''
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

def color_rel(val):
    if pd.isna(val) or val < 1.5: return ''
    return 'background-color: #44475a; color: #8be9fd; font-weight: bold'

# ========================== DATA PROCESSING ==========================
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="refresh")

full_market = fetch_all_market_data().dropna(subset=['Change %'])
spy_change = full_market.loc[full_market['Symbol'] == 'SPY', 'Change %'].values[0] if not full_market.empty else 0
full_market['RS'] = full_market['Change %'] - spy_change

top_gainers = full_market.nlargest(6, 'Change %')
top_losers  = full_market.nsmallest(6, 'Change %')

# ========================== MAIN UI ==========================
st.title("🏛️ Pro Market Terminal")
est_time = datetime.datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')
st.caption(f"Live EST {est_time} • Benchmarking vs SPY")

# Scanner Section
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    st.markdown("**Top Leaders 🚀**")
    for _, r in top_gainers.iterrows():
        news = get_ticker_news(r['Symbol'])
        # Safety check for news and title
        sent = analyze_sentiment(news[0].get('title', '')) if news and len(news) > 0 else "⚖️ Neutral"
        st.write(f"🟢 {r['Asset']}: `{r['Change %']:+.2f}%` {sent} {'🔥' if r['Mkt Rel Vol'] > 1.2 else ''}")
with c2:
    st.markdown("**Top Laggards 📉**")
    for _, r in top_losers.iterrows():
        news = get_ticker_news(r['Symbol'])
        # Safety check for news and title
        sent = analyze_sentiment(news[0].get('title', '')) if news and len(news) > 0 else "⚖️ Neutral"
        st.write(f"🔴 {r['Asset']}: `{r['Change %']:+.2f}%` {sent} {'🔥' if r['Mkt Rel Vol'] > 1.2 else ''}")
with c3:
    up = len(full_market[full_market['Change %'] > 0])
    st.metric("Breadth", f"{up}↑ {len(full_market)-up}↓", delta=f"{up - (len(full_market)-up)}")

st.divider()

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🌎 Indices", "📈 Sectors & Mag7", "📊 RS Analysis", "⚖️ Options", "🎯 Analyst"])

with tab1:
    df_global = full_market[full_market['Asset'].isin(GLOBAL_TICKERS.keys())]
    st.dataframe(df_global.style.format({"Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": "{:.2f}x", "Mkt Rel Vol": "{:.2f}x"})
                 .map(color_pct, subset=["Change %"]).map(color_rel, subset=["Mkt Rel Vol"]), use_container_width=True, hide_index=True)

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Sectors")
        df_sec = full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())]
        st.dataframe(df_sec[['Asset', 'Change %', 'Mkt Rel Vol', 'RS']].style.format("{:.2f}").map(color_pct, subset=['Change %', 'RS']), use_container_width=True, hide_index=True)
    with c2:
        st.subheader("Magnificent 7")
        df_m7 = full_market[full_market['Asset'].isin(MAG7_TICKERS.keys())]
        st.dataframe(df_m7[['Asset', 'Change %', 'Mkt Rel Vol', 'RS']].style.format("{:.2f}").map(color_pct, subset=['Change %', 'RS']), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Relative Strength (vs SPY)")
    st.bar_chart(full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())].set_index('Asset')['RS'])

with tab4:
    st.subheader("Options PCR (Institutional Sentiment)")
    pcr_data = get_options_pcr()
    cols = st.columns(4)
    for i, (lab, info) in enumerate(pcr_data.items()):
        if "pcr" in info:
            cols[i%4].metric(lab, f"{info['pcr']:.2f}", "Bullish" if info['pcr'] < 0.85 else "Bearish" if info['pcr'] > 1.1 else "Neutral")

with tab5:
    days = st.slider("Window", 1, 30, 7)
    r_df, e_df = fetch_earnings_and_ratings(days)
    ca, cb = st.columns(2)
    with ca:
        st.write("**Earnings**")
        st.dataframe(e_df, use_container_width=True, hide_index=True) if not e_df.empty else st.info("Clear calendar")
    with cb:
        st.write("**Analyst Targets**")
        if not r_df.empty:
            st.dataframe(r_df[['Symbol', 'Firm', 'To Grade']].tail(10), use_container_width=True, hide_index=True)
