# ============================================================
# ALPHA TERMINAL PRO — STREAMLIT DASHBOARD
# ============================================================

# ────────────────────────────────────────────────
# IMPORTS
# ────────────────────────────────────────────────
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import requests

from streamlit_autorefresh import st_autorefresh
from bs4 import BeautifulSoup
from finvizfinance.news import News
from scipy.stats import norm

import plotly.express as px
import plotly.graph_objects as go


# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(
    page_title="Alpha Terminal Pro",
    page_icon="🏛️",
    layout="wide"
)


# ============================================================
# USER WATCHLIST
# ============================================================
USER_HOT_LIST = [
    "NET", "RDDT", "CRCL", "CRWD", "CRM", "BMNR", "UNH", "SOFI", "APP", "ORCL",
    "RBRK", "MRVL", "ARM", "COIN", "SMCI", "IBM", "AAL", "BA", "SHOP", "LMND",
    "RIVN", "DUOL", "MDB", "HOOD", "TNA", "ADBE", "PLTR", "NOW", "PANW", "GS",
    "SNDK", "OXY", "ALB", "KO", "LLY", "BABA", "GOOGL", "CRWV", "LULU", "ALAB",
    "AVGO", "IREN", "MU", "BIDU", "OKLO", "DELL", "TSM", "RKLB", "MP", "COST",
    "CYNA", "QBTS", "QUBT", "RGTI", "QCOM", "BE", "RBLX", "CIFR", "IBIT", "ASTS",
    "CAT", "FDX", "XOM", "WDC", "SLV", "ZSL", "TQQQ", "STX"
]


# ============================================================
# MARKET CONFIGURATION
# ============================================================
GLOBAL_TICKERS = {
    "VIX": "^VIX",
    "ES (S&P 500 Fut)": "ES=F",
    "NQ (Nasdaq Fut)": "NQ=F",
    "YM (Dow Fut)": "YM=F",
    "RTY (Russell 2000)": "RTY=F",
    "SPY": "SPY",
    "QQQ": "QQQ",
    "10Y Yield": "^TNX",
    "DXY": "DX-Y.NYB",
    "S&P 500": "^GSPC"
}

SECTOR_TICKERS = {
    "Tech (XLK)": "XLK",
    "Software (IGV)": "IGV",
    "Semiconductor (SMH)": "SMH",
    "Financials (XLF)": "XLF",
    "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV",
    "Disc (XLY)": "XLY",
    "Indus (XLI)": "XLI",
    "Utils (XLU)": "XLU",
    "RE": "XLRE",
    "Staples (XLP)": "XLP",
    "Materials (XLB)": "XLB"
}

MAG7_TICKERS = {
    "Apple": "AAPL",
    "MSFT": "MSFT",
    "Nvidia": "NVDA",
    "Amazon": "AMZN",
    "Google": "GOOGL",
    "Meta": "META",
    "Tesla": "TSLA"
}


# ============================================================
# TRADING THEMES
# ============================================================
TRADING_THEMES = {
    "SEMICONDUCTORS": [
        "SMH", "SOXL", "NVDA", "AMD", "AVGO", "QCOM",
        "INTC", "MU", "MRVL", "TSM", "ARM", "SMCI"
    ],
    "SOFTWARE / SaaS": [
        "IGV", "MSFT", "CRM", "NOW", "ADBE", "CRWD",
        "MDB", "PLTR", "ORCL", "IBM"
    ],
    "MEGA CAP TECH": [
        "QQQ", "META", "GOOGL", "AAPL",
        "AMZN", "MSFT", "NVDA", "TSLA"
    ],
    "CRYPTO": [
        "BTC-USD", "IBIT", "COIN", "CIFR"
    ],
    "USER HOT LIST": USER_HOT_LIST
}


# ============================================================
# SYMBOL MAPPING
# ============================================================
symbol_to_label = {}

for group in [GLOBAL_TICKERS, SECTOR_TICKERS, MAG7_TICKERS]:
    for label, sym in group.items():
        symbol_to_label.setdefault(sym, label)

for symbols in TRADING_THEMES.values():
    for sym in symbols:
        symbol_to_label.setdefault(sym, sym)

ALL_SYMBOLS = list(symbol_to_label.keys())


# ============================================================
# SENTIMENT + NEWS FILTERS
# ============================================================
HIGH_IMPACT_KEYWORDS = [
    "earnings", "eps", "revenue", "guidance",
    "upgrade", "downgrade", "price target",
    "acquisition", "merger", "lawsuit",
    "fed", "inflation", "surge", "plunge"
]

LOW_IMPACT_KEYWORDS = [
    "interview", "opinion", "recap",
    "blog", "podcast", "analysis"
]


def is_high_impact(title: str) -> bool:
    t = title.lower()
    if any(k in t for k in LOW_IMPACT_KEYWORDS):
        return False
    return any(k in t for k in HIGH_IMPACT_KEYWORDS)


def get_sentiment_score(text: str):
    bull_words = ["surge", "rally", "beat", "growth", "strong"]
    bear_words = ["drop", "miss", "weak", "decline", "cut"]

    score = sum(w in text.lower() for w in bull_words) \
          - sum(w in text.lower() for w in bear_words)

    if score > 0:
        return "Bullish", score
    elif score < 0:
        return "Bearish", score
    return "Neutral", 0


# ============================================================
# DATA FUNCTIONS
# ============================================================
@st.cache_data(ttl=20)
def fetch_market_snapshot():
    hist = yf.download(ALL_SYMBOLS, period="10d", interval="1d", progress=False)

    rows = []

    for sym in ALL_SYMBOLS:
        try:
            tk = yf.Ticker(sym)
            info = tk.fast_info

            price = info.get("lastPrice")
            prev = info.get("previousClose")

            if not price or not prev:
                continue

            change = (price - prev) / prev * 100

            rows.append({
                "Symbol": sym,
                "Price": round(price, 2),
                "Change %": round(change, 2)
            })

        except Exception:
            continue

    return pd.DataFrame(rows), hist


# ============================================================
# UI
# ============================================================
market_df, hist_data = fetch_market_snapshot()

st.title("Alpha Terminal Pro")

st.caption(
    f"Last Updated: {datetime.datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')}"
)


# ============================================================
# OVERVIEW TABLE
# ============================================================
st.subheader("Market Snapshot")

st.dataframe(
    market_df.style.background_gradient(
        cmap="RdYlGn",
        subset=["Change %"]
    ),
    use_container_width=True
)


# ============================================================
# RELATIVE STRENGTH CHART
# ============================================================
st.subheader("Relative Strength (vs SPY)")

try:
    df = hist_data['Close'][["SPY"]].dropna()
    norm_df = (df / df.iloc[0] - 1) * 100

    fig = px.line(norm_df, title="SPY Performance (%)")

    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Error: {e}")


# ============================================================
# AUTO REFRESH
# ============================================================
st_autorefresh(interval=45000, key="refresh")
