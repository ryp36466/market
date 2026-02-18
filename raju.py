import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
from finvizfinance.news import News

# Page configuration
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

# ── TICKER CONFIGURATIONS ──
GLOBAL_TICKERS = { ... }      # (your dictionaries unchanged)
SECTOR_TICKERS = { ... }
ETF_TICKERS = { ... }
TWENTYFOUR_TICKERS = { ... }
MAG7_TICKERS = { ... }

OPTIONS_TICKERS = {
    **MAG7_TICKERS,
    "SPY (S&P 500 ETF)": "SPY",
    "QQQ (Nasdaq 100 ETF)": "QQQ",
    "VIX": "^VIX"
}

TIER_1_BANKS = ["Goldman Sachs", "Morgan Stanley", "JPMorgan Chase", "JP Morgan", 
                "Bank of America", "BofA", "Citigroup", "Barclays", "UBS", 
                "Wells Fargo", "Deutsche Bank", "Credit Suisse"]

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS, 
               **TWENTYFOUR_TICKERS, **MAG7_TICKERS}

# ── HELPER FUNCTIONS ──
def analyze_sentiment(text):
    if not text or not isinstance(text, str):
        return "⚖️ Neutral"
    bullish_words = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'growth', 'bull', 'high', 
                     'positive', 'win', 'beat', 'boost', 'strong', 'outperform', 'soar', 'raises']
    bearish_words = ['fall', 'down', 'drop', 'slump', 'plunge', 'bear', 'low', 'negative', 'loss', 
                     'crash', 'dip', 'cut', 'sink', 'weak', 'miss', 'lowers', 'decline']
    text = text.lower()
    bull_score = sum(1 for word in bullish_words if word in text)
    bear_score = sum(1 for word in bearish_words if word in text)
    if bull_score > bear_score:
        return "🐂 Bullish"
    if bear_score > bull_score:
        return "🐻 Bearish"
    return "⚖️ Neutral"

@st.cache_data(ttl=45)
def fetch_all_market_data():
    # (your original function - unchanged, it's solid)
    ...

@st.cache_data(ttl=300)
def get_ticker_news(ticker_symbol):
    try:
        return yf.Ticker(ticker_symbol).news[:3]
    except:
        return []

def color_pct(val):
    if pd.isna(val): return ''
    if val > 0: return 'color: #00ff00'
    if val < 0: return 'color: #ff4b4b'
    return ''

def color_rel(val):
    if pd.isna(val): return ''
    if val > 2.0: return 'background-color: #90ee90; font-weight: bold'
    if val > 1.5: return 'background-color: #98fb98'
    if val < 0.5: return 'background-color: #ffb6c1'
    return ''

@st.cache_data(ttl=600)
def fetch_finviz_news():
    try:
        fnews = News()
        news_dict = fnews.get_news()
        df = pd.DataFrame(news_dict.get('news', []))
        return df.head(10)
    except:
        return pd.DataFrame()

# ── NEW: EARNINGS & ANALYST FUNCTION (moved to top) ──
@st.cache_data(ttl=3600)
def fetch_earnings_and_ratings():
    earnings_list = []
    ratings_list = []
    
    for label, symbol in ALL_TICKERS.items():
        try:
            ticker = yf.Ticker(symbol)
            
            # Analyst recommendations (Tier 1 only)
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                latest = recs.tail(5).copy()
                latest['Symbol'] = symbol
                latest = latest[latest['Firm'].str.contains('|'.join(TIER_1_BANKS), case=False, na=False)]
                if not latest.empty:
                    ratings_list.append(latest)

            # Earnings
            cal = ticker.calendar
            if cal is not None and not cal.empty and 'Earnings Date' in cal.columns:
                e_date = pd.to_datetime(cal['Earnings Date'].iloc[0]).date()
                today = datetime.date.today()
                yesterday = today - datetime.timedelta(days=1)
                
                if e_date in (today, yesterday):
                    news = ticker.news[:3]
                    sent = "⚖️ Neutral"
                    if news:
                        sentiments = [analyze_sentiment(n.get('title', '')) for n in news]
                        sent = max(set(sentiments), key=sentiments.count)
                    
                    earnings_list.append({
                        "Asset": label,
                        "Symbol": symbol,
                        "Date": e_date,
                        "Sentiment": sent
                    })
        except:
            continue
            
    ratings_df = pd.concat(ratings_list) if ratings_list else pd.DataFrame()
    earnings_df = pd.DataFrame(earnings_list)
    return ratings_df, earnings_df

