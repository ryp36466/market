import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
from finvizfinance.news import News
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh

# ────────────────────────────────────────────────
#  1. CONFIGURATION & TICKERS
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# Secure API Key Handling
FINNHUB_KEY = st.secrets.get("FINNHUB_API_KEY", "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog")

GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES (S&P 500 Fut)": "ES=F", "NQ (Nasdaq Fut)": "NQ=F",
    "YM (Dow Fut)": "YM=F", "RTY (Russell 2000)": "RTY=F", "SPY": "SPY", 
    "QQQ": "QQQ", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
}

SECTOR_TICKERS = {
    "Tech (XLK)": "XLK", "Software (IGV)": "IGV", "Semiconductor (SMH)": "SMH",
    "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV",
    "Disc (XLY)": "XLY", "Indus (XLI)": "XLI", "Utils (XLU)": "XLU"
}

TRADING_THEMES = {
    "🔵 SEMICONDUCTORS": ["SMH", "NVDA", "AMD", "AVGO", "TSM", "ARM"],
    "🟣 SOFTWARE / SaaS": ["IGV", "MSFT", "CRM", "NOW", "PLTR", "ORCL"],
    "🟢 NEO CLOUD / AI": ["VRT", "ANET", "SMCI", "DELL", "CRWD"],
    "🟠 CRYPTO / BTC": ["BTC-USD", "MSTR", "COIN", "MARA", "IBIT"],
    "🟤 SMALL CAPS": ["IWM", "TNA", "ASTS", "OKLO"]
}

MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
MAG7_HOT_SYMBOLS = list(MAG7_TICKERS.values()) + ["SPY", "QQQ"]

# Flatten labels for mapping
symbol_to_label = {v: k for d in [GLOBAL_TICKERS, SECTOR_TICKERS, MAG7_TICKERS] for k, v in d.items()}
ALL_SYMBOLS = list(set(list(symbol_to_label.keys()) + [s for t in TRADING_THEMES.values() for s in t]))
ANALYST_SYMBOLS = sorted(list(set([s for t in TRADING_THEMES.values() for s in t])))

# ────────────────────────────────────────────────
#  2. ASYNC DATA ENGINE (Parallel Fetching)
# ────────────────────────────────────────────────

async def fetch_finnhub_quote(session, sym):
    f_sym = sym.replace('^', '').split('=')[0] if any(x in sym for x in ['^', '=']) else sym
    if sym == "DX-Y.NYB": f_sym = "DXY"
    url = f"https://finnhub.io/api/v1/quote?symbol={f_sym}&token={FINNHUB_KEY}"
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                return sym, await response.json()
            return sym, None
    except: return sym, None

async def get_all_quotes(symbols):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_finnhub_quote(session, s) for s in symbols]
        return await asyncio.gather(*tasks)

@st.cache_data(ttl=15)
def fetch_market_snapshot():
    # Batch YFinance for historicals and intraday
    intra = yf.download(ALL_SYMBOLS, period="3d", interval="1m", prepost=True, progress=False)
    hist = yf.download(ALL_SYMBOLS, period="15d", interval="1d", progress=False)
    
    # Run Async Finnhub calls
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    finnhub_data = dict(loop.run_until_complete(get_all_quotes(ALL_SYMBOLS)))
    
    rows = []
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.datetime.now(tz).strftime('%Y-%m-%d')

    for sym in ALL_SYMBOLS:
        try:
            quote = finnhub_data.get(sym)
            if quote and quote.get('c'):
                price, prev_close = quote['c'], quote['pc']
            else:
                price = intra['Close'][sym].dropna().iloc[-1]
                prev_close = hist['Close'][sym].dropna().iloc[-2]
            
            change = ((price - prev_close) / prev_close * 100)
            
            # Gap Logic
            try:
                today_open = intra['Open'][sym].loc[today_str].dropna().iloc[0]
                gap = ((today_open - prev_close) / prev_close * 100)
            except: gap = 0.0

            # RVOL Logic
            try:
                today_vol = intra['Volume'][sym].loc[today_str].sum()
                avg_vol = hist['Volume'][sym].iloc[-15:-2].mean()
                rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            except: rvol = 1.0

            rows.append({
                "Asset": symbol_to_label.get(sym, sym), "Symbol": sym, "Price": price,
                "Gap %": gap, "Change %": change, "RVOL": rvol
            })
        except: continue
    return pd.DataFrame(rows), intra, hist

# ────────────────────────────────────────────────
#  3. ANALYTICS & MATH
# ────────────────────────────────────────────────

