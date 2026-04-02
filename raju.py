import streamlit as st
import yfinance as yf
from datetime import datetime

# Configure the Streamlit page
st.set_page_config(page_title="Day Trading News Tracker", page_icon="📈", layout="centered")

st.title("📈 Yahoo Finance News Scraper")
st.markdown("Fetch the latest news for Stocks and ETFs to power your day trading strategies.")

# User input for the ticker symbol
ticker_input = st.text_input("Enter Ticker Symbol (e.g., AAPL, SPY, QQQ):", value="SPY").upper()

if st.button("Get Latest News"):
    if ticker_input:
        with st.spinner(f"Fetching news for {ticker_input}..."):
            try:
                # Fetch data using yfinance
                ticker = yf.Ticker(ticker_input)
                news_items = ticker.news
                
                if news_items:
                    st.subheader(f"Latest News for {ticker_input}")
                    for article in news_items:
                        title = article.get("title", "No Title")
                        publisher = article.get("publisher", "Unknown Publisher")
                        link = article.get("link", "#")
                        
                        # Convert Unix timestamp to readable date/time
                        pub_time = article.get("providerPublishTime")
                        if pub_time:
                            formatted_time = datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            formatted_time = "Unknown Time"
                        
                        # Display the news article
                        st.markdown(f"### [{title}]({link})")
                        st.caption(f"🏢 **Publisher:** {publisher} | 🕒 **Time:** {formatted_time}")
                        st.divider()
                else:
                    st.warning(f"No recent news found for {ticker_input}. Please check if the ticker is correct.")
            except Exception as e:
                st.error(f"An error occurred while fetching data: {e}")
    else:
        st.warning("Please enter a ticker symbol.")