# ── OPTIONS PCR FUNCTION (moved out of tab for cleanliness) ──
@st.cache_data(ttl=300, show_spinner="Fetching options chains...")
def get_options_pcr():
    results = {}
    for label, symbol in OPTIONS_TICKERS.items():
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            if not expirations:
                results[label] = {"error": "No options data"}
                continue

            call_vol = 0.0
            put_vol = 0.0
            for exp in expirations[:5]:
                chain = ticker.option_chain(exp)
                call_vol += chain.calls["volume"].fillna(0).sum()
                put_vol += chain.puts["volume"].fillna(0).sum()

            pcr = put_vol / call_vol if call_vol > 0 else 0.0
            sentiment = (
                "🐂 Strongly Bullish" if pcr < 0.75 else
                "🐂 Bullish"          if pcr < 0.90 else
                "⚖️ Neutral"          if pcr < 1.10 else
                "🐻 Bearish"          if pcr < 1.30 else
                "🐻 Strongly Bearish"
            )

            results[label] = {
                "pcr": pcr,
                "call_vol": int(call_vol),
                "put_vol": int(put_vol),
                "sentiment": sentiment
            }
        except Exception as e:
            results[label] = {"error": str(e)}
    return results

# ── SIDEBAR NEWS ──
st.sidebar.divider()
st.sidebar.subheader("🗞️ Market Intelligence")
news_data = fetch_finviz_news()
if not news_data.empty:
    for _, row in news_data.iterrows():
        with st.sidebar.expander(f"{row['Source']} | {row['Date']}"):
            st.write(row['Title'])
            link = row.get('url') or row.get('URL')
            if link:
                st.markdown(f"[Read Article]({link})")
else:
    st.sidebar.info("News feed temporarily unavailable.")

# ── MAIN APP LOGIC ──
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

full_market = fetch_all_market_data()
full_market = full_market.dropna(subset=['Change %'])

# Create filtered DataFrames
global_df = full_market[full_market['Asset'].isin(GLOBAL_TICKERS.keys())].copy()
sector_df = full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())].copy()
etf_df = full_market[full_market['Asset'].isin(ETF_TICKERS.keys())].copy()
twentyfour_df = full_market[full_market['Asset'].isin(TWENTYFOUR_TICKERS.keys())].copy()
mag7_df = full_market[full_market['Asset'].isin(MAG7_TICKERS.keys())].copy()

for df in [global_df, sector_df, etf_df, twentyfour_df, mag7_df]:
    df.sort_values('Change %', ascending=False, inplace=True)

# Relative Strength
benchmark = "SPY (S&P 500 ETF)"
benchmark_change = full_market.loc[full_market['Asset'] == benchmark, 'Change %'].iloc[0] \
    if benchmark in full_market['Asset'].values else 0.0

for df in [sector_df, etf_df, twentyfour_df, mag7_df]:
    df['RS'] = df['Change %'] - benchmark_change

top_gainers = full_market.sort_values('Change %', ascending=False).head(6)
top_losers = full_market.sort_values('Change %', ascending=True).head(6)

# Mover news & sentiment
mover_sentiments = {}
mover_news_dict = {}
top_movers = pd.concat([top_gainers, top_losers]).drop_duplicates(subset='Asset')

