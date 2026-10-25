"""Engine tests: deterministic, offline (no network)."""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from backend.engine import candles, options, structure, timeline
from backend.engine.config import IST
from backend.engine.data import _normalize, closed_bars
from backend.engine.news import score_text
from backend.engine.signal import evaluate, resample_15m


def make_bars(closes, start="2026-10-16 09:15", spread=4.0):
    idx = pd.date_range(start, periods=len(closes), freq="5min", tz=IST)
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + spread, "low": np.minimum(o, c) - spread,
                         "close": c, "volume": 0.0}, index=idx)


def session_bars(days=5, drift=0.0, seed=1):
    """`days` full sessions of 75 five-minute bars with a given drift."""
    rng = np.random.default_rng(seed)
    frames, price = [], 23000.0
    d = date(2026, 10, 5)
    while len(frames) < days:
        if timeline.is_trading_day(d):
            steps = rng.normal(drift, 6, 75)
            closes = price + np.cumsum(steps)
            frames.append(make_bars(closes, start=f"{d} 09:15"))
            price = closes[-1]
        d = d.fromordinal(d.toordinal() + 1)
    return pd.concat(frames)


# ---------------- calendar / expiry ----------------
def test_nifty_expiry_moves_before_dussehra_holiday():
    # Tue 20 Oct 2026 is Dussehra -> NIFTY weekly expiry shifts to Mon 19 Oct
    assert timeline.weekly_expiry("NIFTY", date(2026, 10, 19)) == date(2026, 10, 19)
    assert timeline.weekly_expiry("NIFTY", date(2026, 10, 16)) == date(2026, 10, 19)


def test_sensex_expiry_is_thursday():
    assert timeline.weekly_expiry("SENSEX", date(2026, 10, 19)) == date(2026, 10, 22)
    assert timeline.weekly_expiry("NIFTY", date(2026, 10, 21)) == date(2026, 10, 27)


def test_session_phases():
    s = timeline.session(datetime(2026, 10, 19, 10, 0, tzinfo=IST), "NIFTY")
    assert s["is_open"] and s["phase"] == "morning_trend" and s["can_enter"] and s["is_expiry_day"]
    s = timeline.session(datetime(2026, 10, 20, 10, 0, tzinfo=IST), "NIFTY")
    assert not s["is_open"] and not s["is_trading_day"]
    s = timeline.session(datetime(2026, 10, 19, 15, 5, tzinfo=IST), "NIFTY")
    assert s["is_open"] and not s["can_enter"]


# ---------------- data hygiene ----------------
def test_normalize_drops_impossible_bars():
    df = make_bars([100, 101, 102])
    df.iloc[1, df.columns.get_loc("open")] = 500  # open above high
    assert len(_normalize(df.rename(columns=str.title))) == 2


def test_closed_bars_drops_forming_candle():
    df = make_bars([100, 101, 102])
    now = df.index[-1].to_pydatetime() + pd.Timedelta(minutes=2)
    assert len(closed_bars(df, "5m", now)) == 2
    assert len(closed_bars(df, "5m", now + pd.Timedelta(minutes=5))) == 3


def test_resample_only_full_15m_bars():
    df = make_bars(range(100, 107))  # 7 bars = 2 full 15m + 1 partial
    assert len(resample_15m(df)) == 2


# ---------------- candles ----------------
def test_bullish_engulfing_after_decline():
    closes = list(np.linspace(23200, 23100, 22))
    df = make_bars(closes, spread=2)
    # red candle then a bigger green candle that engulfs it
    last = df.index[-1] + pd.Timedelta(minutes=5)
    df.loc[df.index[-1]] = [23110, 23112, 23090, 23095, 0]
    df.loc[last] = [23090, 23130, 23088, 23125, 0]
    names = [p.name for p in candles.detect(df, lookback=1)]
    assert "Bullish Engulfing" in names
    pat = next(p for p in candles.detect(df, lookback=1) if p.name == "Bullish Engulfing")
    assert pat.direction == 1 and pat.context_ok


