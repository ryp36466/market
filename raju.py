import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
from finvizfinance.news import News
import plotly.express as px

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Pro Market Terminal", page_icon="🏛️", layout="wide")

def check_password():
    """Returns True if the user had the correct password."""
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

# --- TICKER CONFIGURATIONS ---
GLOBAL_TICKERS = {
    "S&P 500 Futures (ES)": "ES=F", "Nasdaq 100 Futures (NQ)": "NQ=F",
    "Dow Jones Futures (YM)": "YM=F", "SPY (S&P 500 ETF)": "SPY",
    "QQQ (Nasdaq 100 ETF)": "QQQ", "VIX": "^VIX",
    "10Y Yield (^TNX)": "^TNX", "DXY (US Dollar)": "DX-Y.NYB"
}

MAG7_TICKERS = {
    "Apple (AAPL)": "AAPL", "Microsoft (MSFT)": "MSFT", "Nvidia (NVDA)": "NVDA",
    "Amazon (AMZN)": "AMZN", "Alphabet (GOOGL)": "GOOGL", "Meta (META)": "META",
    "Tesla (TSLA)": "TSLA"
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

OPTIONS_TICKERS = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX"}

TIER_1_BANKS = [
    "Goldman Sachs", "Morgan Stanley", "JPMorgan Chase", "JP Morgan", 
    "Bank of America", "BofA", "Citigroup", "Barclays", "UBS", 
    "Wells Fargo", "Deutsche Bank", "Credit Suisse"
]

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS, **TWENTYFOUR_TICKERS, **MAG7_TICKERS}

# --- DATA FETCHING & ANALYSIS FUNCTIONS ---

def analyze_sentiment(text):
    if not text or not isinstance(text, str): return "⚖️ Neutral"
    bullish_words = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'growth', 'bull', 'high', 'positive', 'win', 'beat', 'boost', 'strong', 'outperform', 'soar', 'raises']
    bearish_words = ['fall', 'down', 'drop', 'slump', 'plunge', 'bear', 'low', 'negative', 'loss', 'crash', 'dip', 'cut', 'sink', 'weak', 'miss', 'lowers', 'decline']
    text = text.lower()
    bull_score = sum(1 for word in bullish_words if word in text)
    bear_score = sum(1 for word in bearish_words if word in text)
    return "🐂 Bullish" if bull_score > bear_score else "🐻 Bearish" if bear_score > bull_score else "⚖️ Neutral"

@st.cache_data(ttl=3600)
def fetch_earnings_and_ratings():
    earnings_list, ratings_list = [], []
    for label, symbol in ALL_TICKERS.items():
        try:
            ticker = yf.Ticker(symbol)
            # Analyst Ratings
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                latest = recs.tail(5).copy()
                latest['Symbol'] = symbol
                latest = latest[latest['Firm'].str.contains('|'.join(TIER_1_BANKS), case=False, na=False)]
                ratings_list.append(latest)
            # Earnings
            cal = ticker.calendar
            if cal is not None and 'Earnings Date' in cal:
                e_date = cal['Earnings Date'][0].date()
                today = datetime.date.today()
                if e_date in [today, today - datetime.timedelta(days=1)]:
                    news = ticker.news[:3]
                    sent = analyze_sentiment(news[0].get('title', '')) if news else "⚖️ Neutral"
                    earnings_list.append({"Asset": label, "Symbol": symbol, "Date": e_date, "Sentiment": sent})
        except: continue
    return (pd.concat(ratings_list) if ratings_list else pd.DataFrame()), pd.DataFrame(earnings_list)

