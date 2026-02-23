import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import pytz
import requests
from bs4 import BeautifulSoup
from finvizfinance.news import News
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm
from streamlit_autorefresh import st_autorefresh
from concurrent.futures import ThreadPoolExecutor, as_completed

# ────────────────────────────────────────────────
#  PAGE CONFIG + SECRETS
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

FINNHUB_KEY = st.secrets.get("FINNHUB_API_KEY", "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog")

# ────────────────────────────────────────────────
#  EXPANDED TICKERS & SECTOR ROTATION FRAMEWORK
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "VIX": "^VIX", "ES": "ES=F", "NQ": "NQ=F", "YM": "YM=F", "RTY": "RTY=F",
    "SPY": "SPY", "QQQ": "QQQ", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
}

SECTOR_ETFS = {
    "🔥 SEMICONDUCTORS": "SMH",
    "☁️ SOFTWARE / CLOUD": "IGV",
    "🖥️ BIG TECH": "QQQ",
    "💰 FINANCIALS": "XLF",
    "🏥 HEALTHCARE": "XLV",
    "🛢️ ENERGY": "XLE",
    "🧱 INDUSTRIALS": "XLI",
    "🛍️ CONSUMER": "XLY",
    "🧪 MATERIALS": "XLB",
    "🪙 CRYPTO / BTC": "BTC-USD"
}

TRADING_THEMES = {
    "🔥 SEMICONDUCTORS (SMH)": ["AVGO", "MU", "TSM", "ARM", "MRVL", "SMCI", "WDC", "STX", "QCOM"],
    "☁️ SOFTWARE / CLOUD (IGV)": ["CRM", "CRWD", "NET", "ORCL", "ADBE", "NOW", "PANW", "PLTR", "MDB", "RBRK"],
    "🖥️ BIG TECH (QQQ)": ["GOOGL", "IBM", "DELL", "SHOP"],
    "💰 FINANCIALS (XLF)": ["GS", "HOOD", "SOFI"],
    "🏥 HEALTHCARE (XLV)": ["UNH", "LLY"],
    "🛢️ ENERGY (XLE)": ["XOM", "OXY"],
    "🧱 INDUSTRIALS": ["BA", "CAT", "FDX"],
    "🛍️ CONSUMER": ["AAL", "LULU", "COST", "KO"],
    "🧪 MATERIALS / METALS": ["ALB", "MP"],
    "🪙 CRYPTO / BTC": ["COIN", "MSTR", "IREN", "CIFR", "IBIT"],
    "⚛️ QUANTUM / SPEC": ["QBTS", "RGTI"],
    "🚀 SPACE / GROWTH": ["RKLB", "ASTS"],
    "⚡ HIGH BETA": ["RIVN"],
    "📈 LEVERAGED": ["TQQQ", "TNA"],
    "🧠 MISC AI / INFRA": ["APP", "ALAB", "OKLO", "BE"]
}

MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN",
                "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}

symbol_to_label = {v: k for d in [GLOBAL_TICKERS, MAG7_TICKERS] for k, v in d.items()}
ALL_SYMBOLS = list(set(list(symbol_to_label.keys()) + 
                       [s for t in TRADING_THEMES.values() for s in t] + 
                       list(SECTOR_ETFS.values()) + ["BTC-USD", "SOXX"]))

ANALYST_SYMBOLS = sorted(list(set([s for t in TRADING_THEMES.values() for s in t])))

# ────────────────────────────────────────────────
#  PARALLEL DATA ENGINE (STABLE)
# ────────────────────────────────────────────────
def fetch_finnhub_quote(sym):
    try:
        f_sym = sym.replace('^', '').split('=')[0] if any(x in sym for x in ['^', '=']) else sym
        if sym == "DX-Y.NYB": f_sym = "DXY"
        r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={f_sym}&token={FINNHUB_KEY}", timeout=6)
        r.raise_for_status()
        return sym, r.json()
    except:
        return sym, None

