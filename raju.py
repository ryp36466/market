import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
import requests
from scipy.stats import norm
import plotly.express as px
import plotly.graph_objects as go

# ────────────────────────────────────────────────
# PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ────────────────────────────────────────────────
# TICKERS
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "VIX": "^VIX",
    "S&P 500": "^GSPC"
}

SECTOR_TICKERS = {
    "Tech (XLK)": "XLK",
    "Financials (XLF)": "XLF",
    "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV",
    "Semis (SMH)": "SMH"
}

MAG7_TICKERS = {
    "Apple": "AAPL",
    "Microsoft": "MSFT",
    "Nvidia": "NVDA",
    "Amazon": "AMZN",
    "Google": "GOOGL",
    "Meta": "META",
    "Tesla": "TSLA"
}

TRADING_THEMES = {
    "🔵 Semiconductors": ["SMH", "NVDA", "AMD", "AVGO"],
    "🟣 Software": ["MSFT", "CRM", "NOW"],
    "🟡 Mega Cap": ["AAPL", "MSFT", "NVDA", "AMZN"],
}

# ────────────────────────────────────────────────
# SYMBOL BUILD
# ────────────────────────────────────────────────
symbol_to_label = {}
for d in [GLOBAL_TICKERS, SECTOR_TICKERS, MAG7_TICKERS]:
    for label, sym in d.items():
        symbol_to_label[sym] = label

for lst in TRADING_THEMES.values():
    for sym in lst:
        symbol_to_label.setdefault(sym, sym)

ALL_SYMBOLS = list(symbol_to_label.keys())

# ────────────────────────────────────────────────
# GLOBAL TICKER CACHE
# ────────────────────────────────────────────────
@st.cache_resource
def get_ticker_cache(symbols):
    return {sym: yf.Ticker(sym) for sym in symbols}

TICKER_CACHE = get_ticker_cache(ALL_SYMBOLS)

# ────────────────────────────────────────────────
# VECTOR GAMMA
# ────────────────────────────────────────────────
def calc_gamma_vectorized(S, K, T, sigma, r, q, opt_type, OI):

    S = np.array(S)
    K = np.array(K)
    T = np.maximum(np.array(T), 1e-6)
    sigma = np.maximum(np.array(sigma), 1e-6)

    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))

    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
    sign = np.where(opt_type == "call", 1, -1)

    return gamma * OI * 100 * S**2 * sign

# ────────────────────────────────────────────────
# MARKET SNAPSHOT
# ────────────────────────────────────────────────
@st.cache_data(ttl=60)
def fetch_market_snapshot():

    data = yf.download(
        tickers=ALL_SYMBOLS,
        period="5d",
        interval="5m",
        group_by="ticker",
        auto_adjust=True,
        threads=True
    )

    rows = []

    for sym in ALL_SYMBOLS:
        try:
            df = data[sym].dropna()

            price = df["Close"].iloc[-1]
            prev_close = df["Close"].iloc[-78]

            change = ((price - prev_close) / prev_close) * 100

            today_vol = df["Volume"].sum()
            avg_vol = df["Volume"].rolling(78).sum().iloc[-2]

            rvol = today_vol / avg_vol if avg_vol > 0 else 1

            rows.append({
                "Asset": symbol_to_label[sym],
                "Symbol": sym,
                "Price": price,
                "Change %": change,
                "RVOL": rvol
            })
        except:
            continue

    return pd.DataFrame(rows)

# ────────────────────────────────────────────────
# PUT CALL RATIO
# ────────────────────────────────────────────────
def get_pcr_data():
    results = []

    for label, sym in MAG7_TICKERS.items():
        try:
            tk = TICKER_CACHE[sym]
            opts = tk.options
            if not opts:
                continue

            cv = pv = 0
            for exp in opts[:2]:
                chain = tk.option_chain(exp)
                cv += chain.calls["volume"].sum()
                pv += chain.puts["volume"].sum()

            pcr = pv / cv if cv > 0 else 0

            results.append({
                "Asset": label,
                "PCR": round(pcr, 2),
                "Bias": "Bullish" if pcr < 0.85 else "Bearish" if pcr > 1.15 else "Neutral"
            })
        except:
            continue

    return pd.DataFrame(results)

# ────────────────────────────────────────────────
# UI
# ────────────────────────────────────────────────
market_df = fetch_market_snapshot()

est = pytz.timezone("US/Eastern")
now = datetime.datetime.now(est).strftime("%H:%M:%S")

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {now} | Optimized Edition")

tabs = st.tabs([
    "📈 Overview",
    "🔥 Sectors",
    "🎯 Themes",
    "📊 GEX",
    "🐳 Options"
])

# ────────────────────────────────────────────────
# OVERVIEW
# ────────────────────────────────────────────────
with tabs[0]:

    st.subheader("Key Indices")

    key_df = market_df[market_df["Symbol"].isin(["SPY", "QQQ", "^VIX"])]

    st.dataframe(key_df, use_container_width=True)

# ────────────────────────────────────────────────
# SECTORS
# ────────────────────────────────────────────────
with tabs[1]:

    sector_df = market_df[market_df["Symbol"].isin(SECTOR_TICKERS.values())]

    st.dataframe(sector_df, use_container_width=True)

# ────────────────────────────────────────────────
# THEMES
# ────────────────────────────────────────────────
with tabs[2]:

    for theme, tickers in TRADING_THEMES.items():
        st.markdown(f"### {theme}")
        df = market_df[market_df["Symbol"].isin(tickers)]
        st.dataframe(df.sort_values("Change %", ascending=False), use_container_width=True)

# ────────────────────────────────────────────────
# GEX TAB
# ────────────────────────────────────────────────
with tabs[3]:

    ticker = st.text_input("Ticker", value="SPY").upper()

    try:
        tk = yf.Ticker(ticker)
        options = tk.options

        if options:

            spot = tk.history(period="1d")["Close"].iloc[-1]

            chains = []

            for exp in options[:3]:
                chain = tk.option_chain(exp)

                chains.append(chain.calls.assign(type="call", exp=exp))
                chains.append(chain.puts.assign(type="put", exp=exp))

            df = pd.concat(chains)

            df["dte"] = (
                pd.to_datetime(df["exp"]) - datetime.datetime.now()
            ).dt.days / 365

            df["GEX"] = calc_gamma_vectorized(
                spot,
                df["strike"],
                df["dte"],
                df["impliedVolatility"],
                0.04,
                0.01,
                df["type"],
                df["openInterest"]
            )

            agg = df.groupby("strike")["GEX"].sum() / 1e6

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=agg.index,
                y=agg.values
            ))

            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(e)

# ────────────────────────────────────────────────
# OPTIONS TAB
# ────────────────────────────────────────────────
with tabs[4]:

    pcr_df = get_pcr_data()

    if not pcr_df.empty:
        st.dataframe(pcr_df, use_container_width=True)

# ────────────────────────────────────────────────
# SMART AUTO REFRESH
# ────────────────────────────────────────────────
hour = datetime.datetime.now().hour

if 9 <= hour <= 16:
    st_autorefresh(interval=180000, key="fast")
else:
    st_autorefresh(interval=600000, key="slow")
