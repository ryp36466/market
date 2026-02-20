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
from scipy.stats import norm

# ────────────────────────────────────────────────
#  PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ────────────────────────────────────────────────
#  TICKER CONFIGS
# ────────────────────────────────────────────────
GLOBAL_TICKERS = {
    "S&P 500 (ES)": "ES=F", "Nasdaq (NQ)": "NQ=F", "Dow (YM)": "YM=F",
    "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "10Y Yield": "^TNX",
    "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
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

NEO_CLOUD_TICKERS = {
    "Nebius": "NBIS", 
    "Vertiv": "VRT", 
    "Arista": "ANET", 
    "Supermicro": "SMCI", 
    "Dell": "DELL", 
    "Palantir": "PLTR"
}

MAG7_TICKERS = {
    "Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN",
    "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"
}

# Combine all for background fetching
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **NEO_CLOUD_TICKERS, **MAG7_TICKERS}

HUGE_CAP_SYMBOLS = {
    'WMT', 'BABA', 'DE', 'SO', 'NEM', 'BKNG', 'TXRH', 'RIO',
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA',
    'T', 'VZ', 'XOM', 'CVX', 'JPM', 'BAC', 'WFC', 'PG', 'KO',
    'HD', 'COST', 'NFLX', 'DIS', 'PFE', 'MRK', 'LLY', 'AVGO'
}

TIER1_FIRMS = {
    'Goldman Sachs', 'Morgan Stanley', 'JPMorgan', 'Bank of America', 'Citigroup', 'Barclays',
    'Evercore', 'UBS', 'Jefferies', 'RBC Capital', 'Deutsche Bank', 'Wells Fargo',
    'BofA Securities', 'Credit Suisse', 'Bernstein', 'Piper Sandler', 'Oppenheimer',
    'Wedbush', 'Stifel', 'Wolfe Research'
}

FINNHUB_API_KEY = "d6au4n9r01qnr27itio0d6au4n9r01qnr27itiog"

# ────────────────────────────────────────────────
#  DATA HELPERS
# ────────────────────────────────────────────────

@st.cache_data(ttl=45)
def fetch_market_snapshot():
    symbols = list(ALL_TICKERS.values())
    # 5-day Daily for RVOL and Relative Strength
    hist_data = yf.download(symbols, period="5d", interval="1d", progress=False)
    # Today's Intraday
    intra = yf.download(symbols, period="1d", interval="5m", prepost=True, progress=False)
    
    rows = []
    for label, sym in ALL_TICKERS.items():
        try:
            price = intra['Close'][sym].dropna().iloc[-1]
            prev_close = hist_data['Close'][sym].iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            today_vol = intra['Volume'][sym].sum()
            avg_vol = hist_data['Volume'][sym].iloc[-5:-1].mean()
            rvol = today_vol / avg_vol if avg_vol > 0 else 1.0
            rows.append({"Asset": label, "Symbol": sym, "Price": price, "Change %": change, "RVOL": rvol})
        except:
            continue
    return pd.DataFrame(rows), intra, hist_data

def get_earnings_calendar_finnhub(date_str):
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={date_str}&to={date_str}&token={FINNHUB_API_KEY}"
    try:
        r = requests.get(url, timeout=10); r.raise_for_status()
        data = r.json(); filtered = []; fallback = []
        for item in data.get('earningsCalendar', []):
            symbol = item.get('symbol', '').upper()
            eps_est = item.get('epsEstimate'); eps_act = item.get('epsActual')
            rev_est = item.get('revenueEstimate'); rev_act = item.get('revenueActual')
            eps_beat = "—"
            if eps_act is not None and eps_est is not None:
                eps_beat = "✅ Beat" if eps_act > eps_est else "❌ Miss" if eps_act < eps_est else "Met"
            rev_beat = "—"
            if rev_act is not None and rev_est is not None:
                rev_beat = "✅ Beat" if rev_act > rev_est else "❌ Miss" if rev_act < rev_est else "Met"
            entry = {
                "When": "", "Symbol": symbol, "Company": symbol, "EPS Est": eps_est if eps_est is not None else "—",
                "EPS Act": eps_act if eps_act is not None else "—",
                "Rev Est (B)": round(rev_est / 1e9, 2) if rev_est else "—",
                "Rev Act (B)": round(rev_act / 1e9, 2) if rev_act else "—",
                "EPS Beat": eps_beat, "Rev Beat": rev_beat
            }
            fallback.append(entry)
            if symbol in HUGE_CAP_SYMBOLS: filtered.append(entry)
        return filtered if filtered else fallback
    except: return []