@st.cache_data(ttl=12)
def fetch_market_snapshot():
    intra = yf.download(ALL_SYMBOLS, period="3d", interval="1m", prepost=True, progress=False, threads=False)
    hist = yf.download(ALL_SYMBOLS, period="15d", interval="1d", progress=False, threads=False)

    with ThreadPoolExecutor(max_workers=30) as executor:
        future_to_sym = {executor.submit(fetch_finnhub_quote, s): s for s in ALL_SYMBOLS}
        finnhub_data = {}
        for future in as_completed(future_to_sym):
            sym, data = future.result()
            finnhub_data[sym] = data

    rows = []
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.datetime.now(tz).strftime('%Y-%m-%d')

    for sym in ALL_SYMBOLS:
        try:
            quote = finnhub_data.get(sym)
            if quote and quote.get('c') and quote['c'] > 0:
                price = float(quote['c'])
                prev_close = float(quote.get('pc') or price)
            else:
                price = float(intra['Close'][sym].dropna().iloc[-1])
                prev_close = float(hist['Close'][sym].dropna().iloc[-2] if len(hist['Close'][sym].dropna()) >= 2 else price)

            change = ((price - prev_close) / prev_close * 100)
            gap = 0.0
            try:
                today_open = intra['Open'][sym].loc[today_str].dropna().iloc[0]
                gap = ((today_open - prev_close) / prev_close * 100)
            except:
                pass

            rvol = 1.0
            try:
                today_vol = intra['Volume'][sym].loc[today_str].sum()
                avg_vol = hist['Volume'][sym].iloc[-15:-2].mean()
                rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            except:
                pass

            rows.append({
                "Asset": symbol_to_label.get(sym, sym),
                "Symbol": sym,
                "Price": round(price, 4 if price < 10 else 2),
                "Gap %": round(gap, 2),
                "Change %": round(change, 2),
                "RVOL": round(rvol, 2)
            })
        except:
            continue

    return pd.DataFrame(rows), intra, hist

# ────────────────────────────────────────────────
#  HELPERS
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
            cv = chain.calls['volume'].sum()
            pv = chain.puts['volume'].sum()
            pcr = pv / cv if cv > 0 else 0
            results.append({"Asset": sym, "PCR": round(pcr, 2),
                            "Sentiment": "🐂 Bull" if pcr < 0.7 else "🐻 Bear" if pcr > 1.1 else "⚖️ Neu"})
        except:
            continue
    return pd.DataFrame(results)

@st.cache_data(ttl=1800)
def get_analyst_ratings():
    ratings = []
    for sym in ANALYST_SYMBOLS[:20]:
        try:
            info = yf.Ticker(sym).info
            ratings.append({
                "Asset": symbol_to_label.get(sym, sym),
                "Consensus": info.get("recommendationKey", "N/A").replace('_', ' ').title(),
                "Target Mean": info.get("targetMeanPrice"),
                "Current": info.get("currentPrice"),
                "Upside %": round(((info.get("targetMeanPrice") or 0) / (info.get("currentPrice") or 1) - 1) * 100, 1)
            })
        except:
            continue
    return pd.DataFrame(ratings)

@st.cache_data(ttl=300)
def get_macro_news():
    try:
        return News().get_news()['news'].head(25).to_dict('records')
    except:
        return []

# ────────────────────────────────────────────────
#  FETCH DATA
# ────────────────────────────────────────────────
market_df, intra_data, hist_data = fetch_market_snapshot()
macro_news = get_macro_news()

