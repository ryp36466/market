import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
from finvizfinance.news import News
import plotly.express as px
import requests
# Page configuration
st.set_page_config(page_title="Pro Market Terminal", page_icon="🏛️", layout="wide")

# --- TICKER CONFIGURATIONS ---
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

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS, **TWENTYFOUR_TICKERS, **MAG7_TICKERS}

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

# --- BATCH DATA FETCH ---
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
            if np.isnan(current_price):
                if 'Close' in daily_data and ticker in daily_data['Close']:
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
    
@st.cache_data(ttl=600)
def fetch_finviz_news():
    try:
        fnews = News()
        # This gets the latest general market news from Finviz
        df_news = fnews.get_news()['news']
        return df_news.head(10) # Return top 10 headlines
    except:
        return pd.DataFrame()

# --- Finviz News Section in Sidebar ---
st.sidebar.divider()
st.sidebar.subheader("🗞️ Market Intelligence")

news_data = fetch_finviz_news()

if not news_data.empty:
    for _, row in news_data.iterrows():
        # Using an expander to keep the sidebar clean
        with st.sidebar.expander(f"{row['Source']} | {row['Date']}"):
            st.write(row['Title'])
            link = row.get('url') or row.get('URL')
            st.markdown(f"[Read Article]({link})")
else:
    st.sidebar.info("News feed temporarily unavailable.")

# --- APP LOGIC ---
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

full_market = fetch_all_market_data()
full_market = full_market.dropna(subset=['Change %'])

global_df = full_market[full_market['Asset'].isin(GLOBAL_TICKERS.keys())].copy()
sector_df = full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())].copy()
etf_df = full_market[full_market['Asset'].isin(ETF_TICKERS.keys())].copy()
twentyfour_df = full_market[full_market['Asset'].isin(TWENTYFOUR_TICKERS.keys())].copy()
mag7_df = full_market[full_market['Asset'].isin(MAG7_TICKERS.keys())].copy()

global_df = global_df.sort_values('Change %', ascending=False)
sector_df = sector_df.sort_values('Change %', ascending=False)
etf_df = etf_df.sort_values('Change %', ascending=False)
twentyfour_df = twentyfour_df.sort_values('Change %', ascending=False)
mag7_df = mag7_df.sort_values('Change %', ascending=False)

# Benchmark for RS
benchmark = "SPY (S&P 500 ETF)"
benchmark_change = 0.0
if benchmark in full_market['Asset'].values:
    try:
        benchmark_change = full_market[full_market['Asset'] == benchmark]['Change %'].iloc[0]
    except:
        benchmark_change = 0.0
else:
    benchmark = "S&P 500 Futures (ES)"
    if benchmark in full_market['Asset'].values:
        try:
            benchmark_change = full_market[full_market['Asset'] == benchmark]['Change %'].iloc[0]
        except:
            benchmark_change = 0.0

sector_df['RS'] = sector_df['Change %'] - benchmark_change
etf_df['RS'] = etf_df['Change %'] - benchmark_change
twentyfour_df['RS'] = twentyfour_df['Change %'] - benchmark_change
mag7_df['RS'] = mag7_df['Change %'] - benchmark_change

top_gainers = full_market.sort_values('Change %', ascending=False).head(6)
top_losers = full_market.sort_values('Change %', ascending=True).head(6)

# --- MOVER SENTIMENT & NEWS ---
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
        if bull_count > bear_count:
            overall = "🐂 Bullish"
        elif bear_count > bull_count:
            overall = "🐻 Bearish"
        else:
            overall = "⚖️ Neutral"
    mover_sentiments[row['Asset']] = overall

# --- SIDEBAR ---
st.sidebar.title("🏛️ Market Settings")
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30)
st_autorefresh(interval=refresh * 1000, key="datarefresh")

st.sidebar.divider()
st.sidebar.subheader("📰 Mover News & Sentiment")

st.sidebar.markdown("**Leaders 🚀**")
for _, row in top_gainers.iterrows():
    overall = mover_sentiments.get(row['Asset'], "⚖️ Neutral")
    vol_note = " 🔥" if row.get('Rel Vol', 0) > 1.5 else ""
    news_items = mover_news_dict.get(row['Asset'], [])
    with st.sidebar.expander(f"{row['Asset']} ({row['Change %']:+.2f}%) {overall}{vol_note}"):
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
    news_items = mover_news_dict.get(row['Asset'], [])
    with st.sidebar.expander(f"{row['Asset']} ({row['Change %']:+.2f}%) {overall}{vol_note}"):
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

