import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
import datetime
import pytz
from finvizfinance.news import News
import matplotlib.pyplot as plt
from scipy.stats import norm

# ========================== PAGE CONFIG ==========================
st.set_page_config(page_title="Pro Market Terminal", page_icon="🏛️", layout="wide")

# ========================== PASSWORD PROTECTION ==========================
def check_password():
    def password_entered():
        if st.session_state["password"] == "Pratimap9!@":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔐 Pro Market Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Access Denied")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ========================== GAMMA CALCULATION ==========================
def calc_gamma(S, K, T, v, r, q, cp_flag, OI):
    if T <= 0 or v <= 0:
        return 0
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return val if cp_flag == 'call' else -val

# ========================== TICKERS ==========================
GLOBAL_TICKERS = {
    "S&P 500 Futures (ES)": "ES=F",
    "Nasdaq 100 Futures (NQ)": "NQ=F",
    "Dow Jones Futures (YM)": "YM=F",
    "SPY (S&P 500 ETF)": "SPY",
    "QQQ (Nasdaq 100 ETF)": "QQQ",
    "VIX": "^VIX",
    "10Y Yield (^TNX)": "^TNX",
    "DXY (US Dollar)": "DX-Y.NYB"
}

SECTOR_TICKERS = {
    "Technology (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE",
    "Healthcare (XLV)": "XLV", "Consumer Disc (XLY)": "XLY", "Industrials (XLI)": "XLI",
    "Utilities (XLU)": "XLU", "Real Estate (XLRE)": "XLRE", "Consumer Staples (XLP)": "XLP",
    "Materials (XLB)": "XLB"
}

ETF_TICKERS = {
    "Bitcoin ETF (IBIT)": "IBIT", "Gold ETF (GLD)": "GLD", "Silver (SLV)": "SLV",
    "Bonds 20Y+ (TLT)": "TLT", "Semis (SMH)": "SMH", "Ark Innovation (ARKK)": "ARKK"
}

TWENTYFOUR_TICKERS = {
    "Bitcoin 24h (BTC-USD)": "BTC-USD", "Ethereum (ETH-USD)": "ETH-USD",
    "Gold Futures (GC)": "GC=F", "Crude Oil (CL)": "CL=F"
}

MAG7_TICKERS = {
    "Apple (AAPL)": "AAPL", "Microsoft (MSFT)": "MSFT", "Nvidia (NVDA)": "NVDA",
    "Amazon (AMZN)": "AMZN", "Alphabet (GOOGL)": "GOOGL", "Meta (META)": "META",
    "Tesla (TSLA)": "TSLA"
}

OPTIONS_TICKERS = {**MAG7_TICKERS, "SPY (S&P 500 ETF)": "SPY", "QQQ (Nasdaq 100 ETF)": "QQQ"}

TIER_1_BANKS = [
    "Goldman Sachs", "Morgan Stanley", "JPMorgan Chase", "JP Morgan",
    "Bank of America", "Citigroup", "Barclays", "UBS",
    "Wells Fargo", "Deutsche Bank", "Credit Suisse"
]

ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **ETF_TICKERS, **TWENTYFOUR_TICKERS, **MAG7_TICKERS}

# ========================== HELPERS ==========================
def analyze_sentiment(text):
    if not text or not isinstance(text, str):
        return "⚖️ Neutral"
    bullish = ['surge', 'up', 'rise', 'gain', 'jump', 'rally', 'growth', 'bull', 'high', 'positive', 'win', 'beat', 'boost', 'strong', 'outperform', 'soar', 'raises']
    bearish = ['fall', 'down', 'drop', 'slump', 'plunge', 'bear', 'low', 'negative', 'loss', 'crash', 'dip', 'cut', 'sink', 'weak', 'miss', 'lowers', 'decline']
    text = text.lower()
    bullish_count = sum(1 for w in bullish if w in text)
    bearish_count = sum(1 for w in bearish if w in text)
    if bullish_count > bearish_count:
        return "🐂 Bullish"
    if bearish_count > bullish_count:
        return "🐻 Bearish"
    return "⚖️ Neutral"

