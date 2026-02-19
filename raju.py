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

# ========================== HELPER FUNCTIONS ==========================
def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return np.where(types == 'call', val, -val)

def fetch_pcr_single(item):
    label, sym = item
    try:
        tk = yf.Ticker(sym)
        cv = pv = 0
        opts = tk.options
        if not opts: return None
        for exp in opts[:2]:
            ch = tk.option_chain(exp)
            cv += ch.calls['volume'].sum()
            pv += ch.puts['volume'].sum()
        pcr = pv / cv if cv > 0 else 0
        return {"Asset": label, "PCR": pcr, "Sentiment": "🐂 Bull" if pcr < 0.85 else "Bear" if pcr > 1.15 else "⚖️ Neu"}
    except: return None

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
def get_atr_data(symbol):
    try:
        data = yf.download(symbol, period="5d", interval="5m", progress=False)
        high_low = data['High'] - data['Low']
        high_cp = np.abs(data['High'] - data['Close'].shift())
        low_cp = np.abs(data['Low'] - data['Close'].shift())
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        return atr
    except: return 0

# ========================== SIDEBAR: RISK MGMT ==========================
with st.sidebar:
    st.header("🧮 Trade Planning")
    acc_size = st.number_input("Account ($)", 1000, 1000000, 50000)
    risk_pct = st.slider("Risk (%)", 0.25, 5.0, 1.0, 0.25)
    
    ticker_focus = st.selectbox("ATR Reference", list(MAG7_TICKERS.keys()))
    atr_val = get_atr_data(MAG7_TICKERS[ticker_focus])
    st.write(f"5m ATR: **{atr_val:.2f}**")
    
    entry = st.number_input("Entry Price", 0.0, 100000.0, 0.0)
    if st.button("Suggest Stop (2x ATR)"):
        st.session_state.stop_val = entry - (2 * atr_val)
    
    stop = st.number_input("Stop Price", 0.0, 100000.0, st.session_state.get('stop_val', 0.0))
    
    if entry > 0 and stop > 0 and entry != stop:
        risk_per_sh = abs(entry - stop)
        pos_size = (acc_size * (risk_pct/100)) / risk_per_sh
        st.success(f"Size: **{int(pos_size)} Shares**")
        st.warning(f"Total Risk: ${(acc_size * (risk_pct/100)):.2f}")
    
    st.divider()
    refresh = st.number_input('Refresh (s)', 15, 600, 30, step=15)
    st_autorefresh(interval=refresh * 1000, key="auto_refresh")

# ========================== MAIN UI ==========================
market_df = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Market Terminal")
st.caption(f"EST {time_now} | Pro Strategy Feed")

# Top Metrics Ribbon
m_cols = st.columns(len(GLOBAL_TICKERS))
for i, (label, sym) in enumerate(GLOBAL_TICKERS.items()):
    row = market_df[market_df['Asset'] == label]
    if not row.empty:
        r = row.iloc[0]
        m_cols[i].metric(label, f"{r['Price']:.2f}", f"{r['Change %']:+.2f}%")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["🔥 Alpha Sectors", "📊 GEX & Gamma", "🐳 Options Flow", "🎯 Institutional"])

with tab1:
    sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    spy_chg = market_df[market_df['Symbol'] == 'SPY']['Change %'].values[0] if 'SPY' in market_df['Symbol'].values else 0
    sect_data['RS'] = sect_data['Change %'] - spy_chg
    
    fig = px.bar(sect_data.sort_values('RS'), x='RS', y='Asset', orientation='h',
                 color='RS', color_continuous_scale='RdYlGn', 
                 title="Relative Strength vs SPY")
    fig.update_layout(template="plotly_dark", height=450)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    gex_ticker = st.selectbox("GEX Analysis", ["SPY", "QQQ", "NVDA", "AAPL", "TSLA"])
    tk = yf.Ticker(gex_ticker)
    spot = tk.history(period="1d")['Close'].iloc[-1]
    
    all_chains = []
    for exp in tk.options[:2]:
        try:
            ch = tk.option_chain(exp)
            c, p = ch.calls, ch.puts
            c['type'], p['type'], c['exp'], p['exp'] = 'call', 'put', exp, exp
            all_chains.extend([c, p])
        except: continue
    
    if all_chains:
        df_g = pd.concat(all_chains)
        df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365
        df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'].values, df_g['dte'].values,
                                            df_g['impliedVolatility'].values, 0.04, 0.01,
                                            df_g['type'].values, df_g['openInterest'].values)
        
        df_agg = df_g.groupby('strike')['GEX'].sum() / 1e6
        fig_gex = go.Figure()
        fig_gex.add_trace(go.Bar(x=df_agg.index, y=df_agg.values, 
                                 marker_color=['green' if x > 0 else 'red' for x in df_agg.values]))
        fig_gex.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text="Spot")
        fig_gex.update_layout(template="plotly_dark", title=f"{gex_ticker} Net Gamma Walls")
        st.plotly_chart(fig_gex, use_container_width=True)

with tab3:
    st.subheader("Put/Call Ratio (Front Expirations)")
    targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ"}
    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(fetch_pcr_single, targets.items()))
    pcr_df = pd.DataFrame([r for r in res if r])
    st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True)

with tab4:
    target_analyst = st.selectbox("Analyst Focus", list(MAG7_TICKERS.keys()))
    recs = yf.Ticker(MAG7_TICKERS[target_analyst]).recommendations
    if recs is not None and not recs.empty:
        filtered = recs[recs['Firm'].str.contains('|'.join(TIER_1_BANKS), case=False, na=False)].tail(10)
        st.table(filtered[['Firm', 'To Grade', 'Action']])
