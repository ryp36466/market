import streamlit as st
import re
import yfinance as yf
import pandas as pd

# --- Configuration ---
st.set_page_config(page_title="Market Conviction Dashboard", layout="wide")

def extract_tickers(headline):
    # Regex to catch tickers like AAPL or $TSLA
    ticker_pattern = r'\$?\b[A-Z]{2,5}\b'
    found = re.findall(ticker_pattern, headline)
    
    # Filter out common non-ticker words
    blacklist = {'CEO', 'FDA', 'USA', 'IPO', 'ETF', 'SEC', 'GAAP', 'EST', 'NEWS', 'A', 'I'}
    
    tickers = {t.replace('$', '') for t in found if t.replace('$', '') not in blacklist}
    return list(tickers)

def get_conviction_score(ticker):
    try:
        stock = yf.Ticker(ticker)
        # Get 2 days of history for price/volume comparison
        df = stock.history(period="2d")
        
        if df.empty or len(df) < 2:
            return None

        prev_close = df['Close'].iloc[-2]
        curr_price = df['Close'].iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        
        # Get 10-day avg volume from info
        avg_vol = stock.info.get('averageDailyVolume10Day', 1)
        
        vol_ratio = curr_vol / avg_vol
        pct_change = ((curr_price - prev_close) / prev_close) * 100
        
        # Logic for High Conviction
        is_high = vol_ratio > 1.5 and abs(pct_change) > 3
        
        return {
            "Ticker": ticker,
            "Price": f"${round(curr_price, 2)}",
            "Vol_Ratio": round(vol_ratio, 2),
            "Pct_Change": f"{round(pct_change, 2)}%",
            "Conviction": "🔥 HIGH" if is_high else "⚖️ MODERATE"
        }
    except Exception as e:
        return None

# --- Streamlit UI ---
st.title("📈 Stock Conviction Analyzer")
st.markdown("Extracts tickers from headlines and checks for unusual volume and price action.")

# User Input
headline_input = st.text_input("Paste News Headline here:", "NVDA surges after earnings while TSLA dips")

if headline_input:
    tickers = extract_tickers(headline_input)
    
    if not tickers:
        st.info("No tickers detected in that headline.")
    else:
        results = []
        with st.spinner(f'Analyzing {", ".join(tickers)}...'):
            for t in tickers:
                score = get_conviction_score(t)
                if score:
                    results.append(score)
        
        if results:
            # Display results in a nice table
            df_display = pd.DataFrame(results)
            st.table(df_display) 
        else:
            st.error("Could not fetch market data for the detected tickers.")

# Sidebar Info
st.sidebar.header("Logic Settings")
st.sidebar.write("✅ **High Conviction** = Volume > 1.5x Avg AND Price Move > 3%")