def get_todays_earnings():
    today = datetime.datetime.now(pytz.timezone('US/Eastern')).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(today)
    for d in data: d["When"] = "Today"
    return data

def get_yesterdays_earnings():
    yest = (datetime.datetime.now(pytz.timezone('US/Eastern')) - datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(yest)
    for d in data: d["When"] = "Yesterday"
    return data

def get_tomorrows_earnings():
    tom = (datetime.datetime.now(pytz.timezone('US/Eastern')) + datetime.timedelta(days=1)).date().strftime('%Y-%m-%d')
    data = get_earnings_calendar_finnhub(tom)
    for d in data: d["When"] = "Tomorrow"
    return data

@st.cache_data(ttl=900)
def get_analyst_changes_yfinance(days_back=10):
    symbols_to_check = list(HUGE_CAP_SYMBOLS)[:40]
    all_changes = []
    for symbol in symbols_to_check:
        try:
            tk = yf.Ticker(symbol); rec = tk.recommendations
            if rec is None or rec.empty: continue
            rec = rec[rec.index >= pd.Timestamp.now() - pd.Timedelta(days=days_back)]
            for idx, row in rec.iterrows():
                firm = row.get('Firm', 'Unknown')
                if firm not in TIER1_FIRMS and 'Unknown' not in firm: continue
                all_changes.append({"Date": idx.strftime('%Y-%m-%d'), "Symbol": symbol, "Firm": firm, "Action": row.get('Action', 'Change'), "From": row.get('From Grade', '—'), "To": row.get('To Grade', '—')})
        except: continue
    df = pd.DataFrame(all_changes)
    if not df.empty:
        df = df.sort_values("Date", ascending=False).drop_duplicates(subset=["Date", "Symbol", "Firm", "To"])
    return df

def get_pcr_data():
    targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ"}
    results = []
    for label, sym in targets.items():
        try:
            tk = yf.Ticker(sym); opts = tk.options
            if opts:
                cv = pv = 0
                for exp in opts[:2]:
                    ch = tk.option_chain(exp)
                    cv += ch.calls['volume'].sum(); pv += ch.puts['volume'].sum()
                pcr = pv / cv if cv > 0 else 0
                results.append({"Asset": label, "PCR": round(pcr, 2), "Sentiment": "🐂 Bull" if pcr < 0.85 else "🐻 Bear" if pcr > 1.15 else "⚖️ Neu"})
        except: continue
    return pd.DataFrame(results)

def get_sentiment_score(text):
    bull = ['upbeat','growth','surge','rally','beat','buy','bullish','expansion','profit','gain','positive','jump']
    bear = ['slump','drop','fall','miss','sell','bearish','contraction','loss','negative','inflation','fear','risk','sink']
    score = sum(1 for w in bull if w in text.lower()) - sum(1 for w in bear if w in text.lower())
    if score > 0: return "🟢 Bullish", score
    if score < 0: return "🔴 Bearish", score
    return "⚪ Neutral", 0

def calc_gamma_vectorized(S, K, T, v, r, q, types, OI):
    T = np.maximum(T, 1/365); v = np.maximum(v, 0.01)
    d1 = (np.log(S / K) + (r - q + 0.5 * v**2) * T) / (v * np.sqrt(T))
    gamma = np.exp(-q * T) * norm.pdf(d1) / (S * v * np.sqrt(T))
    val = (OI * 100) * (S**2) * 0.01 * gamma
    return np.where(types == 'call', val, -val)

def get_finviz_news_stable():
    try: return News().get_news()['news'].head(15).to_dict('records')
    except:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get("https://finviz.com/news.ashx", headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser"); table = soup.find("table", id="news-table")
            if not table: return []
            news_list = []
            for row in table.find_all("tr")[:15]:
                cells = row.find_all("td")
                if len(cells) != 2: continue
                a = cells[1].find("a", class_="tab-link-news")
                if a: news_list.append({"Title": a.text.strip(), "URL": a["href"], "Source": "Finviz", "Date": cells[0].text.strip()})
            return news_list
        except: return []

# ────────────────────────────────────────────────
#  MAIN UI
# ────────────────────────────────────────────────
market_df, intra_data, hist_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Data as of {datetime.date.today()} | Day-Trader Edition with Gamma Flip")

tab_overview, tab_sectors, tab_rel_strength, tab_gex, tab_options, tab_earnings, tab_analyst, tab_extremes, tab_news = st.tabs([
    "📈 Market Overview", "🔥 Alpha Sectors", "⚖️ Relative Strength", "📊 GEX + Gamma Flip", "🐳 Options",
    "🎯 Earnings", "📊 Analyst Changes", "🔥 ATH/ATL Plays", "📰 News Wire"
])

with tab_overview:
    st.subheader("🗝️ Key Indices")
    key_df = market_df[market_df['Asset'].isin(["S&P 500", "SPY", "QQQ"])][['Asset', 'Price', 'Change %', 'RVOL']].round(2)
    st.dataframe(key_df.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)

    st.subheader("🚀 Magnificent 7")
    mag7_df = market_df[market_df['Asset'].isin(MAG7_TICKERS.keys())].copy().sort_values('Change %', ascending=False)
    spy_change = mag7_df[mag7_df['Asset'] == "SPY"]['Change %'].iloc[0] if not mag7_df[mag7_df['Asset'] == "SPY"].empty else 0
    mag7_df['vs SPY (%)'] = (mag7_df['Change %'] - spy_change).round(2)
    st.dataframe(mag7_df[['Asset', 'Price', 'Change %', 'vs SPY (%)', 'RVOL']].round(2)
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'vs SPY (%)', 'RVOL']),
                 hide_index=True, use_container_width=True)

