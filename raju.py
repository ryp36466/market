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
def check_password():
    if st.session_state.get("password_correct"):
        return True

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
    return True

if not check_password():
    st.stop()

# ========================== TICKER CONFIGS ==========================
GLOBAL_TICKERS = {
    "S&P 500 (ES)": "ES=F", 
    "Nasdaq (NQ)": "NQ=F", 
    "Dow (YM)": "YM=F", 
    "SPY": "SPY", 
    "QQQ": "QQQ", 
    "VIX": "^VIX", 
    "10Y Yield": "^TNX", 
    "DXY": "DX-Y.NYB",
    "S&P 500": "^GSPC"
}
SECTOR_TICKERS = {"Tech (XLK)": "XLK", "Financials (XLF)": "XLF", "Energy (XLE)": "XLE", "Healthcare (XLV)": "XLV", "Disc (XLY)": "XLY", "Indus (XLI)": "XLI", "Utils (XLU)": "XLU", "RE": "XLRE", "Staples (XLP)": "XLP", "Materials (XLB)": "XLB"}
MAG7_TICKERS = {"Apple": "AAPL", "MSFT": "MSFT", "Nvidia": "NVDA", "Amazon": "AMZN", "Google": "GOOGL", "Meta": "META", "Tesla": "TSLA"}
ALL_TICKERS = {**GLOBAL_TICKERS, **SECTOR_TICKERS, **MAG7_TICKERS}

# ========================== STABLE PCR FETCH ==========================
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
                results.append({
                    "Asset": label, 
                    "PCR": round(pcr, 2), 
                    "Sentiment": "🐂 Bull" if pcr < 0.85 else "🐻 Bear" if pcr > 1.15 else "⚖️ Neu"
                })
        except:
            continue
    return pd.DataFrame(results)

# ========================== SENTIMENT ENGINE ==========================
def get_sentiment_score(text):
    bull_words = ['upbeat', 'growth', 'surge', 'rally', 'beat', 'buy', 'bullish', 'expansion', 'profit', 'gain', 'positive', 'jump']
    bear_words = ['slump', 'drop', 'fall', 'miss', 'sell', 'bearish', 'contraction', 'loss', 'negative', 'inflation', 'fear', 'risk', 'sink']
    score = 0
    text = text.lower()
    for word in bull_words:
        if word in text:
            score += 1
    for word in bear_words:
        if word in text:
            score -= 1
    if score > 0:
        return "🟢 Bullish", score
    if score < 0:
        return "🔴 Bearish", score
    return "⚪ Neutral", 0

# ========================== MATH HELPERS ==========================
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
        except:
            continue
    return pd.DataFrame(rows), intra

# ========================== EARNINGS DATA ENGINE (IMPROVED) ==========================
@st.cache_data(ttl=3600)
def get_mag7_earnings():
    earnings_list = []
    now = pd.Timestamp.now(tz='America/New_York')
    
    for label, sym in MAG7_TICKERS.items():
        try:
            tk = yf.Ticker(sym)
            hist = tk.get_earnings_dates(limit=12)  # Enough to catch past + near future
            
            next_date = "TBD"
            latest_eps = "N/A"
            surprise_pct = 0.0
            status = "—"
            
            if hist is not None and not hist.empty:
                # Future earnings (if announced)
                future = hist[hist.index > now]
                if not future.empty:
                    next_date = future.index[0].strftime('%Y-%m-%d')
                
                # Most recent reported
                reported = hist.dropna(subset=['Reported EPS'])
                if not reported.empty:
                    recent = reported.iloc[0]
                    latest_eps = round(recent['Reported EPS'], 2)
                    if 'Surprise(%)' in recent:
                        surprise_pct = round(recent['Surprise(%)'], 2)
                        status = "✅ Beat" if surprise_pct > 0 else "❌ Miss" if surprise_pct < 0 else "Met"
            
            earnings_list.append({
                "Asset": label,
                "Next Date": next_date,
                "Last EPS": latest_eps,
                "Surprise (%)": surprise_pct,
                "Status": status
            })
        except:
            continue
    
    return pd.DataFrame(earnings_list)

