from backend.quant_engine import get_quant_analysis
import json

def test_quant():
    ticker = "RELIANCE.NS"
    print(f"Testing Quant Engine for {ticker}...")
    
    try:
        data = get_quant_analysis(ticker)
        print(json.dumps(data, indent=2))
        
        if "error" in data:
            print("FAILED: Quant Engine returned error.")
        else:
            print("SUCCESS: Quant Engine Metrics Calculated.")
            print(f"Drift Score: {data['regime']['drift_score']}")
            print(f"Entropy: {data['chaos_theory']['entropy']}")
            
    except Exception as e:
        print(f"CRITICAL FAILURE: {e}")

if __name__ == "__main__":
    test_quant()