def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365.0)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = gamma * OI * 100 * S
    return np.where(types == 'call', val, -val)

@st.cache_data(ttl=600)
def get_pcr_data():
    results = []
    for sym in ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"]:
        try:
            tk = yf.Ticker(sym)
            chain = tk.option_chain(tk.options[0])
            pcr = chain.puts['volume'].sum() / chain.calls['volume'].sum()
            results.append({"Asset": sym, "PCR": round(pcr, 2), "Sentiment": "🐂 Bull" if pcr < 0.7 else "🐻 Bear" if pcr > 1.1 else "⚖️ Neu"})
        except: continue
    return pd.DataFrame(results)

@st.cache_data(ttl=1800)
def get_analyst_ratings():
    ratings = []
    for sym in ANALYST_SYMBOLS[:15]: # Limit to top 15 for speed
        try:
            info = yf.Ticker(sym).info
            ratings.append({
                "Asset": symbol_to_label.get(sym, sym), "Consensus": info.get("recommendationKey", "N/A").replace('_', ' ').title(),
                "Target Mean": info.get("targetMeanPrice"), "Current": info.get("currentPrice"),
                "Upside %": ((info.get("targetMeanPrice", 0) / info.get("currentPrice", 1)) - 1) * 100
            })
        except: continue
    return pd.DataFrame(ratings)

# ────────────────────────────────────────────────
#  4. UI LAYOUT
# ────────────────────────────────────────────────
# ────────────────────────────────────────────────
#  MORNING BATTLE PLAN (Strategic Summary)
# ────────────────────────────────────────────────

def generate_battle_plan(df, macro_news):
    # 1. Identify Market Pulse
    spy_row = df[df['Symbol'] == 'SPY']
    vix_row = df[df['Symbol'] == '^VIX']
    
    spy_chg = spy_row['Change %'].values[0] if not spy_row.empty else 0
    vix_val = vix_row['Price'].values[0] if not vix_row.empty else 20
    
    # 2. Identify Top Gappers (Alpha)
    top_gappers = df.sort_values('Gap %', ascending=False).head(3)
    gap_names = ", ".join(top_gappers['Symbol'].tolist())
    
    # 3. Macro Sentiment (Heuristic)
    macro_titles = " ".join([item.get('Title', '').lower() for item in macro_news[:5]])
    is_fed = "fed" in macro_titles or "inflation" in macro_titles
    is_geo = "tariff" in macro_titles or "war" in macro_titles or "china" in macro_titles
    
    # 4. Synthesize logic
    # Sentence 1: Market State
    if spy_chg > 0.5: mood = "The market is showing strong **Risk-On** appetite with a gap up."
    elif spy_chg < -0.5: mood = "The market is in **Defensive Mode** with significant selling pressure."
    else: mood = "We are looking at a **Neutral/Chop Open** with low directional conviction."
    
    # Sentence 2: The Catalyst
    if is_fed: catalyst = "Macro focus is centered on **Central Bank policy** and inflation data."
    elif is_geo: catalyst = "Geopolitical headlines and **trade tensions** are driving the narrative."
    else: catalyst = "Action is largely **Sector-Specific**, driven by earnings and individual catalysts."
    
    # Sentence 3: Tactical Execution
    if vix_val > 25: tactic = "High Volatility detected. **Tighten stops** and avoid oversized positions."
    elif not top_gappers.empty and top_gappers['Gap %'].iloc[0] > 2: 
        tactic = f"Watch **{gap_names}** for a 'Gap & Go' setup if opening ranges hold."
    else: tactic = "Patience is key; wait for the 15-minute opening range to define the day's trend."

    return f"{mood} {catalyst} {tactic}"

# ────────────────────────────────────────────────
#  UI: BATTLE PLAN BOX
# ────────────────────────────────────────────────

# Place this right under your Title/Header
st.markdown("---")
with st.container():
    col_plan, col_vitals = st.columns([3, 1])
    
    with col_plan:
        st.subheader("📝 Morning Battle Plan")
        plan_text = generate_battle_plan(market_df, macro_news if 'macro_news' in locals() else [])
        st.info(plan_text)
        
    with col_vitals:
        st.subheader("📡 Vitals")
        vol_pulse = "🔴 High" if vix_val > 22 else "🟢 Low" if vix_val < 15 else "🟡 Med"
        st.write(f"**Volatility Pulse:** {vol_pulse}")
        st.write(f"**Top Gapper:** {top_gappers['Symbol'].iloc[0] if not top_gappers.empty else 'N/A'}")


