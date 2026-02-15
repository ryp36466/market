import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz

# Page configuration
st.set_page_config(page_title="Pro Market Terminal", page_icon="🏛️", layout="wide")

# --- TICKER CONFIGURATIONS ---
GLOBAL_TICKERS = {
    "S&P 500 Futures (ES)": "ES=F",
    "Nasdaq 100 Futures (NQ)": "NQ=F",
    "Dow Jones Futures (YM)": "YM=F",
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
    "Bitcoin (IBIT)": "IBIT",
    "Gold (GLD)": "GLD",
    "Silver (SLV)": "SLV",
    "Bonds 20Y+ (TLT)": "TLT",
    "Semis (SMH)": "SMH",
    "Ark Innovation (ARKK)": "ARKK"
}

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS}

# --- SENTIMENT ---
def analyze_sentiment(text):
    if not text or not isinstance(text, str):
        return "⚖️ Neutral"
    bullish_words = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'growth', 'bull', 'high', 'positive', 'win', 'beat', 'boost', 'strong', 'outperform', 'soar', 'raises']
    bearish_words = ['fall', 'down', 'drop', 'slump', 'plunge', 'bear', 'low', 'negative', 'loss', 'crash', 'dip', 'cut', 'sink', 'weak', 'miss', 'lowers', 'decline']
    text = text.lower()
    bull_score = sum(1 for word in bullish_words if word in text)
    bear_score = sum(1 for word in bearish_words if word in text)
    if bull_score > bear_score: return "🐂 Bullish"
    if bear_score > bull_score: return "🐻 Bearish"
    return "⚖️ Neutral"

# --- BATCH DATA FETCH (much faster) ---
@st.cache_data(ttl=45)
def fetch_all_market_data():
    tickers_list = list(ALL_TICKERS.values())
    ticker_to_label = {v: k for k, v in ALL_TICKERS.items()}

    daily_data = yf.download(tickers=tickers_list, period="60d", interval="1d", progress=False)
    intra_data = yf.download(tickers=tickers_list, period="2d", interval="5m", prepost=True, progress=False)

    rows = []
    for ticker in tickers_list:
        label = ticker_to_label.get(ticker, ticker)
        try:
            # Previous close
            prev_close = np.nan
            if 'Close' in daily_data and ticker in daily_data['Close']:
                close_series = daily_data['Close'][ticker].dropna()
                if len(close_series) >= 2:
                    prev_close = close_series.iloc[-2]

            # Current price
            current_price = np.nan
            if 'Close' in intra_data and ticker in intra_data['Close']:
                intra_close = intra_data['Close'][ticker]
                if not intra_close.isna().all():
                    current_price = intra_close.iloc[-1]
            if np.isnan(current_price) and 'Close' in daily_data and ticker in daily_data['Close']:
                current_price = daily_data['Close'][ticker].iloc[-1]

            # % Change
            pct_change = np.nan
            if not np.isnan(current_price) and not np.isnan(prev_close) and prev_close > 0:
                pct_change = (current_price - prev_close) / prev_close * 100

            # Relative Volume
            day_vol = 0
            avg_vol = np.nan
            if 'Volume' in intra_data and ticker in intra_data['Volume']:
                day_vol = intra_data['Volume'][ticker].sum()
            if 'Volume' in daily_data and ticker in daily_data['Volume']:
                vol_daily = daily_data['Volume'][ticker].dropna()
                if len(vol_daily) >= 20:
                    avg_vol = vol_daily.iloc[-20:].mean()
            rel_vol = day_vol / avg_vol if avg_vol > 0 else np.nan

            rows.append({
                "Asset": label,
                "Symbol": ticker,
                "Price": current_price,
                "Change %": pct_change,
                "Rel Vol": rel_vol
            })
        except:
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

# --- STYLING ---
def color_pct(val):
    if pd.isna(val): return ''
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

def color_rel(val):
    if pd.isna(val): return ''
    if val > 2.0: return 'background-color: #90ee90; font-weight: bold'
    if val > 1.5: return 'background-color: #98fb98'
    if val < 0.5: return 'background-color: #ffb6c1'
    return ''

# --- APP LOGIC ---
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

full_market = fetch_all_market_data()
full_market = full_market.dropna(subset=['Change %'])

global_df = full_market[full_market['Asset'].isin(GLOBAL_TICKERS.keys())].copy()
sector_df = full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())].copy()
etf_df = full_market[full_market['Asset'].isin(ETF_TICKERS.keys())].copy()

