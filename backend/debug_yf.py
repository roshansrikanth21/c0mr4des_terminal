import yfinance as yf
print(f"yfinance version: {yf.__version__}")

tickers = ["^NSEI", "RELIANCE.NS"]
for t in tickers:
    print(f"\nAttempting Ticker().history() for {t}...")
    try:
        ticker_obj = yf.Ticker(t)
        # 5 days, 15m interval
        data = ticker_obj.history(period="5d", interval="15m")
        if data.empty:
            print(f"{t}: Data is empty!")
        else:
            print(f"{t}: Success! Rows: {len(data)}")
            print(data.head(2))
    except Exception as e:
        print(f"{t}: Error: {e}")