def test_doji_and_anatomy_text():
    df = make_bars(list(np.linspace(100, 110, 25)), spread=1)
    t = df.index[-1] + pd.Timedelta(minutes=5)
    df.loc[t] = [110, 113, 107, 110.05, 0]
    assert any(p.name == "Doji" for p in candles.detect(df, lookback=1))
    an = candles.anatomy(df.iloc[-1], 3.0)
    assert an["shape"].startswith("indecisive") and "neither side" in an["text"]


# ---------------- structure ----------------
def test_swings_label_uptrend():
    wave = []
    base = 100
    for k in range(6):
        wave += list(np.linspace(base, base + 20, 6)) + list(np.linspace(base + 20, base + 8, 4))
        base += 8
    df = make_bars(wave, spread=0.5)
    piv = structure.swings(df, k=2, min_atr=0.3)
    labels = [p["label"] for p in piv]
    assert "HH" in labels and "HL" in labels
    assert structure.trend_from_swings(piv)[0] == 1


def test_swings_never_use_future_bars():
    df = session_bars(2)
    piv_full = structure.swings(df)
    piv_cut = structure.swings(df.iloc[:-30])
    # every pivot found on the truncated history must also exist with the same price later
    full = {(p["time"], p["price"]) for p in piv_full}
    stable = [p for p in piv_cut if p["i"] < len(df) - 40]
    assert all((p["time"], p["price"]) in full for p in stable)


# ---------------- options ----------------
def test_put_call_parity():
    S, K, T, sig = 23000, 23000, 7 / 365, 0.14
    ce, pe = options.bs(S, K, T, sig, "CE")["price"], options.bs(S, K, T, sig, "PE")["price"]
    assert abs((ce - pe) - (S - K * np.exp(-options.RISK_FREE * T))) < 0.05


def test_implied_vol_roundtrip():
    p = options.bs(23000, 23100, 3 / 365, 0.16, "CE")["price"]
    assert abs(options.implied_vol(p, 23000, 23100, 3 / 365, "CE") - 0.16) < 0.002


def test_plan_trade_sizes_within_risk():
    risk = {"capital": 100000, "risk_per_trade_pct": 1.0, "max_trades_per_day": 3, "max_daily_loss_pct": 3}
    plan = options.plan_trade("NIFTY", 1, 23000, date(2026, 10, 27), 14, 20, 40, risk,
                              now=datetime(2026, 10, 21, 10, 0, tzinfo=IST))
    assert plan["side"] == "BUY CE" and plan["strike"] % 50 == 0 and plan["lot_size"] == 65
    assert (plan["premium"] - plan["premium_stop"]) * plan["quantity"] <= 1000 + 1e-6
    assert options.plan_trade("SENSEX", -1, 74700, date(2026, 10, 22), 14, 50, 100, risk)["option_type"] == "PE"


# ---------------- news ----------------
@pytest.mark.parametrize("text,direction", [
    ("RBI cuts repo rate by 25 bps", 1),
    ("Sensex tanks 800 points as FIIs sell", -1),
    ("Fed rate hike probability falls to 14%", 1),
    ("Brent crude surges 4% on supply fears", -1),
    ("Software company wins design award", 0),
    ("Actor's house attacked, police probe", 0),
])
def test_news_scoring(text, direction):
    assert score_text(text)["direction"] == direction


# ---------------- brain ----------------
def test_evaluate_is_deterministic_and_bounded():
    df = session_bars(4, drift=1.5)
    daily = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    daily.index = daily.index.normalize()
    sess = {"can_enter": True, "phase": "morning_trend", "is_expiry_day": False}
    a = evaluate(df, daily, 50, session=sess)
    b = evaluate(df, daily, 50, session=sess)
    assert a["verdict"] == b["verdict"] and a["score"] == b["score"]
    assert -1 <= a["score"] <= 1 and a["verdict"] in ("BUY", "SELL", "NO TRADE")
    assert all(r["text"] for r in a["reasons"])
    if a["verdict"] == "NO TRADE":
        assert a["gates"]


def test_evaluate_blocks_entries_when_market_closed():
    df = session_bars(4, drift=3)
    daily = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    r = evaluate(df, daily, 50, session={"can_enter": False, "phase": "closed"})
    assert r["verdict"] == "NO TRADE"