for _, row in top_movers.iterrows():
    news_items = get_ticker_news(row['Symbol'])
    mover_news_dict[row['Asset']] = news_items

    if not news_items:
        overall = "❓ No News"
    else:
        sentiments = [analyze_sentiment(item.get('title', '')) for item in news_items]
        bull_count = sum(1 for s in sentiments if "🐂" in s)
        bear_count = sum(1 for s in sentiments if "🐻" in s)
        overall = "🐂 Bullish" if bull_count > bear_count else "🐻 Bearish" if bear_count > bull_count else "⚖️ Neutral"
    mover_sentiments[row['Asset']] = overall

# ── SIDEBAR CONTROLS ──
st.sidebar.title("🏛️ Market Settings")
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="datarefresh")

# Mover News in Sidebar (unchanged)
st.sidebar.divider()
st.sidebar.subheader("📰 Mover News & Sentiment")
# ... (your sidebar expander code for leaders/laggards - unchanged)

# ── MAIN PAGE ──
st.title("🏛️ Pro Market Terminal")
st.caption(f"Status: Live | EST Time: {time_now} | Auto-Refresh: {refresh}s")

# Market Scanner (unchanged)
# ...

st.divider()

# ── TABS (FIXED: 5 tabs) ──
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🌎 Global Indices",
    "📈 Sectors, ETFs, 24h & Mag7",
    "📊 Relative Strength & Charts",
    "⚖️ Options Sentiment (Mag7 + SPY/QQQ/VIX)",
    "🎯 Analyst & Earnings"
])

with tab1:
    # (your original code)
    ...

with tab2:
    # (your original 4-column code)
    ...

with tab3:
    # (your original code)
    ...

with tab4:
    st.subheader("Options Sentiment (Put/Call Volume Ratio)")
    st.caption(
        "Aggregated from nearest 5 expirations • "
        "PCR = Put Volume / Call Volume • >1.0 → bearish • <0.8 → bullish • "
        "Today's traded volume only"
    )

    data = get_options_pcr()

    cols = st.columns(5)
    for i, (label, info) in enumerate(data.items()):
        col = cols[i % 5]
        if "error" in info:
            col.error(f"{label}\n{info['error']}")
            continue
        col.metric(
            label=label,
            value=f"{info['pcr']:.2f}",
            delta=info['sentiment'],
            help=f"Call: {info['call_vol']:,} • Put: {info['put_vol']:,}"
        )

    # Aggregate PCR (moved inside tab4)
    total_call = sum(d.get("call_vol", 0) for d in data.values() if "error" not in d)
    total_put = sum(d.get("put_vol", 0) for d in data.values() if "error" not in d)
    agg_pcr = total_put / total_call if total_call > 0 else 0.0

    col1, col2 = st.columns([1, 3])
    col1.metric("Aggregate PCR (All 10)", f"{agg_pcr:.2f}")
    if agg_pcr < 0.80:
        col2.success("**Overall bullish options flow**")
    elif agg_pcr > 1.10:
        col2.error("**Overall bearish options flow**")
    else:
        col2.info("**Balanced options sentiment**")

    st.caption("Data via yfinance • Refreshes every 5 min • VIX PCR = expected volatility tilt")

with tab5:
    st.subheader("🎯 Market Moving Events")
    ratings_df, earnings_df = fetch_earnings_and_ratings()
    
    col_e, col_r = st.columns(2)
    
    with col_e:
        st.write("**Recent/Upcoming Earnings**")
        if not earnings_df.empty:
            st.dataframe(earnings_df, use_container_width=True, hide_index=True)
        else:
            st.info("No earnings found for tracked tickers in the 48h window.")
            
    with col_r:
        st.write("**Tier 1 Analyst Moves**")
        if not ratings_df.empty:
            display_ratings = ratings_df[['Symbol', 'Firm', 'To Grade', 'From Grade']].tail(10)
            st.dataframe(display_ratings, use_container_width=True, hide_index=True)
        else:
            st.info("No Tier 1 analyst changes detected today.")

# All fixed ✅
