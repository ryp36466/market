import streamlit as st
import pandas as pd
import yfinance as yf
import re

# --- 1. Configuration & Setup ---
st.set_page_config(layout="wide", page_title="Alpha Feed & Conviction")

# Common words to ignore when extracting tickers
BLACKLIST = {'CEO', 'FDA', 'USA', 'IPO', 'ETF', 'SEC', 'GAAP', 'EST', 'NEWS', 'A', 'I', 'FOR', 'THE', 'AND'}

# Tickers to pull news from if the broad scrape fails
WATCHLIST = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "MSFT", "GOOGL", "META"]

# --- 2. Core Functions ---

def extract_tickers(text):
    """Finds stock symbols like AAPL or $TSLA in text with safety for None types."""
    # Ensure text is a string to prevent TypeError in re.findall
    text = str(text) if text is not None else ""
    
    ticker_pattern = r'\$?\b[A-Z]{2,5}\b'
    found = re.findall(ticker_pattern, text)
    
    # Clean the '$' and filter out common non-ticker words
    tickers = {t.replace('$', '') for t in found if t.replace('$', '') not in BLACKLIST}
    return list(tickers)

def get_market_data(ticker):
    """Fetches volume and price data to determine conviction."""
    try:
        stock = yf.Ticker(ticker)
        # Fetching 2 days to compare previous close vs current
        df = stock.history(period="2d")
        
        if df.empty or len(df) < 2:
            return None

        prev_close = df['Close'].iloc[-2]
        curr_price = df['Close'].iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        
        # Pull 10-day avg volume from info
        avg_vol = stock.info.get('averageDailyVolume10Day', 1)
        
        vol_ratio = curr_vol / avg_vol
        pct_change = ((curr_price - prev_close) / prev_close) * 100
        
        # High Conviction = Vol > 1.5x Avg AND Price Move > 3%
        is_high = vol_ratio > 1.5 and abs(pct_change) > 3
        
        return {
            "Ticker": ticker,
            "Price": f"${curr_price:.2f}",
            "Change": f"{pct_change:.2f}%",
            "Vol_Ratio": round(vol_ratio, 2),
            "Conviction": "🔥 HIGH" if is_high else "⚖️ MODERATE"
        }
    except Exception:
        return None

def fetch_news():
    """Fetches news via yfinance API (stable and non-blocking)."""
    news_list = []
    for ticker in WATCHLIST:
        try:
            t_obj = yf.Ticker(ticker)
            # Get the top 3 news items for each ticker in the watchlist
            for item in t_obj.news[:3]: 
                news_list.append({
                    "Symbol": ticker,
                    "Headline": item.get('title'),
                    "Link": item.get('link')
                })
        except Exception:
            continue
            
    if not news_list:
        return pd.DataFrame(columns=["Symbol", "Headline", "Link"])
        
    return pd.DataFrame(news_list).drop_duplicates(subset=['Headline'])

def categorize_news(headline):
    """Labels the sentiment or event type of a headline."""
    catalysts = ['earnings', 'fda', 'merger', 'acquisition', 'buyback', 'offering', 'contract']
    strength = ['outperforming', 'leads', 'surges', 'rally', 'all-time high', 'outpaces', 'defies']
    weakness = ['underperforming', 'lags', 'slumps', 'tumbles', 'all-time low', 'drifts', 'plunges']
    
    h = str(headline).lower()
    if any(word in h for word in catalysts): return "🔥 Catalyst"
    if any(word in h for word in strength): return "📈 Strength"
    if any(word in h for word in weakness): return "📉 Weakness"
    return "📰 Neutral"

# --- 3. Streamlit UI Layout ---

st.title("⚡ Alpha Feed & Market Conviction")

# Sidebar for manual ticker analysis
st.sidebar.header("Manual Ticker Check")
manual_ticker = st.sidebar.text_input("Enter Ticker (e.g. NVDA)").upper()
if manual_ticker:
    data = get_market_data(manual_ticker)
    if data:
        st.sidebar.json(data)
    else:
        st.sidebar.error("Market data not found for this ticker.")

# Main News Scanner Button
if st.button('🔄 Scan Market News'):
    with st.spinner("Fetching latest news and calculating conviction..."):
        df_news = fetch_news()
        
        if not df_news.empty:
            for _, row in df_news.iterrows():
                headline = row.get('Headline', "No Headline Available")
                symbol = row.get('Symbol', "N/A")
                link = row.get('Link', "#")
                
                # Analyze the headline for extra tickers and impact
                detected = extract_tickers(headline)
                impact = categorize_news(headline)
                
                # UI Layout for each News Item
                with st.container():
                    col1, col2, col3 = st.columns([1, 1, 4])
                    col1.write(f"**{impact}**")
                    col2.write(f"`{symbol}`")
                    col3.markdown(f"[{headline}]({link})")
                    
                    # If other tickers are found in the headline, show their conviction scores
                    if detected:
                        scores = []
                        for det_t in detected:
                            s = get_market_data(det_t)
                            if s: scores.append(s)
                        
                        if scores:
                            st.caption("🔍 **Market Data for Detected Tickers:**")
                            st.table(pd.DataFrame(scores))
                    
                    st.divider()
        else:
            st.warning("No news data retrieved. Please check your connection or watchlist.")
else:
    st.info("Click the button above to scan for the latest high-conviction setups.")
