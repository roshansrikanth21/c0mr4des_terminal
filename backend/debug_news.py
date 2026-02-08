import yfinance as yf
import json

def test_news():
    try:
        ticker = "RELIANCE.NS"
        print(f"Fetching news for {ticker}...")
        t = yf.Ticker(ticker)
        news = t.news
        
        print("News Data Found:")
        print(json.dumps(news, indent=2))
        
        if news:
            print("\nHeadlines:")
            for n in news:
                title = n.get('title')
                link = n.get('link')
                print(f"- {title} ({link})")
        else:
            print("No news found (list empty).")
            
    except Exception as e:
        print(f"Error fetching news: {e}")

if __name__ == "__main__":
    test_news()