# --- MAIN ---
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

tab1, tab2, tab3 = st.tabs(["🌎 Global Indices", "📈 Sectors, ETFs, 24h & Mag7", "📊 Relative Strength & Charts","⚖️ Mag7 Options Sentiment"])

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
            "Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-", "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_sector, use_container_width=True, hide_index=True)
    with c2:
        st.subheader("ETFs")
        styled_etf = etf_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-", "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_etf, use_container_width=True, hide_index=True)
    with c3:
        st.subheader("24h & Commodities")
        styled_24h = twentyfour_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-", "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_24h, use_container_width=True, hide_index=True)
    with c4:
        st.subheader("Magnificent 7")
        styled_mag = mag7_df.drop(columns=['Symbol']).style.format({
            "Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": lambda x: f"{x:.2f}x" if not pd.isna(x) else "-", "RS": "{:+.2f}"
        }).map(color_pct, subset=["Change %", "RS"]).map(color_rel, subset="Rel Vol")
        st.dataframe(styled_mag, use_container_width=True, hide_index=True)

with tab3:
    st.subheader(f"Relative Strength (vs. {benchmark})")
    for name, df in [("Sectors", sector_df), ("24h & Commodities", twentyfour_df), ("Magnificent 7", mag7_df)]:
        rs_sorted = df.sort_values('RS', ascending=False)
        st.write(f"**{name}**")
        st.bar_chart(rs_sorted, y="Asset", x="RS", color="RS", use_container_width=True)
        st.divider()

    st.subheader("Intraday Charts (EST / 24h where applicable)")
    selected = st.multiselect('Select Asset to View', list(ALL_TICKERS.keys()),
                              default=["SPY (S&P 500 ETF)", "Bitcoin 24h (BTC-USD)", "Nvidia (NVDA)", "Technology (XLK)"])
    for label in selected:
        ticker = ALL_TICKERS[label]
        data = yf.Ticker(ticker).history(period='1d', interval='5m')
        if not data.empty:
            data.index = data.index.tz_convert('US/Eastern')
            st.write(f"**{label}**")
            st.line_chart(data['Close'], use_container_width=True)


# ── Add fourth tab for Mag7 Options Sentiment ──
tab1, tab2, tab3, tab4 = st.tabs([
    "🌎 Global Indices",
    "📈 Sectors, ETFs, 24h & Mag7",
    "📊 Relative Strength & Charts",
    "⚖️ Mag7 Options Sentiment"
])

# ... keep your tab1, tab2, tab3 code as-is ...