market_df, intra_data, hist_data = fetch_market_snapshot()
st.title("🏛️ Alpha Terminal Pro")
st.caption(f"Last Sync: {datetime.datetime.now().strftime('%H:%M:%S')} EST | Parallel Engine Active")

# Sidebar Metrics
if not market_df.empty:
    vix_val = market_df[market_df['Symbol'] == "^VIX"]['Price'].values[0]
    st.sidebar.metric("VIX (Fear Index)", f"{vix_val:.2f}", delta="- Risk On" if vix_val < 20 else "+ Volatility")

tabs = st.tabs(["📊 Market Overview", "🎯 Themes", "📊 GEX / Gamma", "🐳 Options", "📊 Analyst Ratings", "🔍 Regime Bias"])

with tabs[0]:
    st.subheader("🗝️ Key Indices & Mag7")
    col1, col2 = st.columns([2, 1])
    
    indices = market_df[market_df['Symbol'].isin(GLOBAL_TICKERS.values())]
    col1.dataframe(indices.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'Gap %']), hide_index=True, use_container_width=True)
    
    mag7 = market_df[market_df['Symbol'].isin(MAG7_TICKERS.values())].sort_values('Change %', ascending=False)
    col2.dataframe(mag7[['Asset', 'Change %']].style.background_gradient(cmap='RdYlGn'), hide_index=True, use_container_width=True)

with tabs[1]:
    cols = st.columns(len(TRADING_THEMES))
    for i, (name, syms) in enumerate(TRADING_THEMES.items()):
        with cols[i]:
            st.markdown(f"**{name}**")
            theme_df = market_df[market_df['Symbol'].isin(syms)]
            st.dataframe(theme_df[['Asset', 'Change %']].style.background_gradient(cmap='RdYlGn'), hide_index=True)

with tabs[2]:
    user_ticker = st.text_input("GEX Lookup", value="SPY").upper()
    try:
        tk = yf.Ticker(user_ticker)
        spot = tk.history(period="1d")['Close'].iloc[-1]
        exp = tk.options[0]
        c = tk.option_chain(exp).calls.assign(type='call')
        p = tk.option_chain(exp).puts.assign(type='put')
        df_g = pd.concat([c, p])
        df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'], 5/365, df_g['impliedVolatility'], 0.04, 0.01, df_g['type'], df_g['openInterest'])
        
        fig = px.bar(df_g.groupby('strike')['GEX'].sum().reset_index(), x='strike', y='GEX', title=f"{user_ticker} Gamma Profile")
        fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text="SPOT")
        st.plotly_chart(fig, use_container_width=True)
    except: st.error("Options data unavailable for this ticker.")

with tabs[3]:
    st.dataframe(get_pcr_data(), use_container_width=True, hide_index=True)

with tabs[4]:
    st.dataframe(get_analyst_ratings().style.background_gradient(cmap='RdYlGn', subset=['Upside %']), use_container_width=True, hide_index=True)

with tabs[5]:
    st.subheader("🔍 Market Regime Analysis")
    def get_bias(row):
        if row['Change %'] > 1.5: return "🚀 Strong Bull"
        if row['Change %'] < -1.5: return "💥 Strong Bear"
        return "⚖️ Neutral / Chop"
    
    market_df['Regime'] = market_df.apply(get_bias, axis=1)
    st.dataframe(market_df[['Asset', 'Change %', 'Regime']].style.map(
        lambda x: 'background-color: #004400' if 'Bull' in str(x) else ('background-color: #440000' if 'Bear' in str(x) else ''),
        subset=['Regime']
    ), hide_index=True, use_container_width=True)

# Auto-refresh: 30 seconds
st_autorefresh(interval=30000, key="data_refresh")

# ────────────────────────────────────────────────
#  RELATIVE STRENGTH HEATMAP LOGIC
# ────────────────────────────────────────────────