@st.cache_data(ttl=45)
def fetch_all_market_data():
    tickers_list = list(ALL_TICKERS.values())
    ticker_to_label = {v: k for k, v in ALL_TICKERS.items()}
    daily_data = yf.download(tickers=tickers_list, period="60d", interval="1d", progress=False)
    intra_data = yf.download(tickers=tickers_list, period="1d", interval="5m", prepost=True, progress=False)
    
    rows = []
    for ticker in tickers_list:
        label = ticker_to_label.get(ticker, ticker)
        try:
            prev_close = daily_data['Close'][ticker].dropna().iloc[-2] if len(daily_data['Close'][ticker].dropna()) >= 2 else np.nan
            current_price = intra_data['Close'][ticker].dropna().iloc[-1] if not intra_data['Close'][ticker].dropna().empty else daily_data['Close'][ticker].iloc[-1]
            pct_change = ((current_price - prev_close) / prev_close * 100) if prev_close > 0 else np.nan
            day_vol = intra_data['Volume'][ticker].sum()
            avg_vol = daily_data['Volume'][ticker].dropna().iloc[-21:-1].mean()
            rows.append({"Asset": label, "Symbol": ticker, "Price": current_price, "Change %": pct_change, "Rel Vol": day_vol/avg_vol if avg_vol > 0 else np.nan})
        except: rows.append({"Asset": label, "Symbol": ticker, "Price": np.nan, "Change %": np.nan, "Rel Vol": np.nan})
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def get_options_pcr():
    results = {}
    for label, symbol in OPTIONS_TICKERS.items():
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            if not expirations: continue
            c_vol, p_vol = 0, 0
            for exp in expirations[:3]:
                chain = ticker.option_chain(exp)
                c_vol += chain.calls['volume'].sum()
                p_vol += chain.puts['volume'].sum()
            pcr = p_vol / c_vol if c_vol > 0 else 0
            results[label] = {"pcr": pcr, "cv": c_vol, "pv": p_vol, "sent": "🐂 Bullish" if pcr < 0.9 else "🐻 Bearish" if pcr > 1.1 else "⚖️ Neutral"}
        except: continue
    return results

# --- UI STYLING ---
def color_pct(val):
    if pd.isna(val): return ''
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

# --- MAIN APP ---
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.sidebar.title("🏛️ Market Settings")
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="datarefresh")

full_market = fetch_all_market_data().dropna(subset=['Change %'])
top_gainers = full_market.sort_values('Change %', ascending=False).head(6)
top_losers = full_market.sort_values('Change %', ascending=True).head(6)

st.title("🏛️ Pro Market Terminal")
st.caption(f"Status: Live | EST: {time_now} | Auto-Refresh: {refresh}s")

# --- TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🌎 Global Indices", "📈 Sectors & Mag7", "📊 Charts", "⚖️ Options Flow", "🎯 Analyst & Earnings"
])

with tab1:
    st.subheader("Major Markets")
    global_df = full_market[full_market['Asset'].isin(GLOBAL_TICKERS.keys())]
    st.dataframe(global_df.style.map(color_pct, subset=['Change %']), use_container_width=True, hide_index=True)

with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Sectors")
        sec_df = full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())]
        st.dataframe(sec_df.style.map(color_pct, subset=['Change %']), use_container_width=True, hide_index=True)
    with col2:
        st.subheader("Magnificent 7")
        mag_df = full_market[full_market['Asset'].isin(MAG7_TICKERS.keys())]
        st.dataframe(mag_df.style.map(color_pct, subset=['Change %']), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Intraday Performance")
    selected = st.selectbox("Select Ticker", list(ALL_TICKERS.keys()))
    hist = yf.Ticker(ALL_TICKERS[selected]).history(period='1d', interval='5m')
    if not hist.empty:
        st.line_chart(hist['Close'])

with tab4:
    st.subheader("Options Sentiment (PCR)")
    pcr_data = get_options_pcr()
    cols = st.columns(4)
    for i, (l, info) in enumerate(pcr_data.items()):
        cols[i % 4].metric(l, f"{info['pcr']:.2f}", delta=info['sent'])
    
    total_c = sum(v['cv'] for v in pcr_data.values())
    total_p = sum(v['pv'] for v in pcr_data.values())
    agg_pcr = total_p / total_c if total_c > 0 else 0
    st.divider()
    st.metric("Aggregate Market PCR", f"{agg_pcr:.2f}", help="Total Put Volume / Total Call Volume across tracked tickers")

with tab5:
    st.subheader("🎯 Market Moving Events")
    ratings_df, earnings_df = fetch_earnings_and_ratings()
    c_e, c_r = st.columns(2)
    with c_e:
        st.write("**Earnings (Today/Yesterday)**")
        if not earnings_df.empty:
            st.dataframe(earnings_df, use_container_width=True, hide_index=True)
        else:
            st.info("No recent earnings for tracked tickers.")
    with c_r:
        st.write("**Tier 1 Analyst Moves**")
        if not ratings_df.empty:
            st.dataframe(ratings_df[['Symbol', 'Firm', 'To Grade', 'From Grade']].tail(10), use_container_width=True, hide_index=True)
        else:
            st.info("No recent Tier 1 analyst changes.")
