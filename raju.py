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

# ================================================
# PAGE CONFIG
# ================================================
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ================================================
# API KEYS (RECOMMENDATION: Move to st.secrets for production)
# ================================================
FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"
ALPHA_VANTAGE_API_KEY = "Q6Z6I3QPW56O7NWP"

# ================================================
# TICKER CONFIGS + TRADING THEMES
# ================================================
USER_HOT_LIST = [
    "NET", "RDDT", "CRCL", "CRWD", "CRM", "BMNR", "UNH", "SOFI", "APP", "ORCL",
    "RBRK", "MRVL", "ARM", "COIN", "SMCI", "IBM", "AAL", "BA", "SHOP", "LMND",
    "RIVN", "DUOL", "MDB", "HOOD", "TNA", "ADBE", "PLTR", "NOW", "PANW", "GS",
    "SNDK", "OXY", "ALB", "KO", "LLY", "BABA", "GOOGL", "CRWV", "LULU", "ALAB",
    "AVGO", "IREN", "MU", "BIDU", "OKLO", "DELL", "TSM", "RKLB", "MP", "COST",
    "CYNA", "QBTS", "QUBT", "RGTI", "QCOM", "BE", "RBLX", "CIFR", "IBIT", "ASTS",
    "CAT", "FDX", "XOM", "WDC", "SLV", "ZSL", "TQQQ", "STX"
]

GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES (S&P 500 Fut)": "ES=F", "NQ (Nasdaq Fut)": "NQ=F",
    "YM (Dow Fut)": "YM=F", "RTY (Russell 2000)": "RTY=F",
    "SPY": "SPY", "QQQ": "QQQ", "10Y Yield": "^TNX",
    "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
}

SECTOR_TICKERS = {
    "Tech (XLK)": "XLK", "Software (IGV)": "IGV", "Semiconductor (SMH)": "SMH",
    "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV",
    "Disc (XLY)": "XLY", "Indus (XLI)": "XLI", "Utils (XLU)": "XLU",
    "RE": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"
}

NEO_CLOUD_TICKERS = {
    "Nebius": "NBIS", "Vertiv": "VRT", "Arista": "ANET",
    "Supermicro": "SMCI", "Dell": "DELL", "Palantir": "PLTR"
}

MAG7_TICKERS = {
    "Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN",
    "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"
}

TRADING_THEMES = {
    "🔵 SEMICONDUCTORS": ["SMH", "SOXL", "NVDA", "AMD", "AVGO", "QCOM", "INTC", "MU", "MRVL", "TSM", "ARM", "SMCI", "WDC", "ALAB"],
    "🟣 SOFTWARE / SaaS": ["IGV", "MSFT", "CRM", "NOW", "ADBE", "CRWD", "MDB", "PLTR", "RBRK", "ORCL", "IBM"],
    "🟢 NEO CLOUD / AI INFRA": ["CRWD", "NBIS", "APP", "ALAB", "RBRK", "PLTR", "SMCI", "DELL"],
    "🟡 MEGA CAP TECH": ["QQQ", "META", "GOOGL", "AAPL", "AMZN", "MSFT", "NVDA", "TSLA"],
    "🟠 CRYPTO / BTC": ["BTC-USD", "IBIT", "MSTR", "COIN", "CIFR", "IREN", "BMNR", "CRCL"],
    "🟤 SMALL CAPS": ["IWM", "TNA", "QBTS", "RGTI", "ASTS", "OKLO", "TEM"],
    "🔴 CONSUMER / HIGH BETA": ["AMZN", "TSLA", "RBLX", "CVNA", "RIVN", "LULU", "NKE", "DUOL", "AAL"],
    "🏦 FINANCIALS": ["JPM", "SOFI", "HOOD", "LMND", "UNH"],
    "⚡ ENERGY": ["XOM", "OXY", "BE", "OKLO"],
    "🏗️ INDUSTRIALS/SPACE": ["CAT", "BA", "RKLB", "ASTS", "FDX"],
    "🏥 HEALTHCARE": ["LLY", "UNH", "TEM"],
    "🥇 COMMODITIES/METALS": ["GC=F", "SLV", "AGQ", "ZSL", "ALB", "MP"],
    "🔥 USER HOT LIST": USER_HOT_LIST
}

symbol_to_label = {}
for d in [GLOBAL_TICKERS, SECTOR_TICKERS, NEO_CLOUD_TICKERS, MAG7_TICKERS]:
    for label, sym in d.items():
        if sym not in symbol_to_label:
            symbol_to_label[sym] = label
for sublist in TRADING_THEMES.values():
    for sym in sublist:
        if sym not in symbol_to_label:
            symbol_to_label[sym] = sym

ALL_SYMBOLS = list(symbol_to_label.keys())
ANALYST_SYMBOLS = sorted({sym for sublist in TRADING_THEMES.values() for sym in sublist})
MAG7_HOT_SYMBOLS = list(MAG7_TICKERS.values()) + ["SPY", "QQQ"]

HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO',
    'HD', 'COST', 'NFLX', 'DIS', 'PFE', 'MRK', 'LLY', 'AVGO'
}

# (The rest of your script continues EXACTLY the same…)

# ────────────────────────────────────────────────
#  AUTO-REFRESH
# ────────────────────────────────────────────────
st_autorefresh(interval=45000, key="global_refresh")