# ────────────────────────────────────────────────
#  PREMARKET SECTOR ROTATION CHECKLIST (NEW CORE FEATURE)
# ────────────────────────────────────────────────
def build_premarket_checklist(df):
    if df.empty:
        return "Data loading..."

    tz = pytz.timezone('US/Eastern')
    est_now = datetime.datetime.now(tz).strftime("%H:%M:%S")

    # Macro Bias
    es = df[df['Symbol'] == 'ES=F']['Change %'].iloc[0] if not df[df['Symbol'] == 'ES=F'].empty else 0
    nq = df[df['Symbol'] == 'NQ=F']['Change %'].iloc[0] if not df[df['Symbol'] == 'NQ=F'].empty else 0
    rty = df[df['Symbol'] == 'RTY=F']['Change %'].iloc[0] if not df[df['Symbol'] == 'RTY=F'].empty else 0
    tnx = df[df['Symbol'] == '^TNX']['Change %'].iloc[0] if not df[df['Symbol'] == '^TNX'].empty else 0
    btc = df[df['Symbol'] == 'BTC-USD']['Change %'].iloc[0] if not df[df['Symbol'] == 'BTC-USD'].empty else 0

    # Sector Strength
    sector_perf = {}
    for name, etf in SECTOR_ETFS.items():
        row = df[df['Symbol'] == etf]
        if not row.empty:
            sector_perf[name] = round(row['Change %'].iloc[0], 2)

    strongest = max(sector_perf, key=sector_perf.get) if sector_perf else "N/A"
    strongest_etf = SECTOR_ETFS[strongest]

    # Top Leaders in Strongest Sector
    leaders = df[df['Symbol'].isin(TRADING_THEMES.get(strongest.replace(" (", " ("), []))]
    top_leaders = leaders.nlargest(5, 'Change %')[['Asset', 'Change %', 'Gap %']]

    checklist = f"""
**🕓 PREMARKET CHECKLIST — {est_now} EST**

### STEP 1: MACRO BIAS
- **Futures**: ES {es:+.2f}% | NQ {nq:+.2f}% | RTY {rty:+.2f}%
- **10Y Yield**: {tnx:+.2f}% {'→ Growth Friendly' if tnx < 0 else '→ Pressure on Growth'}
- **BTC**: {btc:+.2f}% {'🟢 Focus Crypto' if btc > 0 else '🔴 Avoid Crypto'}

**Bias**: {'Risk-On → Semis/Tech' if nq > es else 'Defensive → Energy/Healthcare' if rty < 0 else 'Chop → Wait for Open'}

### STEP 2: STRONGEST SECTOR
**{strongest}** (+{sector_perf.get(strongest, 0):+.2f}%) ← **TRADE HERE ONLY**

### STEP 3: LEADERS IN STRONGEST SECTOR
{top_leaders.to_markdown(index=False)}

### STEP 4: ROTATION PLAYBOOK
- Bull Open → Trade **{strongest}** leaders
- Bear Open → Defensive (XLV / XLE)
- Choppy → SPY/QQQ only or sit out first 30 min

**Written Plan**: Only trade leaders in **{strongest}** with volume & structure.
"""
    return checklist

# ────────────────────────────────────────────────
#  UI
# ────────────────────────────────────────────────
st.title("🏛️ Alpha Terminal Pro")
st.caption(f"Last Sync: {datetime.datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')} EST | Live Parallel Engine")

st.markdown("---")

# BATTLE PLAN + CHECKLIST
col_plan, col_vitals = st.columns([2, 1])
with col_plan:
    st.subheader("📝 Morning Battle Plan")
    plan_text = build_premarket_checklist(market_df).split("### STEP 4")[0]  # reuse macro part
    st.info(plan_text)

with col_vitals:
    st.subheader("📡 Vitals")
    vix_val = market_df[market_df['Symbol'] == "^VIX"]['Price'].iloc[0] if not market_df[market_df['Symbol'] == "^VIX"].empty else 20
    vol_pulse = "🔴 High" if vix_val > 22 else "🟢 Low" if vix_val < 15 else "🟡 Med"
    st.metric("Volatility Pulse", vol_pulse)
    top_gap = market_df.nlargest(1, 'Gap %')['Symbol'].iloc[0] if not market_df.empty else "N/A"
    st.metric("Top Gapper", top_gap)

