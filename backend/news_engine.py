import yfinance as yf
from datetime import datetime

def fetch_market_news(ticker_symbol: str, limit: int = 5) -> str:
    """
    Fetches latest news for a given ticker using yfinance.
    Returns a formatted string summary.
    """
    try:
        # Handle index tickers like NSE/NIFTY
        if ticker_symbol.upper() in ["NIFTY", "NIFTY50", "NSE", "^NSEI"]:
            ticker_symbol = "^NSEI"
        elif ticker_symbol.upper() in ["BANKNIFTY", "BANK NIFTY", "^NSEBANK"]:
            ticker_symbol = "^NSEBANK"
        elif not ticker_symbol.endswith(".NS") and not ticker_symbol.startswith("^") and len(ticker_symbol) < 6:
            # Assume NSE for Indian stocks if generic
            # But safer to just try as is, or search. 
            # For now, let's append .NS if it looks like an Indian stock symbol (generic heuristic)
            pass 

        t = yf.Ticker(ticker_symbol)
        news_items = t.news
        
        if not news_items:
            return f"No recent news found for {ticker_symbol}."

        summary = f"Latest Market News for {ticker_symbol}:\n"
        
        count = 0
        for item in news_items:
            if count >= limit: 
                break
                
            title = item.get('title', 'No Title')
            # Extract summary/text. 'summary' key often contains description
            # Sometimes yfinance returns 'relatedTickers' etc.
            
            # Simple cleaning
            published = item.get('providerPublishTime', 0)
            date_str = ""
            if published:
                date_str = datetime.fromtimestamp(published).strftime('%Y-%m-%d %H:%M')
            
            summary += f"- [{date_str}] {title}\n"
            count += 1
            
        return summary

    except Exception as e:
        return f"Error fetching news: {str(e)}"
