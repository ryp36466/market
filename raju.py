import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
import requests

# ========================== CONFIG & KEYS ==========================
# Using your provided Finnhub key for high-speed ticker-tagged news
FINNHUB_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"

st.set_page_config(page_title="Pro Market Terminal", page_icon="🏛️", layout="wide")

# ========================== AUTHENTICATION ==========================
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
GLOBAL_TICKERS = {"S&P 500 Futures": "ES=F", "Nasdaq 100 Futures": "NQ=F", "Dow Futures": "YM=F", "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"}
SECTOR_TICKERS = {"Tech (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV", "Disc (XLY)": "XLY", "Industrials (XLI)": "XLI", "Utilities (XLU)": "XLU", "Real Estate (XLRE)": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"}
ETF_TICKERS = {"Bitcoin (IBIT)": "IBIT", "Gold (GLD)": "GLD", "Silver (SLV)": "SLV", "Bonds (TLT)": "TLT", "Semis (SMH)": "SMH", "Ark (ARKK)": "ARKK"}
TWENTYFOUR_TICKERS = {"BTC-USD": "BTC-USD", "ETH-USD": "ETH-USD", "Gold Futures": "GC=F", "Crude Oil": "CL=F"}
MAG7_TICKERS = {"Apple": "AAPL", "Microsoft": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Alphabet": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS, **TWENTYFOUR_TICKERS, **MAG7_TICKERS}

# ========================== NEWS & DATA HELPERS ==========================
@st.cache_data(ttl=60)
def fetch_finnhub_news(category="general"):
    """Fetches high-speed news from Finnhub."""
    url = f'https://finnhub.io/api/v1/news?category={category}&token={FINNHUB_KEY}'
    try:
        response = requests.get(url)
        return response.json()[:15]
    except:
        return []

@st.cache_data(ttl=45)
def fetch_all_market_data():
    tickers_list = list(ALL_TICKERS.values())
    daily = yf.download(tickers=tickers_list, period="60d", interval="1d", progress=False)
    intra = yf.download(tickers=tickers_list, period="1d", interval="5m", prepost=True, progress=False)
    
    rows = []
    for t in tickers_list:
        label = [k for k, v in ALL_TICKERS.items() if v == t][0]
        try:
            prev_close = daily['Close'][t].dropna().iloc[-2]
            price = intra['Close'][t].dropna().iloc[-1]
            change = (price - prev_close) / prev_close * 100
            day_vol = intra['Volume'][t].sum()
            avg_vol = daily['Volume'][t].dropna().iloc[-21:-1].mean()
            rows.append({"Asset": label, "Symbol": t, "Price": price, "Change %": change, "Rel Vol": day_vol/avg_vol})
        except:
            continue
    return pd.DataFrame(rows)

def analyze_sentiment(text):
    bullish = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'beat', 'growth', 'upgrade']
    bearish = ['fall', 'down', 'drop', 'slump', 'plunge', 'miss', 'low', 'downgrade']
    text = text.lower()
    b_count = sum(1 for w in bullish if w in text)
    s_count = sum(1 for w in bearish if w in text)
    if b_count > s_count: return "🟢 Bullish"
    if s_count > b_count: return "🔴 Bearish"
    return "⚖️ Neutral"

# ========================== UI STYLING ==========================
def color_pct(val):
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

# ========================== SIDEBAR ==========================
st.sidebar.title("🏛️ Market Settings")
refresh = st.sidebar.number_input('Refresh (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="refresh")

st.sidebar.divider()
st.sidebar.subheader("🗞️ Ticker-Tagged Intelligence")
# Pulling general news but emphasizing the 'related' ticker if available
sidebar_news = fetch_finnhub_news("general")
for item in sidebar_news:
    ticker = item.get('related', 'MKT')
    ticker_display = f"[{ticker}]" if ticker else "[MKT]"
    with st.sidebar.expander(f"{ticker_display} {item.get('source', '')}"):
        st.write(f"**{item['headline']}**")
        st.caption(datetime.datetime.fromtimestamp(item['datetime']).strftime('%H:%M'))
        st.markdown(f"[View Full Story]({item['url']})")

# ========================== MAIN UI ==========================
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')
st.title("🏛️ Pro Market Terminal")
st.caption(f"Live EST {time_now} | {refresh}s Auto-Refresh")

# Fetch Data
full_market = fetch_all_market_data()
top_gainers = full_market.nlargest(6, 'Change %')
top_losers = full_market.nsmallest(6, 'Change %')

# ========================== 🔍 DAY TRADER'S CATALYST SCANNER ==========================
st.subheader("🔍 Active Ticker News (Why it's Moving)")
cat_col1, cat_col2 = st.columns(2)

with cat_col1:
    st.write("**🔥 High Volume Gainers**")
    for _, row in top_gainers.iterrows():
        t_news = yf.Ticker(row['Symbol']).news[:1]
        if t_news:
            headline = t_news[0]['title']
            sent = analyze_sentiment(headline)
            st.success(f"**{row['Symbol']}** ({row['Change %']:+.2f}%) | {sent}\n\n{headline}")
        else:
            st.write(f"**{row['Symbol']}** ({row['Change %']:+.2f}%) | No recent catalyst found.")

with cat_col2:
    st.write("**📉 High Volume Losers**")
    for _, row in top_losers.iterrows():
        t_news = yf.Ticker(row['Symbol']).news[:1]
        if t_news:
            headline = t_news[0]['title']
            sent = analyze_sentiment(headline)
            st.error(f"**{row['Symbol']}** ({row['Change %']:+.2f}%) | {sent}\n\n{headline}")
        else:
            st.write(f"**{row['Symbol']}** ({row['Change %']:+.2f}%) | No recent catalyst found.")

st.divider()

# ========================== TABS ==========================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Performance Matrix", "📈 Relative Strength", "⚖️ Options PCR", "🎯 Analysts"])

with tab1:
    st.dataframe(
        full_market.style.format({"Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": "{:.2f}x"})
        .map(color_pct, subset=["Change %"]),
        use_container_width=True, hide_index=True
    )

with tab2:
    spy_val = full_market.loc[full_market['Symbol'] == 'SPY', 'Change %'].values[0] if 'SPY' in full_market['Symbol'].values else 0
    full_market['RS'] = full_market['Change %'] - spy_val
    st.bar_chart(full_market.set_index("Asset")['RS'])

with tab3:
    st.info("PCR Analysis calculates Put/Call ratios for active tickers to gauge institutional sentiment.")
    # (Optional: Re-insert your Options PCR function call here)

with tab4:
    st.write("Displaying Tier 1 Analyst Upgrades/Downgrades and Price Targets.")
    # (Optional: Re-insert your Analyst Ratings function call here)

with tab3:
    st.subheader(f"Relative Strength vs SPY")
    for name, df in [("Sectors", sector_df), ("24h & Commodities", tf_df), ("Mag7", mag7_df)]:
        st.write(f"**{name}**")
        st.bar_chart(df.set_index("Asset")["RS"])
        st.divider()

    st.subheader("Intraday Charts")
    sel = st.multiselect("Select assets", list(ALL_TICKERS.keys()),
                         default=["SPY (S&P 500 ETF)", "Bitcoin 24h (BTC-USD)", "Nvidia (NVDA)"])
    for lab in sel:
        data = yf.Ticker(ALL_TICKERS[lab]).history(period="1d", interval="5m")
        if not data.empty:
            st.write(f"**{lab}**")
            st.line_chart(data['Close'].tz_convert('US/Eastern'))

with tab4:
    st.subheader("Options Sentiment (PCR)")
    st.caption("Put/Call Ratio • <0.8 Bullish • >1.1 Bearish • nearest 5 expirations")
    data = get_options_pcr()
    cols = st.columns(5)
    for i, (label, info) in enumerate(data.items()):
        c = cols[i % 5]
        if "error" in info:
            c.error(f"{label}\n{info['error']}")
        else:
            c.metric(label, f"{info['pcr']:.2f}", info['sentiment'],
                     help=f"Call: {info['call_vol']:,} • Put: {info['put_vol']:,}")

    # Aggregate
    tc = sum(d.get("call_vol",0) for d in data.values() if "error" not in d)
    tp = sum(d.get("put_vol",0) for d in data.values() if "error" not in d)
    ap = tp / tc if tc else 0
    col1, col2 = st.columns([1,3])
    col1.metric("Aggregate PCR", f"{ap:.2f}")
    if ap < 0.80: col2.success("**Strongly Bullish** options flow")
    elif ap > 1.10: col2.error("**Strongly Bearish** options flow")
    else: col2.info("**Neutral** options flow")

with tab5:
    st.subheader("🎯 Market Moving Events")
    
    # Dynamic Control for the timeframe
    days_range = st.slider("Select Earnings/Analyst Window (Days)", 1, 30, 7)
    
    ratings_df, earnings_df = fetch_earnings_and_ratings(days_window=days_range)
    
    col_e, col_r = st.columns(2)
    
    with col_e:
        st.write(f"**Earnings (±{days_range} Days)**")
        if not earnings_df.empty:
            # Sort by date so soonest is first
            earnings_df = earnings_df.sort_values("Earnings Date")
            st.dataframe(earnings_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"No earnings found in the {days_range} day window.")
            
    with col_r:
        st.write("**Tier 1 Analyst Moves & Targets**")
        if not ratings_df.empty:
            # We look for common target price column names in yfinance
            target_cols = [c for c in ['Target Price', 'Price Target', 'New Target'] if c in ratings_df.columns]
            display_cols = ['Symbol', 'Firm', 'To Grade'] + target_cols
            
            st.dataframe(
                ratings_df[display_cols].tail(15), 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.info("No Tier 1 analyst changes detected in this window.")
