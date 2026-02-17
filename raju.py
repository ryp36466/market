import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
from finvizfinance.news import News
import plotly.express as px

# Page configuration
st.set_page_config(page_title="Pro Market Terminal", page_icon="🏛️", layout="wide")

def check_password():
    """Returns True if the user had the correct password."""
    def password_entered():
        # Change 'your_secret_password' to whatever you want
        if st.session_state["password"] == "your_secret_password":
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # clean up
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

# If password is not correct, stop the app right here
if not check_password():
    st.stop()
    
# ── TICKER CONFIGURATIONS ──
GLOBAL_TICKERS = {
    "S&P 500 Futures (ES)": "ES=F",
    "Nasdaq 100 Futures (NQ)": "NQ=F",
    "Dow Jones Futures (YM)": "YM=F",
    "SPY (S&P 500 ETF)": "SPY",
    "QQQ (Nasdaq 100 ETF)": "QQQ",
    "VIX": "^VIX",
    "10Y Yield (^TNX)": "^TNX",
    "DXY (US Dollar)": "DX-Y.NYB"
}

SECTOR_TICKERS = {
    "Technology (XLK)": "XLK",
    "Financials (XLF)": "XLF",
    "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV",
    "Consumer Disc (XLY)": "XLY",
    "Industrials (XLI)": "XLI",
    "Utilities (XLU)": "XLU",
    "Real Estate (XLRE)": "XLRE",
    "Consumer Staples (XLP)": "XLP",
    "Materials (XLB)": "XLB"
}

ETF_TICKERS = {
    "Bitcoin ETF (IBIT)": "IBIT",
    "Gold ETF (GLD)": "GLD",
    "Silver (SLV)": "SLV",
    "Bonds 20Y+ (TLT)": "TLT",
    "Semis (SMH)": "SMH",
    "Ark Innovation (ARKK)": "ARKK"
}

TWENTYFOUR_TICKERS = {
    "Bitcoin 24h (BTC-USD)": "BTC-USD",
    "Ethereum (ETH-USD)": "ETH-USD",
    "Gold Futures (GC)": "GC=F",
    "Crude Oil (CL)": "CL=F"
}

MAG7_TICKERS = {
    "Apple (AAPL)": "AAPL",
    "Microsoft (MSFT)": "MSFT",
    "Nvidia (NVDA)": "NVDA",
    "Amazon (AMZN)": "AMZN",
    "Alphabet (GOOGL)": "GOOGL",
    "Meta (META)": "META",
    "Tesla (TSLA)": "TSLA"
}

# ── NEW: OPTIONS SENTIMENT TICKERS (Mag7 + SPY, QQQ, VIX) ──
OPTIONS_TICKERS = {
    **MAG7_TICKERS,
    "SPY (S&P 500 ETF)": "SPY",
    "QQQ (Nasdaq 100 ETF)": "QQQ",
    "VIX": "^VIX"
}

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS, **TWENTYFOUR_TICKERS, **MAG7_TICKERS}

# ── SENTIMENT ANALYSIS ──
def analyze_sentiment(text):
    if not text or not isinstance(text, str):
        return "⚖️ Neutral"
    bullish_words = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'growth', 'bull', 'high', 'positive', 'win', 'beat', 'boost', 'strong', 'outperform', 'soar', 'raises']
    bearish_words = ['fall', 'down', 'drop', 'slump', 'plunge', 'bear', 'low', 'negative', 'loss', 'crash', 'dip', 'cut', 'sink', 'weak', 'miss', 'lowers', 'decline']
    text = text.lower()
    bull_score = sum(1 for word in bullish_words if word in text)
    bear_score = sum(1 for word in bearish_words if word in text)
    if bull_score > bear_score:
        return "🐂 Bullish"
    if bear_score > bull_score:
        return "🐻 Bearish"
    return "⚖️ Neutral"

# ── BATCH MARKET DATA FETCH ──
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
            prev_close = np.nan
            if 'Close' in daily_data and ticker in daily_data['Close']:
                close_series = daily_data['Close'][ticker].dropna()
                if len(close_series) >= 2:
                    prev_close = close_series.iloc[-2]

            current_price = np.nan
            if 'Close' in intra_data and ticker in intra_data['Close']:
                intra_close = intra_data['Close'][ticker].dropna()
                if len(intra_close) > 0:
                    current_price = intra_close.iloc[-1]
            if np.isnan(current_price) and 'Close' in daily_data and ticker in daily_data['Close']:
                current_price = daily_data['Close'][ticker].iloc[-1]

            pct_change = np.nan
            if not np.isnan(current_price) and not np.isnan(prev_close) and prev_close > 0:
                pct_change = (current_price - prev_close) / prev_close * 100

            day_vol = 0
            if 'Volume' in intra_data and ticker in intra_data['Volume']:
                day_vol = intra_data['Volume'][ticker].sum()

            avg_vol = np.nan
            if 'Volume' in daily_data and ticker in daily_data['Volume']:
                vol_series = daily_data['Volume'][ticker].dropna()
                if len(vol_series) >= 21:
                    avg_vol = vol_series.iloc[-21:-1].mean()
                elif len(vol_series) > 1:
                    avg_vol = vol_series.iloc[:-1].mean()

            rel_vol = day_vol / avg_vol if avg_vol > 0 and day_vol > 0 else np.nan

            rows.append({
                "Asset": label,
                "Symbol": ticker,
                "Price": current_price,
                "Change %": pct_change,
                "Rel Vol": rel_vol
            })
        except Exception:
            rows.append({
                "Asset": label, "Symbol": ticker,
                "Price": np.nan, "Change %": np.nan, "Rel Vol": np.nan
            })
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def get_ticker_news(ticker_symbol):
    try:
        return yf.Ticker(ticker_symbol).news[:3]
    except:
        return []