@st.cache_data(ttl=45)
def fetch_all_market_data():
    tickers_list = list(ALL_TICKERS.values())
    ticker_to_label = {v: k for k, v in ALL_TICKERS.items()}

    daily = yf.download(tickers=tickers_list, period="60d", interval="1d", progress=False)
    intra = yf.download(tickers=tickers_list, period="1d", interval="5m", prepost=True, progress=False)

    rows = []
    for t in tickers_list:
        label = ticker_to_label.get(t, t)
        try:
            prev_close = daily['Close'][t].dropna().iloc[-2] if len(daily['Close'][t].dropna()) >= 2 else np.nan
            price = intra['Close'][t].dropna().iloc[-1] if not intra['Close'][t].dropna().empty else daily['Close'][t].iloc[-1]

            change = (price - prev_close) / prev_close * 100 if pd.notna(prev_close) and prev_close != 0 else np.nan

            day_vol = intra['Volume'][t].sum() if 'Volume' in intra and t in intra['Volume'] else 0
            avg_vol = daily['Volume'][t].dropna().iloc[-21:-1].mean() if len(daily['Volume'][t].dropna()) >= 21 else np.nan
            rel_vol = day_vol / avg_vol if avg_vol and avg_vol > 0 else np.nan

            rows.append({"Asset": label, "Symbol": t, "Price": price, "Change %": change, "Rel Vol": rel_vol})
        except Exception:
            rows.append({"Asset": label, "Symbol": t, "Price": np.nan, "Change %": np.nan, "Rel Vol": np.nan})
    return pd.DataFrame(rows)

@st.cache_data(ttl=300)
def get_ticker_news(symbol):
    try:
        return yf.Ticker(symbol).news[:3]
    except Exception:
        return []

@st.cache_data(ttl=600)
def fetch_finviz_news():
    try:
        fnews = News()
        return pd.DataFrame(fnews.get_news().get('news', []))[:10]
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_earnings_and_ratings(days_window=7):
    earnings_list = []
    ratings_list = []
    today = datetime.date.today()
    
    for label, symbol in ALL_TICKERS.items():
        try:
            ticker = yf.Ticker(symbol)
            
            # Analyst ratings
            recs = ticker.recommendations
            if recs is not None and not recs.empty:
                latest = recs.tail(10).copy()
                latest['Symbol'] = symbol
                latest = latest[latest['Firm'].str.contains('|'.join(TIER_1_BANKS), case=False, na=False)]
                if not latest.empty:
                    ratings_list.append(latest)

            # Earnings
            cal = ticker.calendar
            if cal is not None and not cal.empty and 'Earnings Date' in cal.columns:
                e_dates = cal['Earnings Date'].dropna()
                for e_dt in e_dates:
                    e_date = e_dt.date() if hasattr(e_dt, 'date') else pd.to_datetime(e_dt).date()
                    if abs((e_date - today).days) <= days_window:
                        news = ticker.news[:3]
                        title = news[0].get('title', '') if news else ""
                        earnings_list.append({
                            "Asset": label,
                            "Symbol": symbol,
                            "Earnings Date": e_date,
                            "Sentiment": analyze_sentiment(title),
                            "Status": "Upcoming" if e_date >= today else "Reported"
                        })
        except Exception:
            continue
            
    ratings_df = pd.concat(ratings_list, ignore_index=True) if ratings_list else pd.DataFrame()
    earnings_df = pd.DataFrame(earnings_list)
    return ratings_df, earnings_df