def test_htf_levels_use_only_past_data():
    df = session_bars(5, drift=1.0)
    daily = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    lv = structure.htf_levels(df, daily)
    today = df.index[-1].date()
    today_high = df[df.index.date == today]["high"].max()
    names = {x["name"] for x in lv}
    assert "Prev Week High" in names or any(n.startswith("1H Swing") for n in names)
    assert all(x["price"] != today_high or x["name"].startswith("1H") for x in lv)


def test_paper_trader_lifecycle(tmp_path, monkeypatch):
    from backend.engine import trader
    monkeypatch.setattr(trader, "PAPER_FILE", tmp_path / "paper.json")
    pt = trader.PaperTrader()
    settings = {"autopilot_strategies": ["Engine"], "capital": 100000, "risk_per_trade_pct": 1, "max_trades_per_day": 3, "max_daily_loss_pct": 3,
                "autopilot_instruments": ["NIFTY"]}
    base = {"instrument": {"key": "NIFTY"}, "session": {"is_open": True}, "vix": {"value": 14}, "chain": None,
            "score": 0.6, "reasons": [{"text": "x"}], "spot_live": 23000.0, "price": 23000.0}
    opt = {"side": "BUY CE", "symbol_hint": "NIFTY 27 OCT 23000 CE", "strike": 23000, "option_type": "CE",
           "expiry": "2026-10-27", "quantity": 65, "lots": 1, "premium": 150.0, "premium_source": "model",
           "premium_stop": 120.0, "premium_target": 210.0, "greeks": {"delta": 0.5}}
    a = {**base, "generated_at": "2026-10-21T10:00:00+05:30", "verdict": "BUY", "option": opt,
         "plan": {"direction": 1, "stop": 22950.0, "target": 23100.0}}
    assert pt.on_analysis(a, settings)["events"][0]["type"] == "paper_entry"
    b = {**a, "generated_at": "2026-10-21T10:30:00+05:30", "verdict": "NO TRADE", "spot_live": 23110.0, "price": 23110.0}
    ev = pt.on_analysis(b, settings)["events"][0]
    assert ev["type"] == "paper_exit" and ev["trade"]["reason"] == "target" and ev["trade"]["pnl"] > 0
    assert not pt.state["open"]
    assert pt.summary()["by_strategy"]["Engine"]["trades"] == 1


def test_orb_breakout_rules():
    from backend.engine import orb
    closes = [23000, 23010, 23020, 23005, 23015, 23010] * 2 + [23012, 23015, 23060]  # breakout on the last bar
    df = make_bars(closes, start="2026-10-21 09:15", spread=5)
    now = df.index[-1].to_pydatetime() + pd.Timedelta(minutes=5)
    r = orb.evaluate(df, prev_close=22950, now=now)
    assert r["verdict"] == "BUY" and r["stop"] == pytest.approx(df.iloc[:12].low.min())
    assert r["target"] == pytest.approx(r["entry"] + 2 * (r["entry"] - r["stop"]))
    r2 = orb.evaluate(df, prev_close=23100, now=now)  # breakout, but below yesterday's close -> filtered
    assert r2["verdict"] == "NO TRADE"
    early = orb.evaluate(df.iloc[:8], prev_close=22950, now=df.index[7].to_pydatetime())
    assert early["status"] == "forming"


def test_first_hour_uses_one_strike_otm():
    risk = {"capital": 10000, "risk_per_trade_pct": 25, "max_trades_per_day": 2, "max_daily_loss_pct": 25}
    now = datetime(2026, 10, 21, 11, 0, tzinfo=IST)
    ce = options.plan_trade("NIFTY", 1, 23010, date(2026, 10, 27), 14, 60, 120, risk, now=now, otm_steps=1)
    pe = options.plan_trade("NIFTY", -1, 23010, date(2026, 10, 27), 14, 60, 120, risk, now=now, otm_steps=1)
    assert ce["strike"] == 23050 and pe["strike"] == 22950


