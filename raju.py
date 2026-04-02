import re
import yfinance as yf

def extract_tickers(headline):
    # Improved regex to handle optional '$' prefix and ensure it's a standalone word
    ticker_pattern = r'\$?\b[A-Z]{2,5}\b'
    found = re.findall(ticker_pattern, headline)
    
    # Clean the '$' and filter out common non-ticker words
    blacklist = {'CEO', 'FDA', 'USA', 'IPO', 'ETF', 'SEC', 'GAAP', 'EST', 'NEWS'}
    
    tickers = {t.replace('$', '') for t in found if t.replace('$', '') not in blacklist}
    return list(tickers)

def get_conviction_score(ticker):
    try:
        stock = yf.Ticker(ticker)
        # Fetching 2 days of data to accurately calculate previous close and current volume
        df = stock.history(period="2d")
        
        if df.empty or len(df) < 2:
            return None

        # Using the dataframe for more reliable data than stock.info
        prev_close = df['Close'].iloc[-2]
        curr_price = df['Close'].iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        
        # Pulling average volume from info (still useful for long-term averages)
        avg_vol = stock.info.get('averageDailyVolume10Day', 1)
        
        vol_ratio = curr_vol / avg_vol
        pct_change = ((curr_price - prev_close) / prev_close) * 100
        
        # Logic: High conviction if volume is 50% above avg and price moves > 3%
        is_high = vol_ratio > 1.5 and abs(pct_change) > 3
        
        return {
            "Ticker": ticker,
            "Vol_Ratio": round(vol_ratio, 2),
            "Pct_Change": f"{round(pct_change, 2)}%",
            "Conviction": "HIGH" if is_high else "MODERATE"
        }
    except Exception as e:
        # Logging the error can help debug specific ticker failures
        print(f"Error processing {ticker}: {e}")
        return None

# Quick test
headline = "NVDA surges after earnings while CEO mentions USA expansion"
tickers = extract_tickers(headline)
for t in tickers:
    print(get_conviction_score(t))
