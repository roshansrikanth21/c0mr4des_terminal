import requests
import json

try:
    print("Testing /api/ict_analysis endpoint...")
    response = requests.get("http://localhost:8000/api/ict_analysis?ticker=^NSEI&period=60d")
    data = response.json()
    
    if data.get("status") == "success":
        ict_data = data["data"]
        print(f"Success! Received {len(ict_data)} ICT events.")
        
        # Count types
        counts = {}
        for evt in ict_data:
            t = evt.get("type", "Unknown")
            counts[t] = counts.get(t, 0) + 1
            
        print("Event Counts:", counts)
        if ict_data:
            print("Sample Event:", ict_data[0])
    else:
        print("Failed:", data)

except Exception as e:
    print(f"Error: {e}")