def test_angel_token_error_detected():
    from backend.engine.data import _token_error
    assert _token_error({"success": False, "message": "Invalid Token", "errorCode": "AG8001", "data": ""})
    assert not _token_error({"status": True, "data": []})
    assert not _token_error(None)


def test_replay_clock_freezes_while_engine_busy():
    import time
    from datetime import date
    from backend.engine import replay
    replay.start(date(2026, 10, 16), speed=600)
    replay.hold(True)
    t0 = replay.now()
    time.sleep(0.3)
    assert replay.now() == t0
    replay.hold(False)
    time.sleep(0.1)
    assert replay.now() > t0
    replay.stop()


def test_scorecard_and_go_no_go():
    from backend.engine.trader import go_no_go, scorecard
    trades = [{"pnl": p} for p in [-1000, -1000, 3000, -1000, 3500] * 4]
    sc = scorecard(trades)
    assert sc["trades"] == 20 and sc["win_rate"] == 40.0 and sc["worst_streak"] == 2
    assert go_no_go(sc)[0] == "GO"
    assert go_no_go(scorecard(trades[:5]))[0].startswith("NOT YET")


def test_go_no_go_blocks_trades_the_account_could_not_afford():
    from backend.engine.trader import go_no_go, scorecard
    trades = [{"pnl": p} for p in [-1000, -1000, 3000, -1000, 3500] * 4]
    assert scorecard(trades)["oversize"] == 0
    trades[3]["oversize"] = True  # one lot risked more than the settings' budget allowed
    sc = scorecard(trades)
    assert sc["oversize"] == 1
    verdict, lines = go_no_go(sc)
    assert verdict == "NO-GO"
    assert any("bigger than your risk budget" in ln for ln in lines)


def test_disabled_strategy_opens_nothing(tmp_path):
    from backend.engine.trader import PaperTrader
    a = {"instrument": {"key": "NIFTY"}, "verdict": "BUY", "option": {"lots": 1}, "plan": {"direction": 1, "stop": 1},
         "orb": {}, "first30": {}, "generated_at": "2026-10-23T10:30:00+05:30", "price": 100, "spot_live": 100,
         "session": {"is_open": True}}
    res = PaperTrader(tmp_path / "p.json").on_analysis(a, {"autopilot_strategies": ["First-Hour"], "max_trades_per_day": 2})
    assert res["events"] == [] and res["open"] == []


def test_lots_are_capped_on_cheap_premiums():
    from datetime import date, datetime
    from backend.engine import options
    from backend.engine.config import IST
    now = datetime(2026, 10, 13, 14, 15, tzinfo=IST)
    o = options.plan_trade("NIFTY", 1, 22582, date(2026, 10, 13), 16.9, 200, 400,
                           {"capital": 10000, "risk_per_trade_pct": 25, "max_trades_per_day": 2, "max_daily_loss_pct": 25},
                           None, now, otm_steps=1)
    assert o["lots"] <= options.MAX_LOTS


# ---------------- robustness (audit 25 Oct 2026) ----------------
def _entry_analysis(when: str, spot: float = 23000.0, verdict: str = "BUY") -> dict:
    opt = {"side": "BUY CE", "symbol_hint": "NIFTY 27 OCT 23000 CE", "strike": 23000, "option_type": "CE",
           "expiry": "2026-10-27", "quantity": 65, "lots": 1, "premium": 150.0, "premium_source": "model",
           "premium_stop": 120.0, "premium_target": 210.0, "greeks": {"delta": 0.5}}
    return {"instrument": {"key": "NIFTY"}, "session": {"is_open": True}, "vix": {"value": 14}, "chain": None,
            "score": 0.6, "reasons": [], "spot_live": spot, "price": spot, "generated_at": when,
            "verdict": verdict, "option": opt, "plan": {"direction": 1, "stop": 22950.0, "target": 23100.0}}