with tabs[5]: # Or add a 6th tab: "⚖️ Leaderboard"
    st.subheader("⚖️ Relative Strength vs SPY (Alpha Delta)")
    st.caption("Shows which stocks are outperforming the benchmark. Green = Leading | Red = Lagging")

    if not market_df.empty:
        try:
            # 1. Get the Benchmark Performance
            spy_change = market_df[market_df['Symbol'] == 'SPY']['Change %'].values[0]
            
            # 2. Build the RS Dataset
            rs_data = []
            for theme, symbols in TRADING_THEMES.items():
                for sym in symbols:
                    row = market_df[market_df['Symbol'] == sym]
                    if not row.empty:
                        stock_chg = row['Change %'].values[0]
                        rs_data.append({
                            "Theme": theme.split()[-1], # Shorten name
                            "Ticker": sym,
                            "Alpha Delta": round(stock_chg - spy_change, 2),
                            "Actual %": round(stock_chg, 2)
                        })
            
            rs_df = pd.DataFrame(rs_data)

            # 3. Create the Heatmap Matrix
            # We pivot the data so Themes are columns and Tickers are rows
            # Since themes have different stocks, we'll use a Bar chart for better clarity 
            # or a specialized Plotly Heatmap
            
            fig_rs = px.bar(
                rs_df.sort_values("Alpha Delta", ascending=False),
                x="Ticker",
                y="Alpha Delta",
                color="Alpha Delta",
                text="Alpha Delta",
                color_continuous_scale="RdYlGn",
                range_color=[-3, 3], # Caps the intensity at +/- 3% relative strength
                template="plotly_dark",
                title=f"Alpha Delta (Stock % minus SPY {spy_change:+.2f}%)"
            )
            
            fig_rs.update_traces(textposition='outside')
            fig_rs.add_hline(y=0, line_dash="dash", line_color="white")
            st.plotly_chart(fig_rs, use_container_width=True)

            # 4. The "Top 5 Alpha" Leaders
            st.markdown("### 🏆 Top 5 Momentum Leaders")
            top_leaders = rs_df.sort_values("Alpha Delta", ascending=False).head(5)
            
            cols = st.columns(5)
            for idx, leader in enumerate(top_leaders.to_dict('records')):
                with cols[idx]:
                    st.metric(
                        label=leader['Ticker'],
                        value=f"{leader['Actual %']}%",
                        delta=f"{leader['Alpha Delta']}% vs SPY"
                    )
        except Exception as e:
            st.warning(f"Waiting for SPY data to sync... {e}")

# ────────────────────────────────────────────────
#  ALERTS ENGINE (Vegas Style)
# ────────────────────────────────────────────────

# 1. Initialize Alert History in Session State
if 'alert_log' not in st.session_state:
    st.session_state.alert_log = []

