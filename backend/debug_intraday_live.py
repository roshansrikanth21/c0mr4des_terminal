import requests
import json
from datetime import datetime
import pytz

try:
    print(f"Testing /api/intraday endpoint at {datetime.now()}...")
    
    # 1. Check Server Time Logic
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    print(f"Server Internal Time (IST): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 2. Call API
    response = requests.get("http://localhost:8000/api/intraday?ticker=^NSEI&interval=5m", timeout=15)
    
    if response.status_code != 200:
        print(f"Error: API returned {response.status_code}")
        print(response.text)
        exit()
        
    data = response.json()
    
    # 3. Analyze Response
    market_open = data.get("market_open")
    history = data.get("data", [])
    
    print(f"API says Market Open: {market_open}")
    print(f"Data Points Returned: {len(history)}")
    
    if history:
        last_candle = history[-1]
        print(f"Latest Candle Time: {last_candle['time']}")
        print(f"Latest Price: {last_candle['price']}")
    else:
        print("WARNING: No data returned from Yahoo Finance.")
        
    print("-" * 30)
    print("Full API Response Keys:", data.keys())

except Exception as e:
    print(f"CRITICAL FAILIURE: {e}")
