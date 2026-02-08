import requests
print("Testing internet connection...")
try:
    r = requests.get("https://www.google.com", timeout=5)
    print(f"Internet OK! Status: {r.status_code}")
except Exception as e:
    print(f"Internet FAILED: {e}")

print("\nTesting Yahoo Finance direct...")
try:
    r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/^NSEI", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
    print(f"Yahoo OK! Status: {r.status_code}")
except Exception as e:
    print(f"Yahoo FAILED: {e}")