# Sort for quick scanning
sector_df = sector_df.sort_values('Change %', ascending=False)
etf_df = etf_df.sort_values('Change %', ascending=False)
global_df = global_df.sort_values('Change %', ascending=False)

# Relative Strength vs ES
spy_change = global_df[global_df['Asset'] == "S&P 500 Futures (ES)"]['Change %'].values
if len(spy_change) > 0:
    spy_change = spy_change[0]
    sector_df['RS'] = sector_df['Change %'] - spy_change
    etf_df['RS'] = etf_df['Change %'] - spy_change
else:
    sector_df['RS'] = np.nan
    etf_df['RS'] = np.nan

top_gainers = full_market.sort_values('Change %', ascending=False).head(5)
top_losers = full_market.sort_values('Change %', ascending=True).head(5)

# --- SIDEBAR ---
st.sidebar.title("🏛️ Market Settings")
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="datarefresh")

st.sidebar.divider()
st.sidebar.subheader("📰 Leader News & Sentiment")
for _, row in top_gainers.iterrows():
    with st.sidebar.expander(f"{row['Asset']} ({row['Change %']:+.2f}%) {'📈' if row['Rel Vol'] > 1.5 else ''}"):
        news_items = get_ticker_news(row['Symbol'])
        if news_items:
            for item in news_items:
                title = item.get('title', 'No Title')
                link = item.get('link', '#')
                publisher = item.get('publisher', 'Unknown')
                sentiment = analyze_sentiment(title)
                st.markdown(f"**{sentiment}**")
                st.markdown(f"[{title}]({link})")
                st.caption(f"Source: {publisher}")
                st.divider()
        else:
            st.write("No recent headlines.")

# --- MAIN ---
st.title("🏛️ Pro Market Terminal")
st.caption(f"Status: Live | EST Time: {time_now} | Auto-Refresh: {refresh}s")

# Scanner
st.subheader("🔍 Market Scanner")
col_g, col_l, col_b = st.columns([2, 2, 1])

with col_g:
    st.write("**Top 5 Leaders 🚀**")
    for _, row in top_gainers.iterrows():
        vol_note = " 🔥" if row['Rel Vol'] > 1.5 else ""
        st.write(f"🟢 {row['Asset']}: `{row['Change %']:+.2f}%`{vol_note}")

with col_l:
    st.write("**Top 5 Laggards 📉**")
    for _, row in top_losers.iterrows():
        st.write(f"🔴 {row['Asset']}: `{row['Change %']:+.2f}%`")

with col_b:
    st.write("**Breadth**")
    up_count = len(full_market[full_market['Change %'] > 0])
    down_count = len(full_market[full_market['Change %'] < 0])
    st.metric("Up / Down", f"{up_count} / {down_count}", delta=f"{up_count - down_count}")

st.divider()

# Tabs
tab1, tab2, tab3 = st.tabs(["🌎 Global Indices", "📈 Sectors & ETFs", "📊 Relative Strength & Charts"])

with tab1:
    st.subheader("Major Markets")
    styled = global_df.drop(columns=['Symbol']).style.format({
        "Price": "{:.2f}",
        "Change %": "{:+.2f}%",
        "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-"
    }).map(color_pct, subset=["Change %"]).map(color_rel, subset="Rel Vol")
    st.dataframe(styled, use_container_width=True, hide_index=True)

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Sectors (SPDR)")
        styled_sector = sector_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}",
            "Change %": "{:+.2f}%",
            "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-",
            "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_sector, use_container_width=True, hide_index=True)
    with c2:
        st.subheader("Key ETFs")
        styled_etf = etf_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}",
            "Change %": "{:+.2f}%",
            "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-",
            "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_etf, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Sector Relative Strength (vs. S&P 500)")
    rs_sorted = sector_df.sort_values('RS', ascending=False)
    st.bar_chart(rs_sorted, y="Asset", x="RS", color="RS", use_container_width=True)

    st.divider()
    st.subheader("Intraday Charts (EST)")
    selected = st.multiselect('Select Asset to View', list(ALL_TICKERS.keys()), default=["S&P 500 Futures (ES)", "Technology (XLK)", "Semis (SMH)"])
    for label in selected:
        ticker = ALL_TICKERS[label]
        data = yf.Ticker(ticker).history(period='1d', interval='5m')
        if not data.empty:
            data.index = data.index.tz_convert('US/Eastern')
            st.write(f"**{label}**")
            st.line_chart(data['Close'], use_container_width=True)
