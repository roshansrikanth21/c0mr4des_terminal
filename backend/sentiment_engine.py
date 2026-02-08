from transformers import pipeline
import numpy as np

# Initialize pipeline once (global) if possible to avoid reload lag
# Use 'distilbert-base-uncased-finetuned-sst-2-english' (default) or 'finbert'
# We use default for now to ensure compatibility
try:
    sentiment_pipeline = pipeline("sentiment-analysis", model="distilbert/distilbert-base-uncased-finetuned-sst-2-english")
    TRANSFORMERS_AVAILABLE = True
except Exception as e:
    print(f"Transformers Init Failed: {e}")
    TRANSFORMERS_AVAILABLE = False

def market_sentiment_analysis(headlines=None):
    """
    Analyze financial news sentiment using Transformers.
    """
    if not TRANSFORMERS_AVAILABLE:
        return {"error": "Transformers model not loaded."}
    
    if not headlines:
        # Default mock headlines if none provided (for testing)
        headlines = [
            "Market hits all-time high amidst strong inflows",
            "Inflation concerns rise as oil prices surge",
            "FIIs sell net 2000 crores today"
        ]
    
    try:
        results = sentiment_pipeline(headlines)
        
        # Calculate aggregate score
        # Label: POSITIVE / NEGATIVE
        # Score: 0.99
        
        scores = []
        for res in results:
            score = res['score']
            if res['label'] == 'NEGATIVE':
                score = -score
            scores.append(score)
            
        avg_score = np.mean(scores)
        
        market_bias = "NEUTRAL"
        if avg_score > 0.3: market_bias = "BULLISH"
        elif avg_score < -0.3: market_bias = "BEARISH"
        
        return {
            "sentiment_score": round(float(avg_score), 4),
            "market_bias": market_bias,
            "details": [{"headline": h, "label": r['label'], "score": round(r['score'], 2)} for h, r in zip(headlines, results)]
        }

    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print(market_sentiment_analysis())