# ========================== STABLE NEWS ENGINE ==========================
def get_finviz_news_stable():
    try:
        fnews = News()
        news_df = fnews.get_news()['news']
        return news_df.head(15).to_dict('records')
    except Exception:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
            }
            response = requests.get("https://finviz.com/news.ashx", headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", id="news-table")
            if not table:
                return []

            news_list = []
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) != 2:
                    continue
                date_cell = cells[0]
                news_cell = cells[1]

                date_text = date_cell.text.strip()
                a_tag = news_cell.find("a", class_="tab-link-news")
                if not a_tag:
                    continue

                title = a_tag.text.strip()
                url = a_tag["href"]

                source_div = news_cell.find("div", class_="news-link-right")
                source = source_div.get_text(strip=True).strip("() ") if source_div else "Finviz"

                news_list.append({
                    "Title": title,
                    "URL": url,
                    "Source": source,
                    "Date": date_text
                })

                if len(news_list) >= 15:
                    break
            return news_list
        except Exception:
            return []

# ========================== MAIN UI ==========================
market_df, intra_data = fetch_market_snapshot()
est = pytz.timezone('US/Eastern')
time_now = datetime.datetime.now(est).strftime('%H:%M:%S')

st.title("🏛️ Alpha Terminal Pro")
st.caption(f"EST {time_now} | Performance: STABLE")

tab_overview, tab_sectors, tab_gex, tab_options, tab_earnings, tab_news = st.tabs([
    "📈 Market Overview", 
    "🔥 Alpha Sectors", 
    "📊 GEX", 
    "🐳 Options", 
    "🎯 Earnings",
    "📰 News Wire"
])

# ==================== MARKET OVERVIEW TAB ====================
with tab_overview:
    st.subheader("🗝️ Key Indices (SPY / QQQ / SPX)")
    
    key_assets = ["S&P 500", "SPY", "QQQ"]
    key_df = market_df[market_df['Asset'].isin(key_assets)][['Asset', 'Price', 'Change %', 'RVOL']].copy()
    key_df[['Price', 'Change %', 'RVOL']] = key_df[['Price', 'Change %', 'RVOL']].round(2)
    
    st.dataframe(
        key_df.style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']),
        hide_index=True,
        use_container_width=True
    )
    
    st.subheader("🚀 Magnificent 7")
    
    mag7_df = market_df[market_df['Asset'].isin(MAG7_TICKERS.keys())].copy()
    mag7_df = mag7_df.sort_values('Change %', ascending=False)
    
    spy_change = market_df[market_df['Asset'] == "SPY"]['Change %'].iloc[0] if not market_df[market_df['Asset'] == "SPY"].empty else 0.0
    mag7_df['vs SPY (%)'] = (mag7_df['Change %'] - spy_change).round(2)
    
    display_cols = ['Asset', 'Price', 'Change %', 'vs SPY (%)', 'RVOL']
    mag7_df[display_cols] = mag7_df[display_cols].round(2)
    
    st.dataframe(
        mag7_df[display_cols].style.background_gradient(cmap='RdYlGn', subset=['Change %', 'vs SPY (%)', 'RVOL']),
        hide_index=True,
        use_container_width=True
    )
    
    st.subheader("📉 Intraday Price Action")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if 'SPY' in intra_data['Close'].columns:
            fig = px.line(intra_data['Close']['SPY'].dropna(), title="SPY Intraday")
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if 'QQQ' in intra_data['Close'].columns:
            fig = px.line(intra_data['Close']['QQQ'].dropna(), title="QQQ Intraday")
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
    
    with col3:
        if '^GSPC' in intra_data['Close'].columns:
            fig = px.line(intra_data['Close']['^GSPC'].dropna(), title="S&P 500 (SPX) Intraday")
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("🔍 MAG7 Intraday Detail")
    selected_mag = st.selectbox("Select MAG7 Stock for Intraday Chart", list(MAG7_TICKERS.keys()))
    sym = MAG7_TICKERS[selected_mag]
    
    if sym in intra_data['Close'].columns:
        fig = px.line(intra_data['Close'][sym].dropna(), title=f"{selected_mag} Intraday")
        fig.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)