def trigger_alert(msg, icon="🔔"):
    """Adds a timestamped alert to the log."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    alert = f"[{now}] {icon} {msg}"
    # Keep only the last 10 alerts
    st.session_state.alert_log = [alert] + st.session_state.alert_log[:9]

def process_live_alerts(df, intra):
    """Checks for technical triggers: VWAP Cross & 52-Week Highs."""
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.datetime.now(tz).strftime('%Y-%m-%d')
    
    for _, row in df.iterrows():
        sym = row['Symbol']
        price = row['Price']
        
        # --- A. VWAP CROSSOVER CALCULATION ---
        try:
            # Filter today's 1m candles
            today_data = intra.xs(sym, level=1, axis=1).dropna()
            today_data = today_data[today_data.index.strftime('%Y-%m-%d') == today_str]
            
            if not today_data.empty:
                # Calculate Cumulative VWAP: sum(P*V) / sum(V)
                v_sum = today_data['Volume'].sum()
                pv_sum = (today_data['Close'] * today_data['Volume']).sum()
                vwap = pv_sum / v_sum if v_sum > 0 else 0
                
                # Detect Crossover (Price was below VWAP 2 mins ago, now above)
                if len(today_data) >= 3:
                    prev_price = today_data['Close'].iloc[-2]
                    if prev_price < vwap and price > vwap:
                        trigger_alert(f"{sym} CRITICAL: Crossing ABOVE VWAP @ ${price:.2f}", "🚀")
                    elif prev_price > vwap and price < vwap:
                        trigger_alert(f"{sym} WARNING: Slicing BELOW VWAP @ ${price:.2f}", "⚠️")
        except: continue

        # --- B. UNUSUAL VOLUME SPARK ---
        if row['RVOL'] > 3.5:
            trigger_alert(f"{sym} VOLUME EXPLOSION: {row['RVOL']}x Avg Vol!", "🔥")

# ────────────────────────────────────────────────
#  UI: THE ALERT TERMINAL
# ────────────────────────────────────────────────

# Place this above your Tabs or in a Sidebar
with st.sidebar:
    st.markdown("### 🎰 LIVE TRADE ALERTS")
    # Run the processor
    process_live_alerts(market_df, intra_data)
    
    # Display the "Vegas" Log
    with st.container(height=300, border=True):
        if not st.session_state.alert_log:
            st.caption("Waiting for market triggers...")
        for alert in st.session_state.alert_log:
            if "CRITICAL" in alert or "EXPLOSION" in alert:
                st.write(f"**:green[{alert}]**")
            elif "WARNING" in alert:
                st.write(f"**:red[{alert}]**")
            else:
                st.write(alert)

    if st.button("Clear Log"):
        st.session_state.alert_log = []
        st.rerun()


# ────────────────────────────────────────────────
#  PAPER TRADING ENGINE (The Simulator)
# ────────────────────────────────────────────────

# 1. Initialize Portfolio
if 'cash' not in st.session_state:
    st.session_state.cash = 100000.0  # Start with $100k
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {}  # { 'AAPL': {'qty': 10, 'avg_price': 150.0} }

def execute_trade(symbol, qty, price, side):
    """Handles the math for buying and selling."""
    cost = qty * price
    if side == "BUY":
        if cost > st.session_state.cash:
            st.error("❌ Insufficient Funds!")
            return
        st.session_state.cash -= cost
        # Update Position
        pos = st.session_state.portfolio.get(symbol, {'qty': 0, 'avg_price': 0.0})
        total_qty = pos['qty'] + qty
        new_avg = ((pos['qty'] * pos['avg_price']) + cost) / total_qty
        st.session_state.portfolio[symbol] = {'qty': total_qty, 'avg_price': new_avg}
        st.toast(f"Bought {qty} {symbol} at ${price:.2f}")
        
    elif side == "SELL":
        pos = st.session_state.portfolio.get(symbol, {'qty': 0})
        if pos['qty'] < qty:
            st.error("❌ You don't own enough shares!")
            return
        st.session_state.cash += cost
        st.session_state.portfolio[symbol]['qty'] -= qty
        if st.session_state.portfolio[symbol]['qty'] == 0:
            del st.session_state.portfolio[symbol]
        st.toast(f"Sold {qty} {symbol} at ${price:.2f}")

# ────────────────────────────────────────────────
#  UI: PORTFOLIO DASHBOARD
# ────────────────────────────────────────────────

with tabs[6]:  # New Tab
    st.subheader("💼 Paper Trading Simulator")
    
    # --- Top Stats ---
    # Calculate Total Portfolio Value
    current_positions_value = 0
    portfolio_rows = []
    
    for sym, data in st.session_state.portfolio.items():
        # Get live price from our market_df
        live_price_row = market_df[market_df['Symbol'] == sym]
        live_price = live_price_row['Price'].values[0] if not live_price_row.empty else data['avg_price']
        
        value = data['qty'] * live_price
        pnl = (live_price - data['avg_price']) * data['qty']
        pnl_pct = ((live_price / data['avg_price']) - 1) * 100
        
        current_positions_value += value
        portfolio_rows.append({
            "Ticker": sym, "Qty": data['qty'], "Avg Price": f"${data['avg_price']:.2f}",
            "Live Price": f"${live_price:.2f}", "P&L $": round(pnl, 2), "P&L %": f"{pnl_pct:+.2f}%"
        })

    total_account_value = st.session_state.cash + current_positions_value
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Cash Balance", f"${st.session_state.cash:,.2f}")
    c2.metric("Total Equity", f"${total_account_value:,.2f}", 
              delta=f"{(total_account_value - 100000):+,.2f} Total P&L")
    c3.metric("Open Positions", len(st.session_state.portfolio))

    # --- Trade Entry ---
    st.markdown("---")
    t_col1, t_col2, t_col3, t_col4 = st.columns([2, 1, 1, 1])
    
    with t_col1:
        trade_sym = st.selectbox("Select Ticker", options=ALL_SYMBOLS)
    with t_col2:
        trade_qty = st.number_input("Quantity", min_value=1, value=10)
    
    # Get current price for UI
    curr_p = market_df[market_df['Symbol'] == trade_sym]['Price'].values[0] if not market_df[market_df['Symbol'] == trade_sym].empty else 0
    
    with t_col3:
        if st.button("BUY", use_container_width=True, type="primary"):
            execute_trade(trade_sym, trade_qty, curr_p, "BUY")
            st.rerun()
    with t_col4:
        if st.button("SELL", use_container_width=True):
            execute_trade(trade_sym, trade_qty, curr_p, "SELL")
            st.rerun()

    # --- Open Positions Table ---
    if portfolio_rows:
        st.write("### Active Positions")
        pdf = pd.DataFrame(portfolio_rows)
        st.dataframe(pdf.style.background_gradient(cmap='RdYlGn', subset=['P&L $']), hide_index=True, use_container_width=True)
    else:
        st.info("No active positions. Execute a trade above to begin.")