@st.cache_data(ttl=300, show_spinner="Fetching options chains...")
def get_options_pcr():
    res = {}
    for label, sym in OPTIONS_TICKERS.items():
        try:
            tk = yf.Ticker(sym)
            exps = tk.options
            if not exps:
                res[label] = {"error": "No options"}
                continue
            cv = pv = 0.0
            for exp in exps[:5]:
                ch = tk.option_chain(exp)
                cv += ch.calls['volume'].fillna(0).sum()
                pv += ch.puts['volume'].fillna(0).sum()
            pcr = pv / cv if cv > 0 else 0.0
            sent = ("🐂 Strongly Bullish" if pcr < 0.75 else "🐂 Bullish" if pcr < 0.90 else
                    "⚖️ Neutral" if pcr < 1.10 else "🐻 Bearish" if pcr < 1.30 else "🐻 Strongly Bearish")
            res[label] = {"pcr": pcr, "call_vol": int(cv), "put_vol": int(pv), "sentiment": sent}
        except Exception as e:
            res[label] = {"error": str(e)}
    return res

# ========================== GEX DATA ==========================
@st.cache_data(ttl=600)
def get_gex_data(symbol):
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="1d")
        
        if hist.empty:
            return None, None
        
        spot = hist['Close'].iloc[-1]
        # We return the list of expirations (strings) instead of the Ticker object
        expirations = tk.options 
        
        return spot, expirations
    except Exception as e:
        st.error(f"GEX Fetch Error: {e}")
        return None, None
# ========================== STYLING ==========================
def color_pct(val):
    if pd.isna(val):
        return ''
    return 'color: #00ff00' if val > 0 else 'color: #ff4b4b' if val < 0 else ''

def color_rel(val):
    if pd.isna(val):
        return ''
    if val > 2.0:
        return 'background-color: #90ee90; font-weight: bold'
    if val > 1.5:
        return 'background-color: #98fb98'
    if val < 0.5:
        return 'background-color: #ffb6c1'
    return ''

# ========================== SIDEBAR ==========================
st.sidebar.divider()
st.sidebar.subheader("🗞️ Market Intelligence")
news_data = fetch_finviz_news()
if not news_data.empty:
    for _, r in news_data.iterrows():
        with st.sidebar.expander(f"{r['Source']} | {r['Date']}"):
            st.write(r['Title'])
            url = r.get('url') or r.get('URL')
            if url:
                st.markdown(f"[Read]({url})")
else:
    st.sidebar.info("News unavailable")

st.sidebar.title("🏛️ Market Settings")
refresh = st.sidebar.number_input('Refresh rate (sec)', 15, 600, 30, step=15)
st_autorefresh(interval=refresh * 1000, key="refresh")

# ========================== DATA FETCHING ==========================
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

full_market = fetch_all_market_data().dropna(subset=['Change %'])

global_df = full_market[full_market['Asset'].isin(GLOBAL_TICKERS.keys())].copy()
sector_df = full_market[full_market['Asset'].isin(SECTOR_TICKERS.keys())].copy()
etf_df = full_market[full_market['Asset'].isin(ETF_TICKERS.keys())].copy()
tf_df = full_market[full_market['Asset'].isin(TWENTYFOUR_TICKERS.keys())].copy()
mag7_df = full_market[full_market['Asset'].isin(MAG7_TICKERS.keys())].copy()

for df in [global_df, sector_df, etf_df, tf_df, mag7_df]:
    df.sort_values('Change %', ascending=False, inplace=True)

benchmark_change = full_market.loc[full_market['Asset'] == "SPY (S&P 500 ETF)", 'Change %'].iloc[0] if "SPY (S&P 500 ETF)" in full_market['Asset'].values else 0.0
for df in [sector_df, etf_df, tf_df, mag7_df]:
    df['RS'] = df['Change %'] - benchmark_change

top_gainers = full_market.nlargest(6, 'Change %')
top_losers = full_market.nsmallest(6, 'Change %')

mover_sent = {}
for _, row in pd.concat([top_gainers, top_losers]).drop_duplicates('Asset').iterrows():
    items = get_ticker_news(row['Symbol'])
    if not items:
        mover_sent[row['Asset']] = "❓ No News"
    else:
        titles = ' '.join([i.get('title', '') for i in items[:3]])
        mover_sent[row['Asset']] = analyze_sentiment(titles)

# ========================== MAIN UI ==========================
st.title("🏛️ Pro Market Terminal")
st.caption(f"Live • EST {time_now} • Refresh {refresh}s")