# ==================== ALPHA SECTORS TAB ====================
with tab_sectors:
    sect_data = market_df[market_df['Asset'].isin(SECTOR_TICKERS.keys())].copy()
    st.dataframe(
        sect_data[['Asset', 'Price', 'Change %', 'RVOL']]
        .style.background_gradient(cmap='RdYlGn', subset=['Change %', 'RVOL']),
        hide_index=True,
        use_container_width=True
    )

# ==================== GEX TAB ====================
with tab_gex:
    st.subheader("📊 Gamma Exposure (GEX) Analysis")
    
    user_ticker = st.text_input(
        "Enter Ticker Symbol for GEX (e.g. SPY, QQQ, NVDA, AAPL, TSLA, XLK, IWM...)", 
        value="SPY",
        help="Most liquid underlyings work best (SPY, QQQ, MAG7, sector ETFs). Less liquid stocks may have sparse/no options data."
    ).upper().strip()
    
    if not user_ticker:
        st.info("Enter a valid ticker symbol to analyze GEX.")
        st.stop()
    
    try:
        tk = yf.Ticker(user_ticker)
        options = tk.options
        if not options:
            st.warning(f"No options chain available for {user_ticker}. Try a stock/ETF with active options (e.g. SPY, NVDA).")
            st.stop()
        
        spot = tk.history(period="1d")['Close'].iloc[-1]
        spot = round(spot, 2)
        
        st.write(f"**Current Price:** ${spot}")
        
        all_chains = []
        for exp in options[:3]:
            try:
                ch = tk.option_chain(exp)
                c, p = ch.calls, ch.puts
                c = c.assign(type='call', exp=exp)
                p = p.assign(type='put', exp=exp)
                all_chains.extend([c, p])
            except:
                continue
        
        if not all_chains:
            st.warning(f"No usable options data found for {user_ticker} in near-term expirations.")
            st.stop()
        
        df_g = pd.concat(all_chains, ignore_index=True)
        
        df_g['dte'] = (pd.to_datetime(df_g['exp']).dt.tz_localize(None) - datetime.datetime.now()).dt.days / 365.0
        
        df_g['GEX'] = calc_gamma_vectorized(
            S=spot,
            K=df_g['strike'].values,
            T=df_g['dte'].values,
            v=df_g['impliedVolatility'].values,
            r=0.04,
            q=0.01,
            types=df_g['type'].values,
            OI=df_g['openInterest'].values
        )
        
        df_agg = df_g.groupby('strike')['GEX'].sum() / 1e6
        df_agg = df_agg[df_agg.abs() > 0.01]
        
        df_agg = df_agg.sort_index()
        
        colors = ['green' if x > 0 else 'red' for x in df_agg.values]
        
        fig_gex = go.Figure(go.Bar(
            x=df_agg.index,
            y=df_agg.values,
            marker_color=colors,
            hovertemplate='Strike: $%{x}<br>Net GEX: %{y:.2f}M<extra></extra>'
        ))
        
        fig_gex.add_vline(x=spot, line_dash="dash", line_color="white", annotation_text=f"Spot ${spot}")
        
        fig_gex.update_layout(
            template="plotly_dark",
            title=f"{user_ticker} Net Gamma Exposure (Near-Term: {len(options[:3])} Expiries)",
            xaxis_title="Strike Price",
            yaxis_title="Net GEX ($M)",
            bargap=0.05,
            height=600
        )
        
        st.plotly_chart(fig_gex, use_container_width=True)
        
        st.subheader("🔼 Top Positive / Negative Gamma Levels")
        top_pos = df_agg[df_agg > 0].nlargest(10)
        top_neg = df_agg[df_agg < 0].nsmallest(10)
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Positive Gamma Walls (Support)**")
            if not top_pos.empty:
                st.dataframe(top_pos.reset_index().rename(columns={'strike': 'Strike', 0: 'GEX ($M)'}).round(2))
            else:
                st.info("No significant positive gamma")
        
        with col2:
            st.write("**Negative Gamma Walls (Resistance)**")
            if not top_neg.empty:
                st.dataframe(top_neg.reset_index().rename(columns={'strike': 'Strike', 0: 'GEX ($M)'}).round(2))
            else:
                st.info("No significant negative gamma")
                
    except Exception as e:
        st.error(f"Failed to fetch data for {user_ticker}. Error: {str(e)}")
        st.info("Common issues: Invalid ticker, no options chain, or temporary yfinance API issue.")

