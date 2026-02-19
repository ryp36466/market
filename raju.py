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

# ========================== PAGE CONFIG ==========================
st.set_page_config(page_title="Alpha Terminal Pro", page_icon="🏛️", layout="wide")

# ========================== PASSWORD PROTECTION ==========================
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

def check_password():
    if st.session_state.get("password_correct", False):
        return True

    def password_entered():
        if st.session_state.get("password") == "Pratimap9!@":
            st.session_state.password_correct = True
            st.session_state.password = ""
        else:
            st.session_state.password_correct = False
            st.session_state.password = ""

    st.title("🔐 Pro Market Access")
    st.text_input("Enter Password", type="password", on_change=password_entered, key="password")

    if st.session_state.get("password_correct") is False and st.session_state.get("password") == "":
        if "password" in st.session_state and st.session_state.password != "":
            st.error("😕 Access Denied")

    return False

if not check_password():
    st.stop()

# ========================== TICKER CONFIGS ==========================
GLOBAL_TICKERS = {
    "S&P 500 (ES)": "ES=F", "Nasdaq (NQ)": "NQ=F", "Dow (YM)": "YM=F",
    "SPY": "SPY", "QQQ": "QQQ", "VIX": "^VIX", "10Y Yield": "^TNX",
    "DXY": "DX-Y.NYB", "S&P 500": "^GSPC"
}
SECTOR_TICKERS = {"Tech (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE",
                  "Healthcare (XLV)": "XLV", "Disc (XLY)": "XLY", "Indus (XLI)": "XLI",
                  "Utils (XLU)": "XLU", "RE": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"}
MAG7_TICKERS = {
    "Apple": "AAPL", "Microsoft": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN",
    "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"
}
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **MAG7_TICKERS}

# ========================== CORE HELPERS ==========================
def get_pcr_data():
    targets = {**MAG7_TICKERS, "SPY": "SPY", "QQQ": "QQQ"}
    results = []
    for label, sym in targets.items():
        try:
            tk = yf.Ticker(sym)
            cv = pv = 0
            opts = tk.options
            if opts:
                for exp in opts[:2]:
                    ch = tk.option_chain(exp)
                    cv += ch.calls['volume'].sum()
                    pv += ch.puts['volume'].sum()
                pcr = pv / cv if cv > 0 else 0
                
                if pcr < 0.85:
                    sentiment = "🐂 Bull"
                    rec = "🟢 BUY CALLS"
                elif pcr > 1.15:
                    sentiment = "🐻 Bear"
                    rec = "🔴 BUY PUTS"
                else:
                    sentiment = "⚖️ Neutral"
                    rec = "⚪ Neutral / Straddle"
                
                results.append({
                    "Asset": label,
                    "PCR": round(pcr, 2),
                    "Sentiment": sentiment,
                    "Recommendation": rec
                })
        except:
            continue
    return pd.DataFrame(results)

def get_sentiment_score(text):
    bull = ['upbeat','growth','surge','rally','beat','buy','bullish','expansion','profit','gain','positive','jump']
    bear = ['slump','drop','fall','miss','sell','bearish','contraction','loss','negative','inflation','fear','risk','sink']
    score = sum(1 for w in bull if w in text.lower()) - sum(1 for w in bear if w in text.lower())
    if score > 0: return "🟢 Bullish", score
    if score < 0: return "🔴 Bearish", score
    return "⚪ Neutral", 0

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
            price = intra['Close'][sym].dropna().iloc[-1] if not intra['Close'][sym].dropna().empty else np.nan
            prev_close = data['Close'][sym].iloc[-2] if len(data['Close'][sym]) >= 2 else np.nan
            change = ((price - prev_close) / prev_close * 100) if pd.notna(price) and pd.notna(prev_close) else np.nan
            today_vol = intra['Volume'][sym].sum() if not intra['Volume'][sym].dropna().empty else 0
            avg_vol = data['Volume'][sym].iloc[-5:-1].mean() if len(data['Volume'][sym]) >= 5 else np.nan
            rvol = today_vol / avg_vol if pd.notna(avg_vol) and avg_vol > 0 else 1.0
            rows.append({"Asset": label, "Symbol": sym, "Price": price, "Change %": change, "RVOL": rvol})
        except:
            continue
    return pd.DataFrame(rows), intra

