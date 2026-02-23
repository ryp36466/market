import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy.stats import norm
from nltk.sentiment import SentimentIntensityAnalyzer
import datetime

# =========================================
# PAGE CONFIG
# =========================================
st.set_page_config(page_title="Alpha Terminal Pro", layout="wide")
st.title("🏛 Alpha Terminal Pro")
st.caption("Institutional-Grade Trading Dashboard")

# =========================================
# GLOBAL SETTINGS
# =========================================
RISK_FREE_RATE = 0.01
sia = SentimentIntensityAnalyzer()

GLOBAL_SYMBOLS = ["SPY", "QQQ", "^VIX", "^TNX", "DX-Y.NYB"]

# =========================================
# DATA ENGINE
# =========================================
@st.cache_data(ttl=30)
def fetch_market_snapshot():
    data = yf.download(GLOBAL_SYMBOLS, period="2d", interval="5m", progress=False)
    rows = []

    for sym in GLOBAL_SYMBOLS:
        try:
            close = data["Close"][sym].dropna()
            price = close.iloc[-1]
            prev = close.iloc[-2]
            change = (price - prev) / prev * 100

            rows.append({
                "Symbol": sym,
                "Price": round(price, 2),
                "Change %": round(change, 2)
            })
        except:
            continue

    return pd.DataFrame(rows)

# =========================================
# GAMMA ENGINE
# =========================================
def calculate_gamma(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

def build_gamma_heatmap(symbol):
    tk = yf.Ticker(symbol)
    spot = tk.history(period="1d")["Close"].iloc[-1]
    expiry = tk.options[0]
    chain = tk.option_chain(expiry)

    df = pd.concat([
        chain.calls.assign(type="call"),
        chain.puts.assign(type="put")
    ])

    T = 1 / 365

    df["gamma"] = calculate_gamma(
        spot,
        df["strike"],
        T,
        RISK_FREE_RATE,
        df["impliedVolatility"]
    )

    df["gex"] = (
        df["gamma"] *
        df["openInterest"] *
        spot**2 *
        0.01 *
        np.where(df["type"] == "call", 1, -1)
    )

    grouped = df.groupby("strike")["gex"].sum().reset_index()

    # Gamma flip
    grouped = grouped.sort_values("strike")
    grouped["cum_gex"] = grouped["gex"].cumsum()
    flip_strike = grouped.iloc[(grouped["cum_gex"].abs()).argsort()[:1]]["strike"].values[0]

    heatmap = df.pivot_table(
        values="gex",
        index="strike",
        columns="type",
        aggfunc="sum"
    ).fillna(0)

    fig = go.Figure(go.Heatmap(
        z=heatmap.values,
        x=heatmap.columns,
        y=heatmap.index,
        colorscale="RdBu",
        zmid=0
    ))

    fig.add_hline(y=spot, line_dash="dash", annotation_text="SPOT")
    fig.add_hline(y=flip_strike, line_color="yellow", annotation_text="Gamma Flip")

    fig.update_layout(height=700)

    return fig, grouped["gex"].sum()

# =========================================
# OPTIONS FLOW ENGINE
# =========================================
def detect_unusual_flow(symbol):
    tk = yf.Ticker(symbol)
    expiry = tk.options[0]
    chain = tk.option_chain(expiry)

    df = pd.concat([
        chain.calls.assign(type="call"),
        chain.puts.assign(type="put")
    ])

    df["premium"] = df["volume"] * df["lastPrice"] * 100
    df["vol_oi_ratio"] = df["volume"] / df["openInterest"]

    flow = df[
        (df["premium"] > 500000) &
        (df["vol_oi_ratio"] > 2)
    ].copy()

    flow["Direction"] = np.where(
        flow["type"] == "call",
        "Bullish",
        "Bearish"
    )

    return flow[[
        "strike",
        "type",
        "volume",
        "openInterest",
        "premium",
        "Direction"
    ]]

# =========================================
# AI NEWS ENGINE
# =========================================
def fetch_ai_news(symbol):
    tk = yf.Ticker(symbol)
    news = tk.news
    rows = []

    for item in news[:20]:
        title = item["title"]
        score = sia.polarity_scores(title)["compound"]

        rows.append({
            "Title": title,
            "Sentiment Score": score
        })

    df = pd.DataFrame(rows)
    return df.sort_values("Sentiment Score", ascending=False)

# =========================================
# MARKET REGIME
# =========================================
def detect_regime(snapshot, total_gex):
    spy = snapshot[snapshot["Symbol"] == "SPY"]["Change %"].values[0]
    vix = snapshot[snapshot["Symbol"] == "^VIX"]["Change %"].values[0]

    if total_gex > 0:
        if spy > 0:
            return "🟢 Long Gamma Trend"
        else:
            return "🟡 Controlled Pullback"
    else:
        return "🔴 Short Gamma Volatility Expansion"

# =========================================
# PORTFOLIO ENGINE
# =========================================
if "cash" not in st.session_state:
    st.session_state.cash = 100000.0
if "positions" not in st.session_state:
    st.session_state.positions = {}

# =========================================
# TABS
# =========================================
tabs = st.tabs([
    "📊 Overview",
    "📊 Gamma Exposure",
    "💰 Options Flow",
    "🧠 AI News",
    "💼 Portfolio"
])

# =========================================
# OVERVIEW
# =========================================
with tabs[0]:
    snapshot = fetch_market_snapshot()
    st.dataframe(snapshot, use_container_width=True)

# =========================================
# GAMMA
# =========================================
with tabs[1]:
    symbol = st.text_input("Symbol", "SPY")
    try:
        fig, total_gex = build_gamma_heatmap(symbol)
        st.plotly_chart(fig, use_container_width=True)

        regime = detect_regime(snapshot, total_gex)
        st.metric("Market Regime", regime)

    except:
        st.error("Options data unavailable.")

# =========================================
# FLOW
# =========================================
with tabs[2]:
    symbol = st.text_input("Flow Symbol", "SPY", key="flow")
    try:
        flow = detect_unusual_flow(symbol)
        st.dataframe(flow, use_container_width=True)
    except:
        st.warning("No unusual flow detected.")

# =========================================
# AI NEWS
# =========================================
with tabs[3]:
    symbol = st.text_input("News Symbol", "SPY", key="news")
    try:
        news = fetch_ai_news(symbol)
        st.dataframe(news, use_container_width=True)
    except:
        st.warning("News unavailable.")

# =========================================
# PORTFOLIO
# =========================================
with tabs[4]:
    st.metric("Available Cash", f"${st.session_state.cash:,.2f}")
    st.write("Positions:", st.session_state.positions)

    trade_symbol = st.text_input("Trade Symbol", "SPY", key="trade")
    qty = st.number_input("Quantity", min_value=1, value=10)

    if st.button("Execute Buy"):
        price = yf.Ticker(trade_symbol).history(period="1d")["Close"].iloc[-1]
        cost = price * qty

        if st.session_state.cash >= cost:
            st.session_state.cash -= cost
            st.session_state.positions[trade_symbol] = \
                st.session_state.positions.get(trade_symbol, 0) + qty
            st.success(f"Bought {qty} {trade_symbol} @ {price:.2f}")
        else:
            st.error("Not enough cash.")

# =========================================
# AUTO REFRESH
# =========================================
st.experimental_rerun if False else None
