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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    for name, url in SOURCES.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue
                
            soup = BeautifulSoup(res.content, 'html.parser')
            # Finviz news rows usually have class 'nn'
            rows = soup.find_all('tr', class_='nn')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    headline_cell = cols[1]
                    link_tag = headline_cell.find('a')
                    if link_tag:
                        headline = link_tag.text.strip()
                        link = link_tag['href']
                        combined_data.append({"Source": name, "Headline": headline, "Link": link})
        except Exception as e:
            st.error(f"Error fetching from {name}: {e}")
            continue
            
    if not combined_data:
        # Return an empty dataframe with the expected columns to avoid KeyErrors
        return pd.DataFrame(columns=["Source", "Headline", "Link"])
        
    return pd.DataFrame(combined_data).drop_duplicates(subset=['Headline'])

def categorize_news(headline):
    catalysts = ['earnings', 'fda', 'merger', 'acquisition', 'buyback', 'offering', 'contract']
    strength = ['outperforming', 'leads', 'surges', 'rally', 'all-time high', 'outpaces', 'defies']
    weakness = ['underperforming', 'lags', 'slumps', 'tumbles', 'all-time low', 'drifts', 'plunges']
    
    h = str(headline).lower()
    if any(word in h for word in catalysts):
        return "🔥 Catalyst"
    elif any(word in h for word in strength):
        return "📈 Relative Strength"
    elif any(word in h for word in weakness):
        return "📉 Relative Weakness"
    return None

# --- Streamlit UI ---
st.set_page_config(layout="wide", page_title="Alpha Feed")
st.title("⚡ Real-Time Alpha Feed")

if st.button('Scan for Market Movers'):
    with st.spinner("Scraping Finviz..."):
        df = fetch_combined_news()
        
        # FIX: Check if the column exists before applying
        if "Headline" in df.columns and not df.empty:
            df['Impact'] = df['Headline'].apply(categorize_news)
            
            # Filter for rows that actually have an impact label
            movers = df[df['Impact'].notna()]
            
            if not movers.empty:
                for _, row in movers.iterrows():
                    col1, col2, col3 = st.columns([1.5, 1, 6])
                    col1.write(f"**{row['Impact']}**")
                    col2.caption(f"[{row['Source']}]")
                    col3.markdown(f"[{row['Headline']}]({row['Link']})")
                    st.divider()
            else:
                st.info("No movers found in the current news cycle.")
        else:
            st.warning("No news data could be retrieved. Check your internet connection or if Finviz is blocking the request.")