with tab_sectors:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Major ETFs")
        sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
        st.dataframe(sect_data[['Asset', 'Price', 'Change %', 'RVOL']]
                     .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']),
                     hide_index=True, use_container_width=True)
    with col_b:
        st.subheader("☁️ Neo Clouds (AI Infrastructure)")
        neo_data = market_df[market_df['Asset'].isin(NEO_CLOUD_TICKERS.keys())].copy()
        st.dataframe(neo_data[['Asset', 'Price', 'Change %', 'RVOL']]
                     .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']),
                     hide_index=True, use_container_width=True)

with tab_rel_strength:
    st.subheader("⚖️ Sector Strength vs SPY")
    st.caption("5-Day Cumulative Performance normalized to 0%")
    try:
        benchmark = "SPY"
        sector_symbols = list(SECTOR_TICKERS.values())
        plot_df = hist_data['Close'][[benchmark] + sector_symbols].dropna()
        normalized_df = (plot_df / plot_df.iloc[0] - 1) * 100
        
        fig = px.line(normalized_df.reset_index().melt(id_vars='Date', var_name='Ticker', value_name='Perf %'),
                      x='Date', y='Perf %', color='Ticker', template="plotly_dark", height=500)
        fig.update_traces(patch={"line": {"width": 4, "dash": "dot"}}, selector={"legendgroup": "SPY"})
        st.plotly_chart(fig, use_container_width=True)
        
        st.write("### Alpha Delta (Current vs SPY)")
        current_perf = normalized_df.iloc[-1]
        rel_perf = (current_perf - current_perf[benchmark]).round(2).reset_index()
        rel_perf.columns = ['Ticker', 'vs SPY (%)']
        st.dataframe(rel_perf.sort_values('vs SPY (%)', ascending=False).style.background_gradient(cmap='RdYlGn'),
                     hide_index=True, use_container_width=True)
    except Exception as e: st.error(f"RS Error: {e}")

    # ────────────────────────────────────────────────
    #  NEW: MAG7 RELATIVE STRENGTH LINE CHART (added exactly as requested)
    # ────────────────────────────────────────────────
    st.subheader("⚖️ Mag7 Strength vs SPY")
    st.caption("5-Day Cumulative Performance normalized to 0%")
    try:
        benchmark = "SPY"
        mag7_symbols = list(MAG7_TICKERS.values())
        plot_df = hist_data['Close'][[benchmark] + mag7_symbols].dropna()
        normalized_df = (plot_df / plot_df.iloc[0] - 1) * 100
        
        fig = px.line(normalized_df.reset_index().melt(id_vars='Date', var_name='Ticker', value_name='Perf %'),
                      x='Date', y='Perf %', color='Ticker', template="plotly_dark", height=500)
        fig.update_traces(patch={"line": {"width": 4, "dash": "dot"}}, selector={"legendgroup": "SPY"})
        st.plotly_chart(fig, use_container_width=True)
        
        st.write("### Alpha Delta (Current vs SPY)")
        current_perf = normalized_df.iloc[-1]
        rel_perf = (current_perf - current_perf[benchmark]).round(2).reset_index()
        rel_perf.columns = ['Ticker', 'vs SPY (%)']
        st.dataframe(rel_perf.sort_values('vs SPY (%)', ascending=False).style.background_gradient(cmap='RdYlGn'),
                     hide_index=True, use_container_width=True)
    except Exception as e: st.error(f"Mag7 RS Error: {e}")