# ========================== MAG7 EARNINGS (numeric + display versions) ==========================
@st.cache_data(ttl=1800)
def get_mag7_earnings_enhanced():
    earnings_list = []
    est = pytz.timezone('US/Eastern')
    now = datetime.datetime.now(est)

    for label, sym in MAG7_TICKERS.items():
        try:
            tk = yf.Ticker(sym)
            hist = tk.get_earnings_dates(limit=8)

            next_date = "TBD"
            is_upcoming = False
            last_eps = np.nan
            last_rev = np.nan
            eps_surprise = 0.0
            rev_surprise = 0.0
            consensus_eps = np.nan
            consensus_rev = np.nan
            status = "—"

            if hist is not None and not hist.empty:
                future = hist[hist.index > now]
                if not future.empty:
                    next_date = future.index[0].strftime('%Y-%m-%d')
                    is_upcoming = True

                reported = hist.dropna(subset=['Reported EPS'])
                if not reported.empty:
                    recent = reported.iloc[0]
                    last_eps = recent['Reported EPS'] if pd.notna(recent['Reported EPS']) else np.nan

                    if 'Surprise(%)' in recent and pd.notna(recent['Surprise(%)']):
                        eps_surprise = recent['Surprise(%)']

                    if 'Estimate' in recent and pd.notna(recent['Estimate']):
                        consensus_eps = recent['Estimate']

                    if 'Reported Revenue' in recent and pd.notna(recent['Reported Revenue']):
                        last_rev = recent['Reported Revenue']
                    if 'Revenue Estimate' in recent and pd.notna(recent['Revenue Estimate']):
                        rev_est = recent['Revenue Estimate']
                        consensus_rev = rev_est
                        if last_rev and rev_est and rev_est != 0:
                            rev_surprise = ((last_rev - rev_est) / rev_est) * 100

                    status = "✅ Beat" if eps_surprise > 0 else "❌ Miss" if eps_surprise < 0 else "Met"

            earnings_list.append({
                "Asset": label,
                "Next Earnings": next_date if is_upcoming else "Reported",
                "Last EPS": last_eps,
                "Consensus EPS": consensus_eps,
                "EPS Surprise": eps_surprise,      # numeric
                "Last Revenue": last_rev,
                "Consensus Revenue": consensus_rev,
                "Revenue Surprise": rev_surprise,  # numeric
                "Status": status
            })
        except:
            earnings_list.append({
                "Asset": label,
                "Next Earnings": "Error",
                "Last EPS": np.nan,
                "Consensus EPS": np.nan,
                "EPS Surprise": 0.0,
                "Last Revenue": np.nan,
                "Consensus Revenue": np.nan,
                "Revenue Surprise": 0.0,
                "Status": "—"
            })

    df = pd.DataFrame(earnings_list)
    return df.sort_values("Asset")

# ========================== NEWS ==========================
def get_finviz_news_stable():
    try:
        return News().get_news()['news'].head(15).to_dict('records')
    except:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get("https://finviz.com/news.ashx", headers=headers, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find("table", id="news-table")
            if not table:
                return []
            news_list = []
            for row in table.find_all("tr")[:15]:
                cells = row.find_all("td")
                if len(cells) != 2:
                    continue
                a = cells[1].find("a", class_="tab-link-news")
                if a:
                    news_list.append({
                        "Title": a.text.strip(),
                        "URL": a["href"],
                        "Source": cells[1].find("div", class_="news-link-right").get_text(strip=True).strip("() ") if cells[1].find("div", class_="news-link-right") else "Finviz",
                        "Date": cells[0].text.strip()
                    })
            return news_list
        except:
            return []

# ========================== MAIN UI ==========================
market_df, intra_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Performance: STABLE")

tab_overview, tab_sectors, tab_gex, tab_options, tab_earnings, tab_news = st.tabs([
    "📈 Market Overview", "🔥 Alpha Sectors", "📊 GEX", "🐳 Options",
    "🎯 Earnings", "📰 News Wire"
])

# ==================== OVERVIEW ====================
with tab_overview:
    st.subheader("🗝️ Key Indices")
    key_df = market_df[market_df['Asset'].isin(["S&P 500", "SPY", "QQQ"])][['Asset', 'Price', 'Change %', 'RVOL']].round(2)
    st.dataframe(key_df.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']), hide_index=True, use_container_width=True)

    st.subheader("🌍 Global & Macro Indicators")
    global_df = market_df[market_df['Asset'].isin(GLOBAL_TICKERS.keys())].copy()
    st.dataframe(
        global_df[['Asset', 'Price', 'Change %', 'RVOL']].round(2)
            .style
            .background_gradient(cmap='RdYlGn', subset=['Change %'])
            .background_gradient(cmap='YlOrRd', subset=['RVOL']),
        hide_index=True,
        use_container_width=True
    )

    st.subheader("🚀 Magnificent 7")
    mag7_df = market_df[market_df['Asset'].isin(MAG7_TICKERS.keys())].copy().sort_values('Change %', ascending=False)
    spy_change = mag7_df[mag7_df['Asset'] == "SPY"]['Change %'].iloc[0] if not mag7_df[mag7_df['Asset'] == "SPY"].empty else 0
    mag7_df['vs SPY (%)'] = (mag7_df['Change %'] - spy_change).round(2)
    st.dataframe(mag7_df[['Asset', 'Price', 'Change %', 'vs SPY (%)', 'RVOL']].round(2)
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'vs SPY (%)', 'RVOL']),
                 hide_index=True, use_container_width=True)

    st.subheader("📉 Intraday Price Action")
    cols = st.columns(3)
    for i, (ticker, name) in enumerate([('SPY','SPY'), ('QQQ','QQQ'), ('^GSPC','S&P 500')]):
        with cols[i]:
            if ticker in intra_data['Close'].columns:
                fig = px.line(intra_data['Close'][ticker].dropna(), title=name)
                fig.update_layout(template="plotly_dark", height=400)
                st.plotly_chart(fig, use_container_width=True)

    selected_mag = st.selectbox("MAG7 Intraday Detail", list(MAG7_TICKERS.keys()))
    sym = MAG7_TICKERS[selected_mag]
    if sym in intra_data['Close'].columns:
        fig = px.line(intra_data['Close'][sym].dropna(), title=f"{selected_mag} Intraday")
        fig.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)

