import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

SOURCES = {
    "All": "https://finviz.com/news.ashx",
    "Market": "https://finviz.com/news.ashx?v=3",
    "Stocks": "https://finviz.com/news.ashx?v=4",
    "Crypto": "https://finviz.com/news.ashx?v=5",
    "ETFs": "https://finviz.com/news.ashx?v=6"
}

def fetch_combined_news():
    combined_data = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for name, url in SOURCES.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.content, 'html.parser')
            rows = soup.find_all('tr', class_='nn')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    headline = cols[1].text.strip()
                    link = cols[1].find('a')['href'] if cols[1].find('a') else ""
                    combined_data.append({"Source": name, "Headline": headline, "Link": link})
        except:
            continue
    return pd.DataFrame(combined_data).drop_duplicates(subset=['Headline'])

def categorize_news(headline):
    # Category 1: Hard Catalysts (Huge News)
    catalysts = ['earnings', 'fda', 'merger', 'acquisition', 'buyback', 'offering', 'contract']
    # Category 2: Relative Strength/Momentum
    strength = ['outperforming', 'leads', 'surges', 'rally', 'all-time high', 'outpaces', 'defies']
    # Category 3: Relative Weakness
    weakness = ['underperforming', 'lags', 'slumps', 'tumbles', 'all-time low', 'drifts', 'plunges']

    h = headline.lower()
    if any(word in h for word in catalysts):
        return "🔥 Catalyst"
    elif any(word in h for word in strength):
        return "📈 Relative Strength"
    elif any(word in h for word in weakness):
        return "📉 Relative Weakness"
    return None

# --- Streamlit UI ---
st.set_page_config(layout="wide")
st.title("⚡ Real-Time Alpha Feed")

if st.button('Scan for Market Movers'):
    df = fetch_combined_news()
    # Apply the categorization
    df['Impact'] = df['Headline'].apply(categorize_news)
    # Filter out the "None" (fluff news)
    movers = df[df['Impact'].notna()]

    if not movers.empty:
        for _, row in movers.iterrows():
            # Use columns for a clean dashboard look
            col1, col2, col3 = st.columns([1.5, 1, 6])
            col1.write(f"**{row['Impact']}**")
            col2.caption(f"[{row['Source']}]")
            col3.markdown(f"[{row['Headline']}]({row['Link']})")
            st.divider()
    else:
        st.info("No relative strength or catalyst news found in the current cycle.")