# ==================== OPTIONS TAB ====================
with tab_options:
    st.subheader("🐳 Put/Call Volume Ratio")
    pcr_df = get_pcr_data()
    if not pcr_df.empty:
        st.dataframe(
            pcr_df.style.background_gradient(subset=['PCR'], cmap='RdYlGn_r'),
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("Gathering options flow...")

# ==================== EARNINGS TAB ====================
# ==================== EARNINGS TAB ====================
with tab_earnings:
    st.subheader("🎯 Magnificent 7 Earnings Intelligence")
    st.caption("Recent EPS performance, surprise history, and upcoming report dates.")
    
    earn_df = get_mag7_earnings()
    
    if not earn_df.empty:
        styled_df = earn_df.style\
            .background_gradient(cmap='RdYlGn', subset=['Surprise (%)'])\
            .applymap(
                lambda x: 'color: #00ff00; font-weight: bold;' if x == "✅ Beat" 
                else ('color: #ff4b4b; font-weight: bold;' if x == "❌ Miss" else ''),
                subset=['Status']
            )
        
        st.dataframe(styled_df, hide_index=True, use_container_width=True)
        
        upcoming = earn_df[earn_df['Next Date'] != "TBD"]
        if not upcoming.empty:
            # Sort by parsed date to ensure correct ordering
            upcoming['parsed_date'] = pd.to_datetime(upcoming['Next Date'])
            next_up = upcoming.sort_values('parsed_date').iloc[0]
            
            # Fixed days_left calculation (safe type handling)
            next_date = pd.to_datetime(next_up['Next Date'])
            days_left = (next_date - pd.Timestamp.today()).days
            
            if days_left == 0:
                day_text = "today"
            elif days_left == 1:
                day_text = "tomorrow"
            elif days_left < 0:
                day_text = f"{abs(days_left)} days ago (already reported?)"
            else:
                day_text = f"in {days_left} days"
            
            st.success(f"🚀 **Next Catalyst:** {next_up['Asset']} reports on **{next_up['Next Date']}** ({day_text})")
        else:
            st.info("No confirmed upcoming earnings dates at this time (common outside reporting season).")
    else:
        st.warning("Earnings data temporarily unavailable.")

# ==================== NEWS TAB ====================
with tab_news:
    st.subheader("📰 Market News & Sentiment")
    headlines = get_finviz_news_stable()

    if headlines:
        total_score = 0
        for item in headlines:
            title = item.get('Title') or item.get('title') or "No title"
            url = item.get('URL') or item.get('Link') or item.get('link') or "#"
            source = item.get('Source') or item.get('source') or "Finviz"

            label, score = get_sentiment_score(title)
            total_score += score

            with st.expander(f"{label} | {title}"):
                st.write(f"**Source:** {source}")
                st.write(f"[Full Story]({url})")

        st.sidebar.divider()
        sentiment_direction = "Positive" if total_score >= 0 else "Negative"
        st.sidebar.metric("Sentiment Pulse", total_score, delta=sentiment_direction)
    else:
        st.error("News feed currently unavailable (Finviz may be rate-limiting requests).")

st_autorefresh(interval=30000, key="global_refresh")
