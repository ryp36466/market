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

# ========================== SENTIMENT ENGINE ==========================
def get_sentiment_score(text):
    """Simple keyword-based sentiment analysis for financial headlines."""
    bull_words = ['upbeat', 'growth', 'surge', 'rally', 'beat', 'buy', 'bullish', 'expansion', 'profit', 'gain', 'positive']
    bear_words = ['slump', 'drop', 'fall', 'miss', 'sell', 'bearish', 'contraction', 'loss', 'negative', 'inflation', 'fear', 'risk']
    
    score = 0
    text = text.lower()
    for word in bull_words:
        if word in text: score += 1
    for word in bear_words:
        if word in text: score -= 1
        
    if score > 0: return "🟢 Bullish", score
    if score < 0: return "🔴 Bearish", score
    return "⚪ Neutral", 0

# ========================== DATA HELPERS ==========================
def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365)
    v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return np.where(types == 'call', val, -val)

@st.cache_data(ttl=45)
def fetch_market_snapshot():
    symbols = list(ALL_TICKERS.values())
    data = yf.download(symbols, period="5d", interval="1d", progress=False)
    intra = yf.download(symbols, period="1d", interval="5m", prepost=True, progress=False)
    
    rows = []
    for label, sym in ALL_TICKERS.items():
        try:
            price = intra['Close'][sym].dropna().iloc[-1]
            prev_close = data['Close'][sym].iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            today_vol = intra['Volume'][sym].sum()
            avg_vol = data['Volume'][sym].iloc[-5:-1].mean()
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            
            rows.append({"Asset": label, "Symbol": sym, "Price": price, "Change %": change, "RVOL": rvol})
        except: continue
    return pd.DataFrame(rows)

# ========================== MAIN UI ==========================
market_df = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Intelligence Feed")

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔥 Alpha Sectors", "📊 GEX", "🐳 Options", "🎯 Institutional", "📰 News & Sentiment"])

with tab1:
    sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    st.dataframe(sect_data[['Asset', 'Price', 'Change %', 'RVOL']].style.background_gradient(cmap='RdYlGn'), hide_index=True)

with tab5:
    st.subheader("🔥 Live News & Sentiment Pulse")
    try:
        f_news = News().get_news()
        headlines = f_news['news'][:25]
        
        total_sentiment = 0
        news_rows = []
        
        for item in headlines:
            label, score = get_sentiment_score(item['Title'])
            total_sentiment += score
            news_rows.append({
                "Time": item.get('Date', 'Live'),
                "Headline": item['Title'],
                "Sentiment": label,
                "Source": item['Source'],
                "URL": item['URL']
            })
        
        # Sentiment Meter
        pulse_col, meter_col = st.columns([1, 2])
        with pulse_col:
            pulse_color = "green" if total_sentiment > 0 else "red" if total_sentiment < 0 else "white"
            st.metric("Market Pulse Score", total_sentiment, delta=total_sentiment)
            st.write(f"Aggregate bias is currently **{pulse_color.upper()}**.")
            
        # Display News
        st.divider()
        for res in news_rows:
            with st.expander(f"{res['Sentiment']} | {res['Headline']}"):
                st.write(f"**Source:** {res['Source']} | **Time:** {res['Time']}")
                st.write(f"[Read Full Article]({res['URL']})")
                
    except Exception as e:
        st.error("Could not load news feed.")

# (Keep your existing Tab 2, 3, 4 logic below this point)
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
    st.subheader("Institutional Put/Call Flow")
    targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ"}
    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(fetch_pcr_single, targets.items()))
    pcr_df = pd.DataFrame([r for r in res if r])
    st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True, use_container_width=True)

# ========================== UPDATED DATA ENGINE (With Earnings) ==========================
@st.cache_data(ttl=45)
def fetch_market_snapshot():
    symbols = list(ALL_TICKERS.values())
    data = yf.download(symbols, period="5d", interval="1d", progress=False)
    intra = yf.download(symbols, period="1d", interval="5m", prepost=True, progress=False)
    
    rows = []
    for label, sym in ALL_TICKERS.items():
        try:
            price = intra['Close'][sym].dropna().iloc[-1]
            prev_close = data['Close'][sym].iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            
            today_vol = intra['Volume'][sym].sum()
            avg_vol = data['Volume'][sym].iloc[-5:-1].mean()
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            
            # --- NEW: Earnings Check ---
            earnings_date = "---"
            try:
                tk = yf.Ticker(sym)
                cal = tk.calendar
                if cal is not None and 'Earnings Date' in cal:
                    e_date = cal['Earnings Date'][0]
                    days_to = (e_date.date() - datetime.date.today()).days
                    if 0 <= days_to <= 2:
                        earnings_date = f"⚠️ {days_to}d"
            except: pass
            
            rows.append({
                "Asset": label, "Symbol": sym, "Price": price, 
                "Change %": change, "RVOL": rvol, "Earnings": earnings_date
            })
        except: continue
    return pd.DataFrame(rows)

# ========================== UPDATED TAB 4 (Fix for KeyError) ==========================
with tab4:
    target_analyst = st.selectbox("Analyst Focus", list(MAG7_TICKERS.keys()))
    try:
        tk = yf.Ticker(MAG7_TICKERS[target_analyst])
        recs = tk.recommendations
        
        if recs is not None and not recs.empty:
            # Dynamically find the firm/analyst column
            col_map = {col.lower(): col for col in recs.columns}
            firm_col = None
            for candidate in ['firm', 'name', 'analyst', 'company']:
                if candidate in col_map:
                    firm_col = col_map[candidate]
                    break
            
            if firm_col:
                # Filter for Tier 1 Banks
                filtered = recs[recs[firm_col].str.contains('|'.join(TIER_1_BANKS), case=False, na=False)].tail(10)
                if not filtered.empty:
                    st.table(filtered.sort_index(ascending=False))
                else:
                    st.info("No recent Tier 1 Analyst moves for this asset.")
            else:
                st.write("Recent Activity (All Firms):")
                st.dataframe(recs.tail(10), use_container_width=True)
        else:
            st.info("No analyst data found for this ticker.")
    except Exception as e:
        st.error(f"Could not load analyst data: {e}")
