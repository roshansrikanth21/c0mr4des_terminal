
from backend.backtest import Backtester
import pandas as pd
import json

try:
    tester = Backtester(ticker="^NSEI", interval="15m", period="5d")
    tester.fetch_data()
    tester.run()
    results = tester.get_results()
    
    # Try to simulate JSON dumping to catch errors
    try:
        json_output = json.dumps(results, default=str)
        print("JSON serialization successful with default=str")
        # Check for Infinity
        if 'Infinity' in json_output:
            print("WARNING: 'Infinity' found in JSON output")
        if 'NaN' in json_output:
            print("WARNING: 'NaN' found in JSON output")
        print(json_output[:200]) # Print start
    except Exception as e:
        print(f"JSON serialization FAILED: {e}")

    print("\nSample Trade:")
    if results.get('trades'):
        print(results['trades'][0])
except Exception as e:
    print(f"Backtest execution failed: {e}")
