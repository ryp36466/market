import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
from finvizfinance.news import News
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from scipy.stats import norm
from concurrent.futures import ThreadPoolExecutor

# ========================== PAGE CONFIG ==========================
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ========================== PASSWORD PROTECTION ==========================
def check_password():
    if st.session_state.get("password_correct"): return True
    def password_entered():
        if st.session_state["password"] == "Pratimap9!@":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else: st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.title("🔐 Pro Market Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Access Denied")
        return False
    return True

if not check_password(): st.stop()

# ========================== TICKER CONFIGS ==========================
GLOBAL_TICKERS = {"S&P 500 (ES)": "ES=F", "Nasdaq (NQ)": "NQ=F", "Dow (YM)": "YM=F", "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "10Y Yield": "^TNX", "DXY": "DX-Y.NYB"}
SECTOR_TICKERS = {"Tech (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV", "Disc (XLY)": "XLY", "Indus (XLI)": "XLI", "Utils (XLU)": "XLU", "RE": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"}
MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **MAG7_TICKERS}
TIER_1_BANKS = ["Goldman Sachs", "Morgan Stanley", "JPMorgan", "Bank of America", "Citigroup", "Barclays", "UBS", "Wells Fargo", "Deutsche Bank"]

# ========================== MATH & CALCULATIONS ==========================
def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return np.where(types == 'call', val, -val)

# ========================== DATA ENGINE ==========================
@st.cache_data(ttl=45)
def fetch_market_snapshot():
    symbols = list(ALL_TICKERS.values())
    data = yf.download(symbols, period="2d", interval="5m", prepost=True, group_by='ticker', progress=False)
    rows = []
    for label, sym in ALL_TICKERS.items():
        try:
            subset = data[sym].dropna()
            price = subset['Close'].iloc[-1]
            prev_close = subset['Close'].iloc[0] 
            change = ((price - prev_close) / prev_close) * 100
            rows.append({"Asset": label, "Symbol": sym, "Price": price, "Change %": change})
        except: continue
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def get_volume_profile(symbol, bins=50):
    try:
        data = yf.download(symbol, period="1d", interval="5m", progress=False)
        if data.empty: return None
        # Bin volume by price
        price_range = np.linspace(data['Low'].min(), data['High'].max(), bins)
        volume_profile = data.groupby(pd.cut(data['Close'], bins=price_range))['Volume'].sum()
        return volume_profile
    except: return None

# ========================== SIDEBAR: RISK MGMT ==========================
with st.sidebar:
    st.header("🧮 Trade Planning")
    acc_size = st.number_input("Account ($)", 1000, 1000000, 50000)
    risk_pct = st.slider("Risk (%)", 0.25, 5.0, 1.0, 0.25)
    entry = st.number_input("Entry", 0.0, 100000.0, 0.0)
    stop = st.number_input("Stop", 0.0, 100000.0, 0.0)
    target = st.number_input("Target", 0.0, 100000.0, 0.0)
    
    if entry > 0 and stop > 0 and entry != stop:
        risk_per_sh = abs(entry - stop)
        pos_size = (acc_size * (risk_pct/100)) / risk_per_sh
        st.success(f"Size: **{int(pos_size)} Shares**")
        if target > 0:
            rr = abs(target - entry) / risk_per_sh
            st.info(f"R/R Ratio: **{rr:.2f}**")
    
    st.divider()
    refresh = st.sidebar.number_input('Refresh (s)', 15, 600, 30, step=15)
    st_autorefresh(interval=refresh * 1000, key="auto_refresh")

# ========================== MAIN UI ==========================
market_df = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Market Terminal")
st.caption(f"EST {time_now} | Mode: High-Frequency Day Trading")

# Top Metrics Ribbon
m_cols = st.columns(len(GLOBAL_TICKERS))
for i, (label, sym) in enumerate(GLOBAL_TICKERS.items()):
    row = market_df[market_df['Asset'] == label]
    if not row.empty:
        r = row.iloc[0]
        m_cols[i].metric(label, f"{r['Price']:.2f}", f"{r['Change %']:+.2f}%")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["🔥 Alpha Sectors", "📊 GEX & Volume Profile", "🐳 Options Flow", "🎯 Institutional"])

with tab1:
    sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    spy_chg = market_df[market_df['Symbol'] == 'SPY']['Change %'].values[0] if 'SPY' in market_df['Symbol'].values else 0
    sect_data['RS'] = sect_data['Change %'] - spy_chg
    
    fig = px.bar(sect_data.sort_values('RS'), x='RS', y='Asset', orientation='h',
                 color='RS', color_continuous_scale='RdYlGn', 
                 title="Relative Strength vs SPY (Real-time Alpha)")
    fig.update_layout(template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    ticker = st.selectbox("Symbol Analysis", ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"])
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("Gamma Exposure (GEX)")
        tk = yf.Ticker(ticker)
        spot = tk.history(period="1d")['Close'].iloc[-1]
        
        # Optimized GEX Logic
        all_opts = []
        for exp in tk.options[:2]:
            ch = tk.option_chain(exp)
            c, p = ch.calls, ch.puts
            c['type'], p['type'], c['exp'], p['exp'] = 'call', 'put', exp, exp
            all_opts.extend([c, p])
        
        df_g = pd.concat(all_opts)
        df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365
        df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'].values, df_g['dte'].values,
                                            df_g['impliedVolatility'].values, 0.04, 0.01,
                                            df_g['type'].values, df_g['openInterest'].values)
        
        df_agg = df_g.groupby('strike')['GEX'].sum() / 1e6
        fig_gex = go.Figure()
        fig_gex.add_trace(go.Bar(x=df_agg.index, y=df_agg.values, 
                                 marker_color=['green' if x > 0 else 'red' for x in df_agg.values]))
        fig_gex.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text=f"Spot: {spot:.2f}")
        fig_gex.update_layout(template="plotly_dark", title=f"{ticker} Net Gamma Walls")
        st.plotly_chart(fig_gex, use_container_width=True)

    with c2:
        st.subheader("Intraday Volume Profile")
        v_prof = get_volume_profile(ticker)
        if v_prof is not None:
            # Convert Interval Index to strings for display
            v_prof.index = v_prof.index.map(lambda x: f"{x.mid:.2f}")
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(y=v_prof.index, x=v_prof.values, orientation='h', marker_color='cyan'))
            fig_vol.update_layout(template="plotly_dark", title=f"{ticker} Volume by Price (Today)")
            st.plotly_chart(fig_vol, use_container_width=True)
        else: st.info("Volume data unavailable for this ticker.")

with tab3:
    with st.spinner("Fetching Options PCR..."):
        pcr_data = []
        targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ"}
        with ThreadPoolExecutor(max_workers=5) as ex:
            # Reusing fetch_pcr_single logic
            res = list(ex.map(lambda x: fetch_pcr_single(*x), targets.items()))
            pcr_df = pd.DataFrame([r for r in res if r])
        st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True)

with tab4:
    target_analyst = st.selectbox("Analyst Focus", list(MAG7_TICKERS.keys()))
    recs = yf.Ticker(MAG7_TICKERS[target_analyst]).recommendations
    if recs is not None and not recs.empty:
        filtered = recs[recs['Firm'].str.contains('|'.join(TIER_1_BANKS), case=False, na=False)].tail(10)
        st.table(filtered[['Firm', 'To Grade', 'Action']])
    else: st.write("No recent Tier 1 updates.")
