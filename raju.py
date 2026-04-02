import streamlit as st
import pandas as pd
import yfinance as yf
import re

# --- 1. Configuration & Setup ---
st.set_page_config(layout="wide", page_title="Alpha Feed & Conviction")

# Common words to ignore when extracting tickers
BLACKLIST = {'CEO', 'FDA', 'USA', 'IPO', 'ETF', 'SEC', 'GAAP', 'EST', 'NEWS', 'A', 'I', 'FOR'}

# Tickers to pull news from if the broad scrape fails
WATCHLIST = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "MSFT", "GOOGL", "META"]

# --- 2. Core Functions ---

def extract_tickers(text):
    """Finds stock symbols like AAPL or $TSLA in text."""
    ticker_pattern = r'\$?\b[A-Z]{2,5}\b'
    found = re.findall(ticker_pattern, text)
    tickers = {t.replace('$', '') for t in found if t.replace('$', '') not in BLACKLIST}
    return list(tickers)

def get_market_data(ticker):
    """Fetches volume and price data to determine conviction."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2d")
        if df.empty or len(df) < 2:
            return None

        prev_close = df['Close'].iloc[-2]
        curr_price = df['Close'].iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        avg_vol = stock.info.get('averageDailyVolume10Day', 1)
        
        vol_ratio = curr_vol / avg_vol
        pct_change = ((curr_price - prev_close) / prev_close) * 100
        
        # High Conviction = Vol > 1.5x and Price move > 3%
        is_high = vol_ratio > 1.5 and abs(pct_change) > 3
        
        return {
            "Ticker": ticker,
            "Price": f"${curr_price:.2f}",
            "Change": f"{pct_change:.2f}%",
            "Vol_Ratio": round(vol_ratio, 2),
            "Conviction": "🔥 HIGH" if is_high else "⚖️ MODERATE"
        }
    except:
        return None

def fetch_news():
    """Fetches news via yfinance (more stable than scraping Finviz directly)."""
    news_list = []
    for ticker in WATCHLIST:
        try:
            t_obj = yf.Ticker(ticker)
            for item in t_obj.news[:3]: # Get top 3 news per watchlist item
                news_list.append({
                    "Symbol": ticker,
                    "Headline": item.get('title'),
                    "Link": item.get('link')
                })
        except:
            continue
    return pd.DataFrame(news_list).drop_duplicates(subset=['Headline'])

def categorize_news(headline):
    """Labels the sentiment/type of headline."""
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

# Sidebar for manual checks
st.sidebar.header("Manual Ticker Check")
manual_ticker = st.sidebar.text_input("Enter Ticker (e.g. NVDA)").upper()
if manual_ticker:
    data = get_market_data(manual_ticker)
    if data:
        st.sidebar.write(data)
    else:
        st.sidebar.error("Data not found.")

# Main News Scanner
if st.button('🔄 Scan Market News'):
    with st.spinner("Fetching latest news and calculating conviction..."):
        df_news = fetch_news()
        
        if not df_news.empty:
            for _, row in df_news.iterrows():
                # Analyze tickers within the headline
                detected = extract_tickers(row['Headline'])
                impact = categorize_news(row['Headline'])
                
                # Create a clean row for each news item
                with st.container():
                    col1, col2, col3 = st.columns([1, 1, 4])
                    col1.write(f"**{impact}**")
                    col2.write(f"`{row['Symbol']}`")
                    col3.markdown(f"[{row['Headline']}]({row['Link']})")
                    
                    # If tickers are found, show their conviction score right below the headline
                    if detected:
                        scores = []
                        for det_t in detected:
                            s = get_market_data(det_t)
                            if s: scores.append(s)
                        if scores:
                            st.caption("🔍 **Ticker Analysis:**")
                            st.dataframe(pd.DataFrame(scores), hide_index=True)
                    
                    st.divider()
        else:
            st.warning("No news data retrieved. Please try again in a moment.")

else:
    st.info("Click 'Scan Market News' to start.")
