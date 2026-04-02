import re

def extract_tickers(headline):
    # Pattern for stock symbols (2-5 uppercase letters)
    # This looks for words like (AAPL), $TSLA, or just "NVDA"
    ticker_pattern = r'\b[A-Z]{2,5}\b'
    tickers = re.findall(ticker_pattern, headline)
    
    # Filter out common false positives (e.g., "CEO", "FDA", "USA")
    false_positives = {'CEO', 'FDA', 'USA', 'IPO', 'ETF', 'SEC', 'GAAP'}
    return [t for t in set(tickers) if t not in false_positives]


import yfinance as yf

def get_conviction_score(ticker):
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="1d", interval="1m")
        info = stock.info
        
        # Volume Check: Current Volume vs Average 10-day Volume
        avg_vol = info.get('averageDailyVolume10Day', 1)
        curr_vol = info.get('regularMarketVolume', 0)
        vol_ratio = curr_vol / avg_vol
        
        # Price Check: % Change
        prev_close = info.get('previousClose', 1)
        curr_price = info.get('regularMarketPrice', 1)
        pct_change = ((curr_price - prev_close) / prev_close) * 100
        
        return {
            "Vol_Ratio": round(vol_ratio, 2),
            "Pct_Change": round(pct_change, 2),
            "Conviction": "HIGH" if vol_ratio > 1.5 and abs(pct_change) > 3 else "MODERATE"
        }
    except:
        return None