with tab4:
    st.subheader("Magnificent 7 Options Sentiment (Put/Call Volume Ratio)")
    st.caption(
        "Aggregated from nearest 5 expirations • "
        "PCR = Put Vol / Call Vol • >1.0 = bearish tilt, <0.8 = bullish tilt"
    )

    @st.cache_data(ttl=300, show_spinner="Loading Mag7 options data...")
    def get_mag7_pcr():
        results = {}
        for label, symbol in MAG7_TICKERS.items():
            try:
                ticker = yf.Ticker(symbol)
                expirations = ticker.options
                if not expirations:
                    results[label] = {"error": "No options"}
                    continue

                call_vol = 0
                put_vol = 0
                for exp in expirations[:5]:
                    chain = ticker.option_chain(exp)
                    call_vol += chain.calls["volume"].fillna(0).sum()
                    put_vol += chain.puts["volume"].fillna(0).sum()

                pcr = put_vol / call_vol if call_vol > 0 else 0.0
                sentiment = (
                    "🐂 Strongly Bullish" if pcr < 0.75 else
                    "🐂 Bullish" if pcr < 0.90 else
                    "⚖️ Neutral" if pcr < 1.10 else
                    "🐻 Bearish" if pcr < 1.30 else
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

    data = get_mag7_pcr()

    # Display in columns
    cols = st.columns(4)
    for i, (label, info) in enumerate(data.items()):
        col = cols[i % 4]
        if "error" in info:
            col.error(f"{label}\n{info['error']}")
            continue

        col.metric(
            label=f"{label}",
            value=f"{info['pcr']:.2f}",
            delta=info['sentiment'],
            help=f"Calls: {info['call_vol']:,} • Puts: {info['put_vol']:,}"
        )

    st.divider()

    # Optional aggregate view
    total_call = sum(d.get("call_vol", 0) for d in data.values() if "error" not in d)
    total_put  = sum(d.get("put_vol",  0) for d in data.values() if "error" not in d)
    agg_pcr = total_put / total_call if total_call > 0 else 0

    col1, col2 = st.columns([1, 3])
    col1.metric("Mag7 Aggregate PCR", f"{agg_pcr:.2f}")
    if agg_pcr < 0.8:
        col2.success("Overall bullish options flow in Mag7")
    elif agg_pcr > 1.1:
        col2.error("Overall bearish options flow in Mag7")
    else:
        col2.info("Balanced options sentiment in Mag7")

    st.caption("Data from yfinance • refreshed every 5 min • volume is today's traded volume")
 

import streamlit as st
import yfinance as yf

def display_options_sentiment(ticker_symbol):
    st.subheader(f"Total Market Sentiment: {ticker_symbol}")
    ticker = yf.Ticker(ticker_symbol)
    
    try:
        # 1. Get all available expiration dates
        expirations = ticker.options
        
        if not expirations:
            st.warning(f"No options found for {ticker_symbol}")
            return

        total_calls_vol = 0
        total_puts_vol = 0
        
        # 2. Loop through the first 5 expirations and sum volumes
        # This gives a "Daily Total" across the most active dates
        for exp in expirations[:5]:
            opt = ticker.option_chain(exp)
            total_calls_vol += opt.calls['volume'].sum()
            total_puts_vol += opt.puts['volume'].sum()
        
        # 3. Calculate the aggregated Put/Call Ratio
        vol_pcr = total_puts_vol / total_calls_vol if total_calls_vol > 0 else 0
        
        # 4. Display results
        col1, col2 = st.columns(2)
        col1.metric("Total Volume PCR", f"{vol_pcr:.2f}", help="Sum of daily volume across the next 5 expiration dates.")
        
        if vol_pcr < 0.7:
            col2.success("Sentiment: Strongly Bullish")
        elif vol_pcr > 1.1:
            col2.error("Sentiment: Strongly Bearish")
        else:
            col2.info("Sentiment: Neutral / Balanced")
            
    except Exception as e:
        st.error(f"Error fetching aggregated data: {e}")

def display_options_sentiment(ticker_symbol):
    st.subheader(f"Total Market Sentiment: {ticker_symbol}")
    ticker = yf.Ticker(ticker_symbol)
    
    try:
        expirations = ticker.options
        if not expirations:
            st.warning(f"No options found for {ticker_symbol}")
            return

        total_calls_vol = 0
        total_puts_vol = 0
        
        # Aggregating data from the first 5 expiration dates
        for exp in expirations[:5]:
            opt = ticker.option_chain(exp)
            total_calls_vol += opt.calls['volume'].sum()
            total_puts_vol += opt.puts['volume'].sum()
        
        vol_pcr = total_puts_vol / total_calls_vol if total_calls_vol > 0 else 0
        
        # UI Layout: Metrics on top, Chart below
        col1, col2 = st.columns(2)
        col1.metric("Aggregated PCR", f"{vol_pcr:.2f}")
        
        if vol_pcr < 0.7:
            col2.success("Sentiment: Strongly Bullish")
        elif vol_pcr > 1.1:
            col2.error("Sentiment: Strongly Bearish")
        else:
            col2.info("Sentiment: Neutral / Balanced")

        # Create the Pie Chart
        df_pie = pd.DataFrame({
            "Type": ["Calls", "Puts"],
            "Volume": [total_calls_vol, total_puts_vol]
        })
        
        fig = px.pie(
            df_pie, 
            values='Volume', 
            names='Type', 
            title=f"Call vs Put Volume (Next 5 Expirations)",
            color='Type',
            color_discrete_map={'Calls': '#00ff00', 'Puts': '#ff0000'} # Green for Calls, Red for Puts
        )
        
        st.plotly_chart(fig, use_container_width=True)
            
    except Exception as e:
        st.error(f"Error fetching data: {e}")