# ── STYLING FUNCTIONS ──
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
        df_news = fnews.get_news()['news']
        return df_news.head(10)
    except:
        return pd.DataFrame()

# ── SIDEBAR ──
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

global_df   = full_market[full_market['Asset'].isin(GLOBAL_TICKERS.keys())].copy()
sector_df   = full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())].copy()
etf_df      = full_market[full_market['Asset'].isin(ETF_TICKERS.keys())].copy()
twentyfour_df = full_market[full_market['Asset'].isin(TWENTYFOUR_TICKERS.keys())].copy()
mag7_df     = full_market[full_market['Asset'].isin(MAG7_TICKERS.keys())].copy()

for df in [global_df, sector_df, etf_df, twentyfour_df, mag7_df]:
    df.sort_values('Change %', ascending=False, inplace=True)

# Benchmark for Relative Strength
benchmark = "SPY (S&P 500 ETF)"
benchmark_change = full_market.loc[full_market['Asset'] == benchmark, 'Change %'].iloc[0] if benchmark in full_market['Asset'].values else 0.0

for df in [sector_df, etf_df, twentyfour_df, mag7_df]:
    df['RS'] = df['Change %'] - benchmark_change

top_gainers = full_market.sort_values('Change %', ascending=False).head(6)
top_losers  = full_market.sort_values('Change %', ascending=True).head(6)

# Mover sentiment & news
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

st.sidebar.divider()
st.sidebar.subheader("📰 Mover News & Sentiment")

st.sidebar.markdown("**Leaders 🚀**")
for _, row in top_gainers.iterrows():
    overall = mover_sentiments.get(row['Asset'], "⚖️ Neutral")
    vol_note = " 🔥" if row.get('Rel Vol', 0) > 1.5 else ""
    with st.sidebar.expander(f"{row['Asset']} ({row['Change %']:+.2f}%) {overall}{vol_note}"):
        news_items = mover_news_dict.get(row['Asset'], [])
        if news_items:
            st.markdown(f"**Overall: {overall}**")
            for item in news_items:
                title = item.get('title', 'No Title')
                link = item.get('link', '#')
                publisher = item.get('publisher', 'Unknown')
                sentiment = analyze_sentiment(title)
                st.markdown(f"**{sentiment}** [{title}]({link})")
                st.caption(f"Source: {publisher}")
                st.divider()
        else:
            st.write("No recent headlines.")

st.sidebar.markdown("**Laggards 📉**")
for _, row in top_losers.iterrows():
    overall = mover_sentiments.get(row['Asset'], "⚖️ Neutral")
    vol_note = " 🔥" if row.get('Rel Vol', 0) > 1.5 else ""
    with st.sidebar.expander(f"{row['Asset']} ({row['Change %']:+.2f}%) {overall}{vol_note}"):
        news_items = mover_news_dict.get(row['Asset'], [])
        if news_items:
            st.markdown(f"**Overall: {overall}**")
            for item in news_items:
                title = item.get('title', 'No Title')
                link = item.get('link', '#')
                publisher = item.get('publisher', 'Unknown')
                sentiment = analyze_sentiment(title)
                st.markdown(f"**{sentiment}** [{title}]({link})")
                st.caption(f"Source: {publisher}")
                st.divider()
        else:
            st.write("No recent headlines.")

# ── MAIN PAGE ──
st.title("🏛️ Pro Market Terminal")
st.caption(f"Status: Live | EST Time: {time_now} | Auto-Refresh: {refresh}s")

st.subheader("🔍 Market Scanner")
col_g, col_l, col_b = st.columns([2, 2, 1])

with col_g:
    st.write("**Top 6 Leaders 🚀**")
    for _, row in top_gainers.iterrows():
        overall = mover_sentiments.get(row['Asset'], "⚖️ Neutral")
        vol_note = " 🔥" if row.get('Rel Vol', 0) > 1.5 else ""
        st.write(f"🟢 {row['Asset']}: `{row['Change %']:+.2f}%` {overall}{vol_note}")