def test_paper_book_recovers_from_a_corrupt_file(tmp_path):
    from backend.engine import trader
    p = tmp_path / "paper.json"
    pt = trader.PaperTrader(p)
    pt.state["closed"].append({"pnl": 10.0, "opened_at": "2026-10-21T10:00:00+05:30", "instrument": "NIFTY",
                               "strategy": "First-Hour", "slot": "NIFTY|orb", "closed_at": "2026-10-21T11:00:00+05:30"})
    pt._save()
    pt._save()  # second save turns the valid file into paper.json.bak
    p.write_text('{"open": {', encoding="utf-8")  # what a kill mid-write used to leave behind
    again = trader.PaperTrader(p)
    assert len(again.state["closed"]) == 1
    assert list(tmp_path.glob("paper.json.corrupt-*.json")), "the unreadable file must be preserved"


def test_missed_square_off_is_closed_next_session(tmp_path):
    from backend.engine import trader
    pt = trader.PaperTrader(tmp_path / "p.json")
    settings = {"autopilot_strategies": ["Engine"], "capital": 100000, "risk_per_trade_pct": 1,
                "max_trades_per_day": 3, "max_daily_loss_pct": 3, "autopilot_instruments": ["NIFTY"]}
    assert pt.on_analysis(_entry_analysis("2026-10-21T10:00:00+05:30"), settings)["events"][0]["type"] == "paper_entry"
    # Next day, between stop and target: nothing would have closed it, so it must be forced out.
    ev = pt.on_analysis(_entry_analysis("2026-10-22T09:20:00+05:30", verdict="NO TRADE"), settings)["events"][0]
    assert ev["type"] == "paper_exit" and ev["trade"]["reason"] == "stale (square-off missed)"
    assert ev["trade"]["stale"] is True and not pt.state["open"]
    # Keyed on opened_at, so yesterday's forced exit never touches today's daily-loss cap.
    assert pt.today_closed(day=date(2026, 10, 22)) == []
    assert pt.today_closed(day=date(2026, 10, 21)) != []


def test_first30_has_no_target():
    from backend.engine import orb
    closes = [23000, 23001, 23002, 23003, 23004, 23005]
    df = make_bars(closes, start="2026-10-21 09:15", spread=1)
    r = orb.first30(df, datetime(2026, 10, 21, 9, 50, tzinfo=IST))
    assert r["verdict"] == "BUY" and r["direction"] == 1
    assert r["target"] is None and "no target" in r["text"]


def test_settings_are_clamped(tmp_path, monkeypatch):
    from backend.engine import service
    monkeypatch.setattr(service, "SETTINGS_FILE", tmp_path / "settings.json")
    s = service.save_settings({"capital": -5, "max_trades_per_day": 0,
                               "risk_per_trade_pct": 500, "max_daily_loss_pct": 300})
    assert s["capital"] == 1000.0 and s["max_trades_per_day"] == 1
    assert s["risk_per_trade_pct"] == 100.0 and s["max_daily_loss_pct"] == 100.0


def test_evaluate_refuses_a_nearly_empty_frame():
    df = make_bars([100, 101, 102])
    with pytest.raises(RuntimeError):
        evaluate(df, df, 50)



def test_expiry_play_is_one_lot_with_capped_loss():
    from datetime import date, datetime
    from backend.engine import service
    from backend.engine.config import IST
    now = datetime(2026, 10, 27, 10, 30, tzinfo=IST)  # a Tuesday expiry
    orb_sig = {"verdict": "BUY", "direction": 1, "stop": 22900, "target": 23300, "risk_points": 100, "target_points": 200,
               "text": "breakout"}
    sess = {"is_expiry_day": True, "can_enter": True, "is_open": True}
    sig = service._expiry_signal("NIFTY", orb_sig, sess, 23000, {"value": 15}, service.load_settings(), None,
                                 date(2026, 10, 27), now, in_replay=True)
    o = sig["option"]
    assert sig["verdict"] == "BUY" and o["lots"] == 1 and o["expiry"] == "2026-10-27"
    assert (o["premium"] - o["premium_stop"]) * 65 <= service.EXPIRY_MAX_LOSS + 1
    assert service._expiry_signal("NIFTY", orb_sig, {**sess, "is_expiry_day": False}, 23000, None, {}, None,
                                  date(2026, 10, 27), now, True) is None
