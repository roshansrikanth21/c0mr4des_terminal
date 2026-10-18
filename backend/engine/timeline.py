"""Session clock, trading calendar and expiry logic."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .config import HOLIDAYS, IST, INSTRUMENTS, MARKET_CLOSE, MARKET_OPEN, NO_NEW_TRADES_AFTER, SQUARE_OFF_BY


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def prev_trading_day(d: date) -> date:
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def next_trading_day(d: date) -> date:
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def weekly_expiry(key: str, today: date) -> date:
    """Nearest weekly expiry on/after today; a holiday expiry moves to the previous trading day."""
    wd = INSTRUMENTS[key].weekly_expiry_weekday
    d = today
    for _ in range(3):
        cand = d + timedelta(days=(wd - d.weekday()) % 7)
        exp = cand if is_trading_day(cand) else prev_trading_day(cand)
        if exp >= today:
            return exp
        d = cand + timedelta(days=1)
    return today


def trading_days_between(a: date, b: date) -> int:
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


PHASES = [
    (time(9, 0), time(9, 15), "pre_open", "Pre-open auction. No trading in options yet."),
    (time(9, 15), time(9, 30), "opening", "Opening 15 minutes: noisy, wide spreads, fake moves. Let the opening range form."),
    (time(9, 30), time(11, 30), "morning_trend", "Best window: the day's trend usually shows itself here."),
    (time(11, 30), time(13, 30), "midday_chop", "Lunch-time chop: lower momentum, more false breakouts. Be picky."),
    (time(13, 30), time(15, 0), "afternoon", "Afternoon session: trends resume, Europe opens around 13:30 IST."),
    (time(15, 0), time(15, 30), "closing", "Last 30 minutes: no fresh entries, manage/exit open trades by 15:15."),
]


def session(now: datetime | None = None, key: str = "NIFTY") -> dict:
    now = now or datetime.now(IST)
    today = now.date()
    t = now.time()
    trading_day = is_trading_day(today)
    is_open = trading_day and MARKET_OPEN <= t < MARKET_CLOSE
    phase, note = "closed", "Market is closed."
    if trading_day:
        for a, b, p, n in PHASES:
            if a <= t < b:
                phase, note = p, n
    if not trading_day:
        note = "Holiday / weekend. Market is closed." if today in HOLIDAYS or today.weekday() >= 5 else note
    next_open_day = today if (trading_day and t < MARKET_OPEN) else next_trading_day(today)
    exp = weekly_expiry(key, today if not (trading_day and t >= MARKET_CLOSE) else next_trading_day(today))
    dte = trading_days_between(today, exp)
    expiry_day = exp == today and trading_day
    return {
        "now": now.isoformat(timespec="seconds"),
        "is_trading_day": trading_day,
        "is_open": is_open,
        "phase": phase,
        "phase_note": note,
        "can_enter": is_open and time(9, 30) <= t < NO_NEW_TRADES_AFTER,
        "square_off_by": SQUARE_OFF_BY.strftime("%H:%M"),
        "next_open": datetime.combine(next_open_day, MARKET_OPEN, IST).isoformat(),
        "expiry": exp.isoformat(),
        "expiry_weekday": exp.strftime("%A"),
        "days_to_expiry": dte,
        "is_expiry_day": expiry_day,
        "expiry_note": _expiry_note(dte, expiry_day, now),
        "minutes_to_close": max(0, int((datetime.combine(today, MARKET_CLOSE, IST) - now).total_seconds() // 60)) if is_open else 0,
    }


def _expiry_note(dte: int, expiry_day: bool, now: datetime) -> str:
    if expiry_day:
        if now.time() >= time(13, 0):
            return ("EXPIRY AFTERNOON: option premiums melt very fast (theta). Buying options now needs a fast, "
                    "strong move; otherwise skip or use next week's expiry.")
        return "Expiry day: big intraday swings are common but premiums decay fast. Keep trades short, book profits quickly."
    if dte == 1:
        return "1 trading day to expiry: time decay is heavy. Prefer ATM/slightly ITM strikes, not cheap OTM."
    return f"{dte} trading days to expiry: time decay is moderate."