st.sidebar.metric("VIX (Fear Index)", f"{vix_val:.2f}", delta="Risk On" if vix_val < 20 else "Volatility")

# ────────────────────────────────────────────────
#  TABS (New Checklist Tab First)
# ────────────────────────────────────────────────
tabs = st.tabs([
    "🚀 Premarket Rotation Checklist",
    "📊 Market Overview",
    "🎯 Trading Themes",
    "📊 GEX / Gamma",
    "🐳 Options PCR",
    "📊 Analyst Ratings",
    "🔍 Regime + Alpha Delta",
    "💼 Paper Trading"
])

# TAB 0 — NEW CHECKLIST (FULL VERSION)
with tabs[0]:
    st.subheader("🚀 PREMARKET SECTOR ROTATION CHECKLIST")
    st.markdown(build_premarket_checklist(market_df))
    st.caption("Copy this into your notes every morning. Trade **only** the strongest sector leaders.")

# TAB 1
with tabs[1]:
    st.subheader("🗝️ Key Indices & Mag7")
    col1, col2 = st.columns([2, 1])
    with col1:
        indices = market_df[market_df['Symbol'].isin(GLOBAL_TICKERS.values())]
        st.dataframe(indices.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'Gap %']), hide_index=True, use_container_width=True)
    with col2:
        mag7 = market_df[market_df['Symbol'].isin(MAG7_TICKERS.values())].sort_values('Change %', ascending=False)
        st.dataframe(mag7[['Asset', 'Price', 'Change %', 'Gap %']].style.background_gradient(cmap='RdYlGn', subset=['Change %']), hide_index=True, use_container_width=True)

# TAB 2
with tabs[2]:
    cols = st.columns(len(TRADING_THEMES))
    for i, (name, syms) in enumerate(TRADING_THEMES.items()):
        with cols[i % 4]:
            st.markdown(f"**{name}**")
            theme_df = market_df[market_df['Symbol'].isin(syms)]
            st.dataframe(theme_df[['Asset', 'Price', 'Change %']].style.background_gradient(cmap='RdYlGn'), hide_index=True, use_container_width=True)

# TAB 3 — GEX
with tabs[3]:
    user_ticker = st.text_input("GEX Ticker", value="SPY").upper().strip()
    if user_ticker:
        try:
            tk = yf.Ticker(user_ticker)
            spot = tk.history(period="1d")['Close'].iloc[-1]
            exp = tk.options[0]
            c = tk.option_chain(exp).calls.assign(type='call')
            p = tk.option_chain(exp).puts.assign(type='put')
            df_g = pd.concat([c, p])
            df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'], 5/365, df_g['impliedVolatility'], 0.04, 0.01, df_g['type'], df_g['openInterest'])
            fig = px.bar(df_g.groupby('strike')['GEX'].sum().reset_index(), x='strike', y='GEX', title=f"{user_ticker} Gamma Exposure")
            fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text="SPOT")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Options data unavailable: {e}")

# TAB 4 — PCR
with tabs[4]:
    st.subheader("🐳 Put/Call Volume Ratio")
    st.dataframe(get_pcr_data().style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True, use_container_width=True)

# TAB 5 — Analyst
with tabs[5]:
    st.subheader("📊 Analyst Ratings")
    analyst_df = get_analyst_ratings()
    if not analyst_df.empty:
        st.dataframe(analyst_df.style.background_gradient(cmap='RdYlGn', subset=['Upside %']), hide_index=True, use_container_width=True)