# ==================== SECTORS ====================
with tab_sectors:
    sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    st.dataframe(sect_data[['Asset', 'Price', 'Change %', 'RVOL']]
                 .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']),
                 hide_index=True, use_container_width=True)

# ==================== GEX ====================
with tab_gex:
    st.subheader("📊 Gamma Exposure (GEX) Analysis + Gamma Flip")
    user_ticker = st.text_input("Enter Ticker for GEX", value="SPY").upper().strip()
    if user_ticker:
        try:
            tk = yf.Ticker(user_ticker)
            options = tk.options
            if not options:
                st.warning("No options chain found.")
                st.stop()
            spot = round(tk.history(period="1d")['Close'].iloc[-1], 2)
            st.write(f"**Current Price:** ${spot}")

            all_chains = []
            for exp in options[:3]:
                ch = tk.option_chain(exp)
                c = ch.calls.assign(type='call', exp=exp)
                p = ch.puts.assign(type='put', exp=exp)
                all_chains.extend([c, p])

            df_g = pd.concat(all_chains, ignore_index=True)
            df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365.0
            df_g['GEX'] = calc_gamma_vectorized(spot, df_g['strike'].values, df_g['dte'].values,
                                                df_g['impliedVolatility'].values, 0.04, 0.01,
                                                df_g['type'].values, df_g['openInterest'].values)

            df_agg = (df_g.groupby('strike')['GEX'].sum() / 1e6).sort_index()
            df_agg = df_agg[df_agg.abs() > 0.01]

            gamma_flip = spot
            if not df_agg.empty:
                strikes = np.array(df_agg.index)
                gex_vals = np.array(df_agg.values)
                cum_gex = np.cumsum(gex_vals)
                sign_changes = np.where(np.diff(np.sign(cum_gex)) != 0)[0]
                if len(sign_changes) > 0:
                    i = sign_changes[0]
                    x1, x2 = strikes[i], strikes[i+1]
                    y1, y2 = cum_gex[i], cum_gex[i+1]
                    gamma_flip = x1 - y1 * (x2 - x1) / (y2 - y1) if (y2 - y1) != 0 else (x1 + x2) / 2
                else:
                    gamma_flip = strikes[np.argmin(np.abs(cum_gex))]
                gamma_flip = round(gamma_flip, 2)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("**Spot Price**", f"${spot}")
            with col2:
                st.metric("**Gamma Flip Level**", f"${gamma_flip}")
            with col3:
                status = "🟢 LONG GAMMA (Stable)" if spot > gamma_flip else "🔴 SHORT GAMMA (Volatile)"
                st.metric("Dealer Gamma Regime", status)

            if abs(spot - gamma_flip) <= 5:
                st.warning(f"⚠️ **Price is very close to Gamma Flip (${gamma_flip})** → Expect chop / volatility expansion!")

            fig = go.Figure(go.Bar(x=df_agg.index, y=df_agg.values,
                                   marker_color=['green' if x > 0 else 'red' for x in df_agg.values]))
            fig.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text=f"Spot ${spot}")
            fig.add_vline(x=gamma_flip, line_dash="dot", line_color="yellow", 
                          annotation_text="⚡ GAMMA FLIP", annotation_position="top left")
            fig.update_layout(template="plotly_dark", title=f"{user_ticker} Net Gamma Exposure + Gamma Flip", height=650)
            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"Error: {str(e)}")

