import pandas as pd
import numpy as np
import yfinance as yf
import streamlit as st

def compute_atr(df, period=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

@st.cache_data(ttl=120)
def build_dynamic_trade_universe(symbols, min_price=5, min_dollar_vol=20_000_000, min_rvol=1.5, min_atr_abs=4.0, min_atr_pct=5.0):
    rows = []

    for sym in symbols:
        try:
            hist = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=False)
            if hist.empty or len(hist) < 30:
                continue

            close = float(hist['Close'].iloc[-1])
            atr = float(compute_atr(hist, 14).iloc[-1])
            atr_pct = (atr / close) * 100 if close > 0 else 0

            avg_vol_20 = float(hist['Volume'].tail(20).mean())
            dollar_vol = avg_vol_20 * close

            intraday = yf.download(sym, period="1d", interval="5m", progress=False, prepost=True, auto_adjust=False)
            today_vol = float(intraday['Volume'].sum()) if not intraday.empty else 0.0
            rvol = today_vol / avg_vol_20 if avg_vol_20 > 0 else 0.0

            if close < min_price:
                continue
            if dollar_vol < min_dollar_vol:
                continue
            if rvol < min_rvol:
                continue
            if not (atr >= min_atr_abs or atr_pct >= min_atr_pct):
                continue

            rows.append({
                "Symbol": sym,
                "Close": round(close, 2),
                "ATR_14": round(atr, 2),
                "ATR_%": round(atr_pct, 2),
                "AvgVol20": int(avg_vol_20),
                "DollarVol20": round(dollar_vol, 0),
                "RVOL": round(rvol, 2),
            })

        except Exception:
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    return df.sort_values(["RVOL", "ATR_%", "DollarVol20"], ascending=False).reset_index(drop=True)
