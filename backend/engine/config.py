"""Market constants for Indian index options. One place, verified Oct 2026.

Sources: NSE circular FAOP70616 (NIFTY lot 75 -> 65 from Jan 2026 series),
BSE (SENSEX lot 20), SEBI expiry-day rationalisation (NSE weekly = Tuesday,
BSE weekly = Thursday from Sep 2025), Budget 2026 STT (0.15% on option sell premium).
Re-check these every quarter; exchanges revise lot sizes twice a year.
"""
from dataclasses import dataclass
from datetime import date, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    yf_symbol: str          # spot index on Yahoo (fallback feed, ~delayed, no volume)
    angel_spot_token: str   # Angel One SmartAPI spot index token
    angel_exchange: str     # exchange for spot quotes
    option_exchange: str    # NFO / BFO
    lot_size: int
    strike_step: int
    weekly_expiry_weekday: int  # Monday=0
    angel_name: str         # 'name' field in Angel scrip master for options


INSTRUMENTS = {
    "NIFTY": Instrument("NIFTY", "NIFTY 50", "^NSEI", "99926000", "NSE", "NFO",
                        lot_size=65, strike_step=50, weekly_expiry_weekday=1, angel_name="NIFTY"),
    "SENSEX": Instrument("SENSEX", "SENSEX", "^BSESN", "99919000", "BSE", "BFO",
                         lot_size=20, strike_step=100, weekly_expiry_weekday=3, angel_name="SENSEX"),
}

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
NO_NEW_TRADES_AFTER = time(15, 0)
SQUARE_OFF_BY = time(15, 15)

# NSE/BSE trading holidays 2026 (weekday closures). Confirm against the exchange circular.
HOLIDAYS = {
    date(2026, 1, 26), date(2026, 3, 3), date(2026, 3, 26), date(2026, 3, 31),
    date(2026, 4, 3), date(2026, 4, 14), date(2026, 5, 1), date(2026, 5, 28),
    date(2026, 6, 26), date(2026, 9, 14), date(2026, 10, 2), date(2026, 10, 20),
    date(2026, 11, 10), date(2026, 11, 24), date(2026, 12, 25),
}

# Charges for BUYING options (round trip). Rates as fractions of premium turnover.
CHARGES = {
    "brokerage_per_order": 20.0,       # flat discount-broker fee
    "stt_sell": 0.0015,                # 0.15% on sell-side premium (Budget 2026)
    "exchange_txn": 0.0003503,         # NSE options ~0.03503% of premium
    "sebi_fee": 0.000001,              # Rs 10 per crore
    "stamp_buy": 0.00003,              # 0.003% on buy side
    "gst": 0.18,                       # on brokerage + exchange + sebi fee
}

# Risk defaults (overridable from the Settings page)
# Small-account defaults (Rs 10k): one NIFTY lot costs ~Rs 7k, an average loss is ~Rs 1.7k (17%).
RISK_DEFAULTS = {
    "capital": 10000.0,
    "risk_per_trade_pct": 25.0,
    "max_trades_per_day": 2,
    "max_daily_loss_pct": 25.0,
    # One position at a time. The owner wants to learn one trade before juggling three: the
    # strategies run in parallel slots, and without this cap two of them can be long at once.
    "max_open_positions": 1,
}
