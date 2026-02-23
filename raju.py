import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import asyncio
import aiohttp
import requests
import time
import threading
from queue import Queue
from streamlit_autorefresh import st_autorefresh
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm

# RTD Specific Imports (Requires the 'src' folder from the cloned repo)
try:
    from src.rtd.rtd_worker import RTDWorker
    from src.utils.option_symbol_builder import OptionSymbolBuilder
    from src.ui.gamma_chart import GammaChartBuilder
    from src.ui.dashboard_layout import DashboardLayout
    RTD_AVAILABLE = True
except ImportError:
    RTD_AVAILABLE = False

# ────────────────────────────────────────────────
#  PAGE CONFIG & SESSION STATE
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

if 'initialized' not in st.session_state:
    st.session_state.initialized = False
    st.session_state.data_queue = Queue()
    st.session_state.stop_event = threading.Event()
    st.session_state.option_symbols = []
    st.session_state.active_thread = None
    st.session_state.last_figure = None
    st.session_state.loading_complete = False

FINNHUB_KEY = st.secrets.get("FINNHUB_API_KEY", "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog")

# ────────────────────────────────────────────────
#  MARKET DATA ENGINE
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES Fut": "ES=F", "NQ Fut": "NQ=F", "RTY Fut": "RTY=F",
    "SPY": "SPY", "QQQ": "QQQ", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"
}

TRADING_THEMES = {
    "🔥 SEMICONDUCTORS": ["NVDA", "AMD", "AVGO", "TSM", "ARM", "MU", "SMCI"],
    "☁️ SOFTWARE / AI": ["MSFT", "PLTR", "CRM", "CRWD", "NOW", "ORCL", "ADBE"],
    "🖥️ BIG TECH": ["AAPL", "GOOGL", "META", "AMZN", "NFLX", "TSLA"],
    "🚀 GROWTH": ["RKLB", "ASTS", "PLTR", "OKLO", "RIVN"]
}

ALL_SYMBOLS = sorted(list(set(list(GLOBAL_TICKERS.values()) + [s for t in TRADING_THEMES.values() for s in t])))

async def fetch_async(session, url):
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200: return await response.json()
    except: return None

async def get_market_package(symbols, news_tickers):
    async with aiohttp.ClientSession() as session:
        q_tasks = [fetch_async(session, f"https://finnhub.io/api/v1/quote?symbol={s.replace('^', '').split('=')[0]}&token={FINNHUB_KEY}") for s in symbols]
        to_date = datetime.datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        n_tasks = [fetch_async(session, f"https://finnhub.io/api/v1/company-news?symbol={s}&from={from_date}&to={to_date}&token={FINNHUB_KEY}") for s in news_tickers]
        results = await asyncio.gather(*(q_tasks + n_tasks))
        return results[:len(symbols)], results[len(symbols):]

@st.cache_data(ttl=30)
def fetch_terminal_data(news_focus):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    q_data, n_data = loop.run_until_complete(get_market_package(ALL_SYMBOLS, news_focus))
    return q_data, n_data

# ────────────────────────────────────────────────
#  UI LAYOUT
# ────────────────────────────────────────────────
st.title("🏛️ Alpha Terminal Pro")

with st.sidebar:
    st.header("⚙️ Control Center")
    target_news = st.multiselect("News Watchlist", ALL_SYMBOLS, default=["SPY", "NVDA", "TSLA"])
    if st.button("Manual Refresh"):
        st.cache_data.clear()
        st.rerun()

tabs = st.tabs(["📊 Market Overview", "📰 News Sentiment", "🎯 Live TOS Gamma (GEX)"])

# TAB 1: OVERVIEW
with tabs[0]:
    q_data, _ = fetch_terminal_data(target_news)
    st.subheader("Global Indices")
    cols = st.columns(len(GLOBAL_TICKERS))
    for i, (name, sym) in enumerate(GLOBAL_TICKERS.items()):
        cols[i].metric(name, f"{sym}")

# TAB 2: NEWS
with tabs[1]:
    _, n_data = fetch_terminal_data(target_news)
    st.subheader("Live Wire")
    if n_data:
        for news_list in n_data:
            if news_list:
                for item in news_list[:3]:
                    st.write(f"**{item['headline']}** ({item['source']})")

# TAB 3: LIVE GEX (The Merged Code)
with tabs[2]:
    if not RTD_AVAILABLE:
        st.error("RTD Source files not found. Ensure the 'src' folder is in your directory.")
    else:
        st.subheader("ThinkorSwim Real-Time Gamma")
        
        # Dashboard Layout Inputs
        symbol, expiry_date, strike_range, strike_spacing, refresh_rate, start_stop_button = DashboardLayout.create_input_section()
        
        gamma_chart_placeholder = st.empty()

        if 'chart_builder' not in st.session_state or st.session_state.get('last_symbol') != symbol:
            st.session_state.chart_builder = GammaChartBuilder(symbol)
            st.session_state.last_figure = st.session_state.chart_builder.create_empty_chart()
            st.session_state.last_symbol = symbol

        if st.session_state.last_figure:
            gamma_chart_placeholder.plotly_chart(st.session_state.last_figure, use_container_width=True)

        if start_stop_button:
            if not st.session_state.initialized:
                st.session_state.stop_event = threading.Event()
                st.session_state.data_queue = Queue()
                st.session_state.rtd_worker = RTDWorker(st.session_state.data_queue, st.session_state.stop_event)
                
                thread = threading.Thread(target=st.session_state.rtd_worker.start, args=([symbol],), daemon=True)
                thread.start()
                st.session_state.active_thread = thread
                st.session_state.initialized = True
                st.rerun()
            else:
                st.session_state.stop_event.set()
                st.session_state.initialized = False
                st.rerun()

        # Update Logic
        if st.session_state.initialized:
            if not st.session_state.data_queue.empty():
                data = st.session_state.data_queue.get()
                price_key = f"{symbol}:LAST"
                price = data.get(price_key)
                
                if price and not st.session_state.option_symbols:
                    st.session_state.option_symbols = OptionSymbolBuilder.build_symbols(
                        symbol, expiry_date, price, strike_range, strike_spacing
                    )
                    # Restart worker with full symbols
                    st.session_state.stop_event.set()
                    st.session_state.stop_event = threading.Event()
                    st.session_state.rtd_worker = RTDWorker(st.session_state.data_queue, st.session_state.stop_event)
                    threading.Thread(target=st.session_state.rtd_worker.start, args=([symbol] + st.session_state.option_symbols,), daemon=True).start()

                if st.session_state.option_symbols:
                    strikes = sorted([float(s.split('C')[-1]) for s in st.session_state.option_symbols if 'C' in s])
                    fig = st.session_state.chart_builder.create_chart(data, strikes, st.session_state.option_symbols)
                    st.session_state.last_figure = fig
                    gamma_chart_placeholder.plotly_chart(fig, use_container_width=True)
                    time.sleep(refresh_rate)
                    st.rerun()

st_autorefresh(interval=60000, key="global_refresh")
