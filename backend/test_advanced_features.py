import sys
import os
# Ensure backend is in path
sys.path.append(os.getcwd())

def test_advanced_features():
    print("\n=== TESTING PHASE 10: INSTITUTIONAL GRADE MATH ===")
    
    ticker = "^NSEI" # Nifty 50
    print(f"Target: {ticker}")

    # 1. Advanced Quant (Monte Carlo)
    print("\n[1] Quant Engine (Monte Carlo & Bayesian)...")
    try:
        from backend.quant_engine import get_quant_analysis, BayesianMarketModel
        q_data = get_quant_analysis(ticker)
        if "risk_assessment" in q_data:
            print(f"SUCCESS: Monte Carlo VaR (95%): {q_data['risk_assessment'].get('var_95')}%")
            print(f"SUCCESS: Monte Carlo Profit Prob: {q_data['risk_assessment'].get('prob_profit')}")
        else:
            print(f"WARNING: Risk Assessment missing in {q_data.keys()}")
            
        # Bayesian Test
        bayes = BayesianMarketModel()
        bayes.update_belief(wins=5, losses=2)
        print(f"SUCCESS: Bayesian Win Prob: {bayes.update_belief(1,0)['win_probability']}")
    except Exception as e:
        print(f"FAILED: Quant Engine - {e}")

    # 2. Time Series Forecast
    print("\n[2] Time Series Forecast (SARIMA + GARCH)...")
    try:
        from backend.time_series_forecast import advanced_forecast
        ts_data = advanced_forecast(ticker, forecast_days=2)
        if "projected_close" in ts_data:
            print(f"SUCCESS: Forecasted Close: {ts_data['projected_close']}")
            print(f"SUCCESS: Volatility ({ts_data['volatility_forecast_annualized']})")
        else:
            print(f"FAILED: {ts_data}")
    except Exception as e:
        print(f"FAILED: Time Series - {e}")

    # 3. Market Microstructure
    print("\n[3] Market Microstructure (NSEPython)...")
    try:
        from backend.microstructure import analyze_market_microstructure
        micro_data = analyze_market_microstructure(ticker)
        if "error" in micro_data:
            print(f"SKIPPED: {micro_data['error']}")
        else:
            print(f"SUCCESS: PCR: {micro_data.get('pcr')}")
            print(f"SUCCESS: Signal: {micro_data.get('pcr_signal')}")
    except Exception as e:
        print(f"FAILED: Microstructure - {e}")

    # 4. Sentiment Engine
    print("\n[4] Sentiment Engine (Transformers)...")
    try:
        from backend.sentiment_engine import market_sentiment_analysis
        sent_data = market_sentiment_analysis()
        if "error" in sent_data:
             print(f"SKIPPED: {sent_data['error']}")
        else:
             print(f"SUCCESS: Sentiment Score: {sent_data.get('sentiment_score')}")
             print(f"SUCCESS: Bias: {sent_data.get('market_bias')}")
    except Exception as e:
        print(f"FAILED: Sentiment - {e}")

if __name__ == "__main__":
    test_advanced_features()