# Market Scanner
st.subheader("🔍 Market Scanner")
c1, c2, c3 = st.columns([2, 2, 1])

with c1:
    st.write("**Top 6 Leaders 🚀**")
    for _, r in top_gainers.iterrows():
        fire = "🔥" if r.get('Rel Vol', 0) > 1.5 else ""
        st.write(f"🟢 {r['Asset']}: `{r['Change %']:+.2f}%` {mover_sent.get(r['Asset'], '')} {fire}")

with c2:
    st.write("**Top 6 Laggards 📉**")
    for _, r in top_losers.iterrows():
        fire = "🔥" if r.get('Rel Vol', 0) > 1.5 else ""
        st.write(f"🔴 {r['Asset']}: `{r['Change %']:+.2f}%` {mover_sent.get(r['Asset'], '')} {fire}")

with c3:
    up = len(full_market[full_market['Change %'] > 0])
    total = len(full_market)
    st.metric("Breadth", f"{up} ↑ / {total - up} ↓", delta=up - (total - up))

st.divider()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🌎 Global Indices",
    "📈 Sectors, ETFs, 24h & Mag7",
    "📊 Relative Strength & Charts",
    "⚖️ Options Sentiment",
    "🎯 Analyst & Earnings",
    "📉 Gamma Exposure"
])

with tab1:
    st.subheader("Major Markets & Indices")
    st.dataframe(
        global_df.drop(columns=['Symbol']).style
            .format({"Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": "{:.2f}x"})
            .applymap(color_pct, subset=["Change %"])
            .applymap(color_rel, subset=["Rel Vol"]),
        use_container_width=True, hide_index=True
    )

