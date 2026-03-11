"""
CLI utility to backfill persisted historical datasets.

Usage examples:
  python backend/backfill_historical_data.py --ticker ^NSEI --interval 15m --period 60d
  python backend/backfill_historical_data.py --ticker AAPL --interval 1d --period 5y --force
"""

import argparse
import json

from backend.services.historical_data_service import historical_data_service


def main():
    parser = argparse.ArgumentParser(description="Backfill historical OHLCV data")
    parser.add_argument("--ticker", default="^NSEI", help="Ticker symbol (default: ^NSEI)")
    parser.add_argument("--interval", default="1d", help="Interval (default: 1d)")
    parser.add_argument("--period", default="2y", help="Provider period (default: 2y)")
    parser.add_argument("--force", action="store_true", help="Replace existing dataset instead of merging")
    args = parser.parse_args()

    result = historical_data_service.backfill(
        ticker=args.ticker,
        period=args.period,
        interval=args.interval,
        force_refresh=args.force,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

