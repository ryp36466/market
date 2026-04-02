import streamlit as st
import pandas as pd
import yfinance as yf
import re
from datetime import datetime

# --- 1. Configuration & UI Setup ---
st.set_page_config(layout="wide", page_title="Dynamic Alpha Radar", page_icon="⚡")

# UI Styling
st.markdown("""
    <style>
    .metric-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
    .stTable { font-size: 12px; }
    </style>
    """, unsafe_allow_html=True)

# Common words to ignore when extracting tickers
BLACKLIST = {'CEO', 'FDA', 'USA', 'IPO', 'ETF', 'SEC', 'GAAP', 'EST', 'NEWS', 'A', 'I', 'FOR', 'THE', 'AND', 'IS', 'HAS'}

# Core Market Leaders to always check
MARKET_LEADERS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "MSFT", "GOOGL", "META", "AMZN"]

# --- 2. Core Logic ---

def extract_tickers(text):
    """Finds stock symbols in text with safety for None types."""
    text = str(text) if text is not None else ""
    ticker_pattern = r'\$?\b[A-Z]{2,5}\b'
    found = re.findall(ticker_pattern, text)
    return list({t.replace('$', '') for t in found if t.replace('$', '') not in BLACKLIST})

def get_market_data(ticker):
    """Fetches volume and price data to determine conviction score."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2d")
        if df.empty or len(df) < 2:
            return None

        prev_close = df['Close'].iloc[-2]
        curr_price = df['Close'].iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        
        # Pull 10-day avg volume
        info = stock.info
        avg_vol = info.get('averageDailyVolume10Day', 1)
        
        vol_ratio = curr_vol / avg_vol
        pct_change = ((curr_price - prev_close) / prev_close) * 100
        
        # IMPACT CRITERIA: Volume > 1.5x Avg OR Price Move > 3%
        is_high = vol_ratio > 1.8 or abs(pct_change) > 3.5
        
        return {
            "Ticker": ticker,
            "Price": f"${curr_price:.2f}",
            "Change": f"{pct_change:+.2f}%",
            "Vol_Ratio": f"{vol_ratio:.2f}x",
            "Conviction": "🔥 HIGH" if is_high else "⚖️ MODERATE",
            "is_high": is_high
        }
    except:
        return None

def fetch_dynamic_movers():
    """Fetches trending tickers dynamically and combines with market leaders."""
    # We use a broader list to start, including some known active symbols
    dynamic_list = set(MARKET_LEADERS)
    
    # Discovery: Check news for SPY/QQQ to find what's being talked about right now
    for leader in ["SPY", "QQQ"]:
        try:
            news = yf.Ticker(leader).news
            for item in news[:10]:
                found = extract_tickers(item.get('title', ''))
                dynamic_list.update(found)
        except:
            continue
            
    return list(dynamic_list)

def categorize_news(headline):
    """Labels the event type of a headline."""
    catalysts = ['earnings', 'fda', 'merger', 'acquisition', 'buyback', 'offering', 'contract', 'partnership']
    strength = ['outperforming', 'leads', 'surges', 'rally', 'all-time high', 'breakout']
    weakness = ['underperforming', 'lags', 'slumps', 'tumbles', 'drop', 'crash']
    
    h = str(headline).lower()
    if any(word in h for word in catalysts): return "💡 Catalyst"
    if any(word in h for word in strength): return "📈 Bullish"
    if any(word in h for word in weakness): return "📉 Bearish"
    return "📰 News"

# --- 3. Streamlit UI Layout ---

st.title("⚡ Dynamic Market Radar")
st.caption(f"Tracking high-impact market movers for {datetime.now().strftime('%B %d, %Y')}")

# Sidebar - Quick Stats
with st.sidebar:
    st.header("Settings")
    min_vol = st.slider("Min Volume Ratio (x Avg)", 1.0, 5.0, 1.5)
    st.divider()
    st.write("📊 **Market Context**")
    for index in ["^GSPC", "^IXIC"]:
        idx_data = yf.Ticker(index).history(period="1d")
        if not idx_data.empty:
            price = idx_data['Close'].iloc[-1]
            st.metric(index.replace("^", ""), f"{price:,.2f}")

# Main Logic
if st.button('🚀 Scan for Dynamic Movers'):
    with st.spinner("Scanning markets for unusual activity..."):
        all_tickers = fetch_dynamic_movers()
        movers_found = []
        
        # Analyze every ticker found in the dynamic scan
        progress_bar = st.progress(0)
        for i, ticker in enumerate(all_tickers):
            data = get_market_data(ticker)
            if data and data['is_high']:
                # Fetch news specifically for these high-impact stocks
                news_items = yf.Ticker(ticker).news[:2]
                data['News'] = news_items
                movers_found.append(data)
            progress_bar.progress((i + 1) / len(all_tickers))

        if movers_found:
            st.subheader(f"Found {len(movers_found)} High-Impact Setups")
            
            for stock in movers_found:
                with st.expander(f"**{stock['Ticker']}** | {stock['Change']} | Vol: {stock['Vol_Ratio']}", expanded=True):
                    col1, col2 = st.columns([1, 3])
                    
                    with col1:
                        st.write(f"**Price:** {stock['Price']}")
                        st.write(f"**Conviction:** {stock['Conviction']}")
                    
                    with col2:
                        if stock.get('News'):
                            for n in stock['News']:
                                impact = categorize_news(n.get('title'))
                                st.markdown(f"**{impact}**: [{n.get('title')}]({n.get('link')})")
                        else:
                            st.write("No direct news found for this ticker.")
                st.divider()
        else:
            st.warning("No high-conviction movers found in the current scan. Try lowering the filters.")

else:
    st.info("Click 'Scan for Dynamic Movers' to find stocks impacting the market right now.")
