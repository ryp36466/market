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
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================================================ #
# PAGE CONFIG
# ================================================ #
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ================================================ #
# API KEYS (Use st.secrets for production)
# ================================================ #
FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"
# Your FMP Key provided: thDjYnltvzKxDlpUgS00v4j9gfa8jHGj

# ================================================ #
# TICKER CONFIGS + TRADING THEMES
# ================================================ #
USER_HOT_LIST = [
    "NET", "RDDT", "CRCL", "CRWD", "CRM", "BMNR", "UNH", "SOFI", "APP", "ORCL", "RBRK", 
    "MRVL", "ARM", "COIN", "SMCI", "IBM", "AAL", "BA", "SHOP", "LMND", "RIVN", "DUOL", 
    "MDB", "HOOD", "TNA", "ADBE", "PLTR", "NOW", "PANW", "GS", "SNDK", "OXY", "ALB", 
    "KO", "LLY", "BABA", "GOOGL", "LULU", "ALAB", "AVGO", "IREN", "MU", "BIDU", 
    "OKLO", "DELL", "TSM", "RKLB", "MP", "COST", "QBTS", "QUBT", "RGTI", "QCOM", 
    "BE", "RBLX", "CIFR", "IBIT", "ASTS", "CAT", "FDX", "XOM", "WDC", "SLV", "TQQQ", "STX"
]

GLOBAL_TICKERS = {"VIX": "^VIX", "S&P 500": "SPY", "Nasdaq": "QQQ", "10Y Yield": "^TNX"}
SECTOR_TICKERS = {"Tech (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV"}
MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}

TRADING_THEMES = {
    "🔵 SEMICONDUCTORS": ["SMH", "NVDA", "AMD", "AVGO", "QCOM", "TSM", "ARM"],
    "🟣 SOFTWARE / SaaS": ["MSFT", "CRM", "NOW", "ADBE", "PLTR", "ORCL"],
    "🟠 CRYPTO / BTC": ["BTC-USD", "IBIT", "MSTR", "COIN"],
    "🔥 USER HOT LIST": USER_HOT_LIST
}

ALL_SYMBOLS = list(set(USER_HOT_LIST + list(GLOBAL_TICKERS.values()) + list(MAG7_TICKERS.values()) + list(SECTOR_TICKERS.values())))
ANALYST_SYMBOLS = sorted({sym for sublist in TRADING_THEMES.values() for sym in sublist if not sym.endswith('=F')})

# ================================================ #
# DATA FUNCTIONS
# ================================================ #

@st.cache_data(ttl=300)
def get_fmp_analyst_ratings(symbol):
    """Fetches historical analyst grades from FMP."""
    # Use st.secrets["FMP_API_KEY"] in production
    api_key = "thDjYnltvzKxDlpUgS00v4j9gfa8jHGj"
    url = f"https://financialmodelingprep.com/stable/historical-grades/{symbol}?limit=50&apikey={api_key}"
    try:
        r = requests.get(url, timeout=10)
        return pd.DataFrame(r.json()) if r.status_code == 200 else pd.DataFrame()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def fetch_market_snapshot():
    data = yf.download(ALL_SYMBOLS, period="2d", interval="5m", progress=False)
    rows = []
    for s in ALL_SYMBOLS:
        try:
            current_price = data['Close'][s].iloc[-1]
            prev_close = data['Close'][s].iloc[0]
            change = ((current_price - prev_close) / prev_close) * 100
            rows.append({"Symbol": s, "Price": current_price, "Change %": change, "RVOL": 1.0}) # Simplified RVOL
        except: continue
    return pd.DataFrame(rows)

# ================================================ #
# MAIN APP UI
# ================================================ #
st.title("🏛️ Alpha Terminal Pro")
market_df = fetch_market_snapshot()

# FIX: Define all tabs here to avoid NameError
tab_overview, tab_sectors, tab_themes, tab_analyst, tab_news = st.tabs([
    "📈 Overview", "🏢 Sectors", "🎯 Themes", "📊 Analyst Ratings", "📰 News"
])

with tab_overview:
    st.subheader("Market Snapshot")
    st.dataframe(market_df, use_container_width=True)

with tab_sectors:
    st.subheader("Sector Performance")
    sector_list = list(SECTOR_TICKERS.values())
    sect_df = market_df[market_df['Symbol'].isin(sector_list)]
    st.dataframe(sect_df, use_container_width=True)

with tab_themes:
    st.subheader("Trading Themes")
    theme_choice = st.selectbox("Select Theme", list(TRADING_THEMES.keys()))
    theme_tickers = TRADING_THEMES[theme_choice]
    theme_df = market_df[market_df['Symbol'].isin(theme_tickers)]
    st.dataframe(theme_df, use_container_width=True)

with tab_analyst:
    st.header("🏢 Institutional Intelligence (FMP)")
    selected_stock = st.selectbox("Select Ticker to Analyze", ANALYST_SYMBOLS, index=0)
    
    if selected_stock:
        df_ratings = get_fmp_analyst_ratings(selected_stock)
        if not df_ratings.empty:
            # Metrics
            upgrades = len(df_ratings[df_ratings['action'] == 'Upgrade'])
            downgrades = len(df_ratings[df_ratings['action'] == 'Downgrade'])
            m1, m2, m3 = st.columns(3)
            m1.metric("Upgrades", upgrades)
            m2.metric("Downgrades", downgrades)
            m3.metric("Total Reports", len(df_ratings))

            # Table
            display_df = df_ratings[['date', 'gradingCompany', 'fromGrade', 'toGrade', 'action']].copy()
            def style_action(val):
                color = '#00ff88' if val == 'Upgrade' else '#ff4444' if val == 'Downgrade' else '#cccccc'
                return f'color: {color}; font-weight: bold;'
            
            st.dataframe(display_df.style.applymap(style_action, subset=['action']), use_container_width=True)
        else:
            st.info("No data found for this ticker.")

with tab_news:
    st.subheader("Market News Feed")
    st.write("Fetching latest headlines...")

st_autorefresh(interval=60000, key="global_refresh")