with tab2:
    c1, c2, c3, c4 = st.columns(4)
    for name, df, col in zip(
        ["Sectors", "ETFs", "24h & Commodities", "Magnificent 7"],
        [sector_df, etf_df, tf_df, mag7_df],
        [c1, c2, c3, c4]
    ):
        with col:
            st.subheader(name)
            styled = df.drop(columns=['Symbol']).style \
                .format({"Price": "{:.2f}", "Change %": "{:+.2f}%", "Rel Vol": "{:.2f}x", "RS": "{:+.2f}%"}) \
                .applymap(color_pct, subset=["Change %", "RS"]) \
                .applymap(color_rel, subset=["Rel Vol"])
            st.dataframe(styled, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Relative Strength vs SPY")
    for name, df in [("Sectors", sector_df), ("24h & Commodities", tf_df), ("Mag7", mag7_df)]:
        st.write(f"**{name}**")
        st.bar_chart(df.set_index("Asset")["RS"])
        st.divider()

    st.subheader("Intraday Charts")
    sel = st.multiselect(
        "Select assets", list(ALL_TICKERS.keys()),
        default=["SPY (S&P 500 ETF)", "Bitcoin 24h (BTC-USD)", "Nvidia (NVDA)"]
    )
    for lab in sel:
        data = yf.Ticker(ALL_TICKERS[lab]).history(period="1d", interval="5m", prepost=True)
        if not data.empty:
            st.write(f"**{lab}**")
            close = data['Close']
            if close.index.tz is None:
                close = close.tz_localize('UTC').tz_convert('US/Eastern')
            else:
                close = close.tz_convert('US/Eastern')
            st.line_chart(close)

with tab4:
    st.subheader("Options Sentiment (PCR)")
    st.caption("Put/Call Ratio • <0.8 Bullish • >1.1 Bearish • nearest 5 expirations")
    data = get_options_pcr()
    cols = st.columns(5)
    for i, (label, info) in enumerate(data.items()):
        c = cols[i % 5]
        if "error" in info:
            c.error(f"{label}\n{info['error']}")
        else:
            c.metric(
                label, f"{info['pcr']:.2f}", info['sentiment'],
                help=f"Call: {info['call_vol']:,} • Put: {info['put_vol']:,}"
            )

    tc = sum(d.get("call_vol", 0) for d in data.values() if "error" not in d)
    tp = sum(d.get("put_vol", 0) for d in data.values() if "error" not in d)
    ap = tp / tc if tc > 0 else 0
    col1, col2 = st.columns([1, 3])
    col1.metric("Aggregate PCR", f"{ap:.2f}")
    if ap < 0.80:
        col2.success("**Strongly Bullish** options flow")
    elif ap > 1.10:
        col2.error("**Strongly Bearish** options flow")
    else:
        col2.info("**Neutral** options flow")

with tab5:
    st.subheader("🎯 Market Moving Events")
    days_range = st.slider("Select Earnings/Analyst Window (Days)", 1, 30, 7)
    ratings_df, earnings_df = fetch_earnings_and_ratings(days_window=days_range)
    
    col_e, col_r = st.columns(2)
    
    with col_e:
        st.write(f"**Earnings (±{days_range} Days)**")
        if not earnings_df.empty:
            earnings_df = earnings_df.sort_values("Earnings Date")
            st.dataframe(earnings_df.drop(columns=['Symbol']), use_container_width=True, hide_index=True)
        else:
            st.info(f"No earnings found in ±{days_range} day window.")
            
    with col_r:
        st.write("**Tier 1 Analyst Moves & Targets**")
        if not ratings_df.empty:
            target_cols = [c for c in ['Target Price', 'Price Target', 'New Target'] if c in ratings_df.columns]
            display_cols = ['Symbol', 'Firm', 'To Grade'] + target_cols + ['Action']
            st.dataframe(ratings_df[display_cols].sort_values(by='Date', ascending=False).head(20),
                         use_container_width=True, hide_index=True)
        else:
            st.info("No Tier 1 analyst changes detected.")

with tab6:
    st.subheader("Gamma Exposure (GEX) Profile")
    gex_options = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "MSFT", "AMZN", "META", "GOOGL"]
    gex_ticker = st.selectbox("Select Ticker for GEX", gex_options, index=0)
    
    with st.spinner(f"Calculating GEX for {gex_ticker}..."):
        # FIX 1: Only unpack 2 values (spot and expirations)
        result = get_gex_data(gex_ticker)
        
        if result and result[0] is not None:
            spot, expirations = result
            tk = yf.Ticker(gex_ticker) # Local ticker object
            all_opts = []
            
            for exp in expirations[:3]:
                try:
                    chain = tk.option_chain(exp)
                    c, p = chain.calls.copy(), chain.puts.copy()
                    c['type'], p['type'], c['exp'], p['exp'] = 'call', 'put', exp, exp
                    all_opts.append(pd.concat([c, p]))
                except Exception:
                    continue
            
            # FIX 2: Ensure this 'if' is perfectly aligned
            if all_opts:
                df_gex = pd.concat(all_opts)
                now = pd.Timestamp.now().tz_localize(None)
                df_gex['dte'] = (pd.to_datetime(df_gex['exp']).dt.tz_localize(None) - now).dt.days / 365.0
                df_gex['dte'] = df_gex['dte'].clip(lower=1/365)
                
                df_gex['GEX'] = df_gex.apply(lambda r: calc_gamma(
                    spot, r['strike'], r['dte'], r['impliedVolatility'], 0.04, 0.01, r['type'], r['openInterest']
                ), axis=1)
                
                df_agg = df_gex.groupby('strike')['GEX'].sum() / 1e6
                
                fig, ax = plt.subplots(figsize=(12, 5))
                fig.patch.set_facecolor('#0e1117')
                ax.set_facecolor('#0e1117')
                ax.bar(df_agg.index, df_agg.values, width=(spot * 0.003), color='#00d4ff', alpha=0.8)
                ax.axvline(spot, color='#ff4b4b', linestyle='--', label=f'Spot: {spot:.2f}')
                ax.set_xlim(spot * 0.94, spot * 1.06)
                ax.tick_params(colors='white')
                ax.grid(True, alpha=0.1)
                st.pyplot(fig)
            else:
                st.error("No options data found for this ticker.")
        else:
            st.error("Could not fetch spot price. Yahoo Finance might be throttling requests.")