# TAB 6 — Regime + Alpha Delta
with tabs[6]:
    st.subheader("🔍 Market Regime Analysis")
    def get_bias(chg):
        if chg > 1.5: return "🚀 Strong Bull"
        if chg < -1.5: return "💥 Strong Bear"
        return "⚖️ Neutral / Chop"
    market_df['Regime'] = market_df['Change %'].apply(get_bias)
    st.dataframe(market_df[['Asset', 'Price', 'Change %', 'Gap %', 'Regime']].style.background_gradient(cmap='RdYlGn', subset=['Change %']), hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("⚖️ Relative Strength vs SPY (Alpha Delta)")
    if not market_df.empty:
        try:
            spy_change = market_df[market_df['Symbol'] == 'SPY']['Change %'].iloc[0]
            rs_data = []
            for theme, symbols in TRADING_THEMES.items():
                for sym in symbols:
                    row = market_df[market_df['Symbol'] == sym]
                    if not row.empty:
                        stock_chg = row['Change %'].iloc[0]
                        rs_data.append({
                            "Theme": theme.split()[0],
                            "Ticker": sym,
                            "Alpha Delta": round(stock_chg - spy_change, 2),
                            "Actual %": round(stock_chg, 2)
                        })
            rs_df = pd.DataFrame(rs_data)
            fig_rs = px.bar(rs_df.sort_values("Alpha Delta", ascending=False), x="Ticker", y="Alpha Delta",
                            color="Alpha Delta", text="Alpha Delta", color_continuous_scale="RdYlGn",
                            title=f"Alpha Delta vs SPY ({spy_change:+.2f}%)")
            fig_rs.add_hline(y=0, line_dash="dash", line_color="white")
            st.plotly_chart(fig_rs, use_container_width=True)

            st.markdown("### 🏆 Top 5 Momentum Leaders")
            top_leaders = rs_df.nlargest(5, "Alpha Delta")
            cols = st.columns(5)
            for idx, leader in enumerate(top_leaders.to_dict('records')):
                with cols[idx]:
                    st.metric(label=leader['Ticker'], value=f"{leader['Actual %']}%", delta=f"{leader['Alpha Delta']}% vs SPY")
        except:
            st.warning("RS data syncing...")

# TAB 7 — Paper Trading
with tabs[7]:
    st.subheader("💼 Paper Trading Simulator")
    if 'cash' not in st.session_state: st.session_state.cash = 100000.0
    if 'portfolio' not in st.session_state: st.session_state.portfolio = {}

    def execute_trade(symbol, qty, price, side):
        cost = qty * price
        if side == "BUY":
            if cost > st.session_state.cash:
                st.error("❌ Insufficient Funds!")
                return
            st.session_state.cash -= cost
            pos = st.session_state.portfolio.get(symbol, {'qty': 0, 'avg_price': 0.0})
            total_qty = pos['qty'] + qty
            new_avg = ((pos['qty'] * pos['avg_price']) + cost) / total_qty if total_qty > 0 else price
            st.session_state.portfolio[symbol] = {'qty': total_qty, 'avg_price': new_avg}
            st.success(f"✅ Bought {qty} {symbol} @ ${price:.2f}")
        else:
            pos = st.session_state.portfolio.get(symbol, {'qty': 0})
            if pos['qty'] < qty:
                st.error("❌ Not enough shares!")
                return
            st.session_state.cash += cost
            st.session_state.portfolio[symbol]['qty'] -= qty
            if st.session_state.portfolio[symbol]['qty'] == 0:
                del st.session_state.portfolio[symbol]
            st.success(f"✅ Sold {qty} {symbol} @ ${price:.2f}")

    total_value = st.session_state.cash
    portfolio_rows = []
    for sym, data in st.session_state.portfolio.items():
        live_row = market_df[market_df['Symbol'] == sym]
        live_price = live_row['Price'].iloc[0] if not live_row.empty else data['avg_price']
        value = data['qty'] * live_price
        pnl = (live_price - data['avg_price']) * data['qty']
        total_value += value
        portfolio_rows.append({
            "Ticker": sym, "Qty": data['qty'], "Avg Price": f"${data['avg_price']:.2f}",
            "Live Price": f"${live_price:.2f}", "P&L $": round(pnl, 2), "P&L %": f"{((live_price/data['avg_price']-1)*100):+.2f}%"
        })

    c1, c2, c3 = st.columns(3)
    c1.metric("Cash", f"${st.session_state.cash:,.2f}")
    c2.metric("Total Equity", f"${total_value:,.2f}", f"{(total_value - 100000):+,.2f}")
    c3.metric("Positions", len(st.session_state.portfolio))

    st.markdown("---")
    t1, t2, t3, t4 = st.columns([2, 1, 1, 1])
    with t1: trade_sym = st.selectbox("Ticker", options=ALL_SYMBOLS, key="trade_sym")
    with t2: trade_qty = st.number_input("Qty", min_value=1, value=10, key="trade_qty")
    curr_price = market_df[market_df['Symbol'] == trade_sym]['Price'].iloc[0] if not market_df[market_df['Symbol'] == trade_sym].empty else 0
    with t3:
        if st.button("BUY", type="primary", use_container_width=True):
            execute_trade(trade_sym, trade_qty, curr_price, "BUY")
            st.rerun()
    with t4:
        if st.button("SELL", use_container_width=True):
            execute_trade(trade_sym, trade_qty, curr_price, "SELL")
            st.rerun()

    if portfolio_rows:
        st.dataframe(pd.DataFrame(portfolio_rows).style.background_gradient(cmap='RdYlGn', subset=['P&L $']), hide_index=True, use_container_width=True)

# ────────────────────────────────────────────────
#  LIVE ALERTS (VWAP + RVOL)
# ────────────────────────────────────────────────
if 'alert_log' not in st.session_state:
    st.session_state.alert_log = []

def trigger_alert(msg, icon="🔔"):
    now = datetime.datetime.now(pytz.timezone('US/Eastern')).strftime("%H:%M:%S")
    alert = f"[{now}] {icon} {msg}"
    st.session_state.alert_log = [alert] + st.session_state.alert_log[:9]

def process_live_alerts(df, intra):
    tz = pytz.timezone('US/Eastern')
    today_str = datetime.datetime.now(tz).strftime('%Y-%m-%d')
    for _, row in df.iterrows():
        sym = row['Symbol']
        price = row['Price']
        try:
            today_data = intra.xs(sym, level=1, axis=1).dropna()
            today_data = today_data[today_data.index.strftime('%Y-%m-%d') == today_str]
            if len(today_data) >= 3:
                v_sum = today_data['Volume'].sum()
                pv_sum = (today_data['Close'] * today_data['Volume']).sum()
                vwap = pv_sum / v_sum if v_sum > 0 else 0
                prev_price = today_data['Close'].iloc[-2]
                if prev_price < vwap and price > vwap:
                    trigger_alert(f"{sym} 🚀 CROSSING ABOVE VWAP @ ${price:.2f}", "🚀")
                elif prev_price > vwap and price < vwap:
                    trigger_alert(f"{sym} ⚠️ SLICING BELOW VWAP @ ${price:.2f}", "⚠️")
        except:
            pass
        if row['RVOL'] > 3.5:
            trigger_alert(f"{sym} 🔥 VOLUME EXPLOSION: {row['RVOL']:.1f}x Avg!", "🔥")

with st.sidebar:
    st.markdown("### 🎰 LIVE TRADE ALERTS")
    process_live_alerts(market_df, intra_data)
    with st.container(height=320, border=True):
        if not st.session_state.alert_log:
            st.caption("Waiting for triggers...")
        for alert in st.session_state.alert_log:
            if "🚀" in alert or "EXPLOSION" in alert:
                st.success(alert)
            elif "⚠️" in alert:
                st.warning(alert)
            else:
                st.info(alert)
    if st.button("Clear Alerts"):
        st.session_state.alert_log = []
        st.rerun()

# ────────────────────────────────────────────────
#  AUTO REFRESH
# ────────────────────────────────────────────────
st_autorefresh(interval=25000, key="live_refresh")