with tab_gex:
    st.subheader("📊 Gamma Exposure (GEX) + Gamma Flip Level")
    st.caption("Front 3 expirations • Green = Long Gamma (stabilizing) • Red = Short Gamma (amplifying) • Yellow line = **Gamma Flip**")
    
    user_ticker = st.text_input("Enter Ticker for GEX Analysis", value="SPY").upper().strip()
    
    if user_ticker:
        try:
            tk = yf.Ticker(user_ticker)
            options = tk.options
            if not options:
                st.warning("No options data found.")
            else:
                spot = round(tk.history(period="1d")['Close'].iloc[-1], 2)
                
                all_chains = []
                for exp in options[:3]:
                    ch = tk.option_chain(exp)
                    all_chains.extend([
                        ch.calls.assign(type='call', exp=exp),
                        ch.puts.assign(type='put', exp=exp)
                    ])
                df_g = pd.concat(all_chains, ignore_index=True)
                
                df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365.0
                df_g['GEX'] = calc_gamma_vectorized(
                    spot, df_g['strike'].values, df_g['dte'].values,
                    df_g['impliedVolatility'].values, 0.04, 0.01,
                    df_g['type'].values, df_g['openInterest'].values
                )
                
                df_agg = (df_g.groupby('strike')['GEX'].sum() / 1e6).sort_index()
                
                # ====================== GAMMA FLIP CALCULATION ======================
                strikes = np.asarray(df_agg.index)
                gex_vals = np.asarray(df_agg.values)
                
                flip_level = spot  # fallback
                for i in range(1, len(strikes)):
                    if gex_vals[i-1] <= 0 and gex_vals[i] > 0:
                        # Linear interpolation at zero crossing
                        x1, y1 = strikes[i-1], gex_vals[i-1]
                        x2, y2 = strikes[i], gex_vals[i]
                        flip_level = x1 - y1 * (x2 - x1) / (y2 - y1)
                        break
                
                # Fallback: highest strike still showing negative GEX
                if abs(flip_level - spot) < 0.1 and np.any(gex_vals < 0):
                    flip_level = strikes[gex_vals < 0][-1]
                
                flip_level = round(flip_level)
                
                # ====================== METRICS ======================
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric(
                        label="🔄 **Gamma Flip Level**",
                        value=f"${flip_level:,}",
                        delta=f"Spot is {((spot - flip_level)/flip_level*100):+.1f}% above flip"
                    )
                with col2:
                    total_gex = round(df_agg.sum(), 1)
                    st.metric(
                        label="Net GEX",
                        value=f"{total_gex}M",
                        delta="🟢 Long Gamma (pinning likely)" if total_gex > 0 else "🔴 Short Gamma (volatile)"
                    )
                with col3:
                    st.metric("Current Spot", f"${spot:,.2f}")
                
                st.caption("**Gamma Flip** = strike where net GEX changes from negative → positive. "
                          "Above flip = dealers long gamma (dampens moves). Below = short gamma (amplifies moves). "
                          "Key intraday level for day traders.")
                
                # ====================== PLOT ======================
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=df_agg.index,
                    y=df_agg.values,
                    marker_color=['#00ff88' if x > 0 else '#ff4444' for x in df_agg.values],
                    name="GEX ($M)"
                ))
                
                fig.add_vline(
                    x=spot,
                    line_dash="dash",
                    line_color="white",
                    annotation_text=f"Spot ${spot}",
                    annotation_position="top"
                )
                fig.add_vline(
                    x=flip_level,
                    line_dash="dot",
                    line_color="#ffd700",
                    line_width=3,
                    annotation_text=f"🔄 GAMMA FLIP ${flip_level}",
                    annotation_position="bottom right" if flip_level < spot else "top left"
                )
                
                fig.update_layout(
                    template="plotly_dark",
                    title=f"{user_ticker} Net Gamma Exposure + Gamma Flip Level",
                    height=560,
                    xaxis_title="Strike Price",
                    yaxis_title="Gamma Exposure ($ Millions)",
                    hovermode="x unified"
                )
                st.plotly_chart(fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"GEX Error: {e}")
            st.info("Try SPY, QQQ, NVDA, TSLA — most liquid names work best.")