# ==================== OPTIONS ====================
with tab_options:
    st.subheader("🐳 Put/Call Volume Ratio + Options Bias")
    pcr_df = get_pcr_data()
    if not pcr_df.empty:
        styled = pcr_df.style\
            .background_gradient(subset=['PCR'], cmap='RdYlGn_r')\
            .applymap(lambda x: 'background-color: #00ff00; color: black; font-weight:bold' if 'BUY CALLS' in str(x) else
                              'background-color: #ff4b4b; color: white; font-weight:bold' if 'BUY PUTS' in str(x) else '', 
                      subset=['Recommendation'])
        st.dataframe(styled, hide_index=True, use_container_width=True)
    else:
        st.info("Gathering options flow...")

# ==================== EARNINGS – FIXED ====================
with tab_earnings:
    st.subheader("🎯 MAG7 Earnings Overview")
    st.caption("Recent reported + upcoming earnings with EPS / Revenue / Surprise / Consensus")

    earn_df = get_mag7_earnings_enhanced()

    if not earn_df.empty:
        # 1. Create display version with formatted strings
        df_display = earn_df.copy()

        df_display['Last EPS'] = df_display['Last EPS'].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "N/A"
        )
        df_display['Consensus EPS'] = df_display['Consensus EPS'].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "N/A"
        )
        df_display['EPS Surprise'] = df_display['EPS Surprise'].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
        )
        df_display['Revenue Surprise'] = df_display['Revenue Surprise'].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
        )
        df_display['Last Revenue'] = df_display['Last Revenue'].apply(
            lambda x: f"${x/1e9:.2f}B" if pd.notna(x) and x > 0 else "N/A"
        )
        df_display['Consensus Revenue'] = df_display['Consensus Revenue'].apply(
            lambda x: f"${x/1e9:.2f}B" if pd.notna(x) and x > 0 else "N/A"
        )

        # 2. Apply styling – but bar() only on the numeric original columns
        #    We use the numeric values for bar length, but display the formatted strings

        def bar_color(val, col_name):
            if pd.isna(val):
                return ''
            pct = earn_df.loc[val.name, col_name]  # get numeric value
            if pct > 0:
                return 'background: linear-gradient(to right, transparent 0%, #5fba7d ' + str(min(pct*2, 100)) + '%)'
            elif pct < 0:
                return 'background: linear-gradient(to right, #d65f5f ' + str(min(abs(pct)*2, 100)) + '%, transparent 0%)'
            return ''

        styled = df_display.style\
            .map(bar_color, subset=['EPS Surprise'], col_name='EPS Surprise')\
            .map(bar_color, subset=['Revenue Surprise'], col_name='Revenue Surprise')\
            .applymap(
                lambda x: 'color:#00ff00; font-weight:bold' 
                    if isinstance(x, str) and '%' in x and x != "N/A" and float(x.strip('%')) > 0 else
                          'color:#ff4b4b; font-weight:bold' 
                    if isinstance(x, str) and '%' in x and x != "N/A" and float(x.strip('%')) < 0 else '',
                subset=['EPS Surprise', 'Revenue Surprise']
            )\
            .applymap(
                lambda x: 'color:#00ff00;font-weight:bold' if x == "✅ Beat" else
                          'color:#ff4b4b;font-weight:bold' if x == "❌ Miss" else '',
                subset=['Status']
            )

        st.dataframe(styled, hide_index=True, use_container_width=True)

        upcoming = earn_df[earn_df['Next Earnings'] != "Reported"]
        if not upcoming.empty:
            next_up = upcoming.iloc[0]
            st.info(f"🚀 **Next reported:** {next_up['Asset']} on **{next_up['Next Earnings']}")
    else:
        st.warning("MAG7 earnings data temporarily unavailable.")

# ==================== NEWS ====================
with tab_news:
    st.subheader("📰 Market News & Sentiment")
    headlines = get_finviz_news_stable()
    if headlines:
        total_score = 0
        for item in headlines:
            title = item.get('Title') or item.get('title') or "No title"
            url = item.get('URL') or item.get('Link') or "#"
            source = item.get('Source') or "Finviz"
            label, score = get_sentiment_score(title)
            total_score += score
            with st.expander(f"{label} | {title}"):
                st.write(f"**Source:** {source}")
                st.write(f"[Full Story]({url})")
        st.sidebar.divider()
        st.sidebar.metric("Sentiment Pulse", total_score, delta="Positive" if total_score >= 0 else "Negative")
    else:
        st.error("News feed currently unavailable.")

st_autorefresh(interval=30000, key="global_refresh")
