import yfinance as yf
import pandas as pd

ticker = "^NSEI"
print(f"Testing yf.download for {ticker}...")

df = yf.download(ticker, period="1wk", interval="1d", progress=False)
print("\n--- No group_by ---")
print(f"Empty: {df.empty}")
print(f"Columns: {df.columns.tolist()}")
print(f"Type: {type(df.columns)}")

df_gb = yf.download(ticker, period="1wk", interval="1d", progress=False, group_by='ticker')
print("\n--- With group_by='ticker' ---")
print(f"Empty: {df_gb.empty}")
print(f"Columns: {df_gb.columns.tolist()}")
print(f"Type: {type(df_gb.columns)}")
if isinstance(df_gb.columns, pd.MultiIndex):
    print(f"Levels: {df_gb.columns.levels}")