with tab_options:
    st.subheader("🐳 Put/Call Volume Ratio")
    pcr_df = get_pcr_data()
    if not pcr_df.empty:
        st.dataframe(pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'), hide_index=True, use_container_width=True)

with tab_earnings:
    st.subheader("🎯 Earnings Calendar")
    all_events = get_yesterdays_earnings() + get_todays_earnings() + get_tomorrows_earnings()
    if all_events:
        df = pd.DataFrame(all_events)
        def highlight_beats(val):
            if val == "✅ Beat": return 'background-color: #00cc66; color: black; font-weight: bold;'
            if val == "❌ Miss": return 'background-color: #ff4d4d; color: white; font-weight: bold;'
            return ''
        st.dataframe(df.style.applymap(highlight_beats, subset=['EPS Beat', 'Rev Beat']), hide_index=True, use_container_width=True)

with tab_analyst:
    st.subheader("📊 Recent Analyst Changes")
    analyst_df = get_analyst_changes_yfinance()
    if not analyst_df.empty:
        def highlight_action(val):
            if "Upgrade" in val: return 'background-color: #00cc66; color: black; font-weight: bold;'
            if "Downgrade" in val: return 'background-color: #ff4d4d; color: white; font-weight: bold;'
            return ''
        st.dataframe(analyst_df.style.applymap(highlight_action, subset=['Action']), hide_index=True, use_container_width=True)

with tab_extremes:
    st.info("ATH/ATL scanner – coming soon")

with tab_news:
    st.subheader("📰 News Wire")
    headlines = get_finviz_news_stable()
    if headlines:
        total_score = 0
        for item in headlines:
            label, score = get_sentiment_score(item.get('Title', ''))
            total_score += score
            with st.expander(f"{label} | {item.get('Title')}"):
                st.write(f"Source: {item.get('Source')}")
                st.write(f"[Link]({item.get('URL')})")
        st.sidebar.metric("Sentiment Pulse", total_score, delta="Positive" if total_score >= 0 else "Negative")

st_autorefresh(interval=300000, key="global_refresh")