with col_l:
    st.write("**Top 6 Laggards 📉**")
    for _, row in top_losers.iterrows():
        overall = mover_sentiments.get(row['Asset'], "⚖️ Neutral")
        vol_note = " 🔥" if row.get('Rel Vol', 0) > 1.5 else ""
        st.write(f"🔴 {row['Asset']}: `{row['Change %']:+.2f}%` {overall}{vol_note}")

with col_b:
    st.write("**Breadth**")
    up_count = len(full_market[full_market['Change %'] > 0])
    down_count = len(full_market[full_market['Change %'] < 0])
    st.metric("Up / Down", f"{up_count} / {down_count}", delta=f"{up_count - down_count}")

st.divider()

# ── TABS ──
tab1, tab2, tab3, tab4 = st.tabs([
    "🌎 Global Indices",
    "📈 Sectors, ETFs, 24h & Mag7",
    "📊 Relative Strength & Charts",
    "⚖️ Options Sentiment (Mag7 + SPY/QQQ/VIX)"
])

with tab1:
    st.subheader("Major Markets & Indices")
    styled = global_df.drop(columns=['Symbol']).style.format({
        "Price": "{:.2f}",
        "Change %": "{:+.2f}%",
        "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-"
    }).map(color_pct, subset=["Change %"]).map(color_rel, subset="Rel Vol")
    st.dataframe(styled, use_container_width=True, hide_index=True)

with tab2:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.subheader("Sectors")
        styled_sector = sector_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-",
            "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_sector, use_container_width=True, hide_index=True)
    with c2:
        st.subheader("ETFs")
        styled_etf = etf_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-",
            "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_etf, use_container_width=True, hide_index=True)
    with c3:
        st.subheader("24h & Commodities")
        styled_24h = twentyfour_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-",
            "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_24h, use_container_width=True, hide_index=True)
    with c4:
        st.subheader("Magnificent 7")
        styled_mag = mag7_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-",
            "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_mag, use_container_width=True, hide_index=True)

with tab3:
    st.subheader(f"Relative Strength (vs. {benchmark})")
    for name, df in [("Sectors", sector_df), ("24h & Commodities", twentyfour_df), ("Magnificent 7", mag7_df)]:
        rs_sorted = df.sort_values('RS', ascending=False)
        st.write(f"**{name}**")
        st.bar_chart(rs_sorted.set_index("Asset")["RS"], use_container_width=True)
        st.divider()

    st.subheader("Intraday Charts (EST / 24h where applicable)")
    selected = st.multiselect(
        'Select Asset to View',
        list(ALL_TICKERS.keys()),
        default=["SPY (S&P 500 ETF)", "Bitcoin 24h (BTC-USD)", "Nvidia (NVDA)", "Technology (XLK)"]
    )
    for label in selected:
        ticker = ALL_TICKERS[label]
        data = yf.Ticker(ticker).history(period='1d', interval='5m')
        if not data.empty:
            data.index = data.index.tz_convert('US/Eastern')
            st.write(f"**{label}**")
            st.line_chart(data['Close'], use_container_width=True)

with tab4:
    st.subheader("Options Sentiment (Put/Call Volume Ratio)")
    st.caption(
        "Aggregated from nearest 5 expirations • "
        "PCR = Put Volume / Call Volume • >1.0 → bearish tilt • <0.8 → bullish tilt • "
        "Today's traded volume only • SPY, QQQ & VIX added"
    )

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
                put_vol  = 0.0
                for exp in expirations[:5]:
                    chain = ticker.option_chain(exp)
                    call_vol += chain.calls["volume"].fillna(0).sum()
                    put_vol  += chain.puts["volume"].fillna(0).sum()

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

    data = get_options_pcr()

    # 5-column layout for 10 assets
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
            help=f"Call volume: {info['call_vol']:,} • Put volume: {info['put_vol']:,}"
        )

    st.divider()

    # Aggregate
    total_call = sum(d.get("call_vol", 0) for d in data.values() if "error" not in d)
    total_put  = sum(d.get("put_vol",  0) for d in data.values() if "error" not in d)
    agg_pcr = total_put / total_call if total_call > 0 else 0.0

    col1, col2 = st.columns([1, 3])
    col1.metric("Aggregate PCR (All 10)", f"{agg_pcr:.2f}")
    if agg_pcr < 0.80:
        col2.success("**Overall bullish options flow** across Mag7 + SPY/QQQ/VIX")
    elif agg_pcr > 1.10:
        col2.error("**Overall bearish options flow** across Mag7 + SPY/QQQ/VIX")
    else:
        col2.info("**Balanced options sentiment** across Mag7 + SPY/QQQ/VIX")

    st.caption("Data via yfinance • Refreshes every 5 minutes • Low-liquidity contracts zero-filled • VIX follows same PCR logic (high PCR = higher vol expected = bearish market tilt)")
