"""Engine tests: deterministic, offline (no network)."""
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from backend.engine import candles, mtf, options, structure, timeline
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


# ---------------- multi-timeframe ladder ----------------
def to_daily(df5):
    return df5.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                   "close": "last", "volume": "sum"}).dropna()


def test_ladder_reads_an_uptrend_on_every_timeframe():
    df5 = session_bars(days=25, drift=1.5)
    out = mtf.ladder(df5, to_daily(df5))
    assert out["bias"] > 0.2
    assert out["phase"] in ("aligned", "conflict", "pullback")
    assert out["counted"] >= 4
    for row in out["rows"]:
        if row["available"]:
            assert row["direction"] >= 0, row
    assert out["primary"]["direction"] == 1


def test_ladder_calls_a_fast_rally_inside_a_downtrend_a_pullback():
    df5 = session_bars(days=25, drift=-1.5)
    base = float(df5["close"].iloc[-13])
    tail = df5.iloc[-12:].copy()
    tail["close"] = base + np.arange(1, 13) * 10.0
    tail["open"] = np.r_[base, tail["close"].values[:-1]]
    tail["high"] = np.maximum(tail["open"], tail["close"]) + 4
    tail["low"] = np.minimum(tail["open"], tail["close"]) - 4
    df5 = pd.concat([df5.iloc[:-12], tail])

    out = mtf.ladder(df5, to_daily(df5))
    assert out["phase"] == "pullback"
    assert out["bias"] < 0            # the slow timeframes still rule the read
    assert "pullback" in out["story"].lower()


def test_ladder_says_so_when_there_is_no_history():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    out = mtf.ladder(empty, empty)
    assert out["phase"] == "unclear"
    assert out["primary"] is None
    assert out["counted"] == 0


# ---------------- previous session ----------------
def test_previous_session_reports_close_position_and_gap():
    daily = pd.DataFrame(
        {"open": [22900.0, 23000.0], "high": [22960.0, 23100.0], "low": [22880.0, 22900.0],
         "close": [22920.0, 23085.0], "volume": [0.0, 0.0]},
        index=pd.DatetimeIndex(["2026-10-15", "2026-10-16"], tz=IST))
    intraday = make_bars([23150.0, 23160.0, 23170.0], start="2026-10-19 09:15")
    out = structure.prev_session(daily, intraday)
    assert out["close"] == 23085.0
    assert out["range"] == 200.0
    assert out["close_position_pct"] == 92.5
    assert out["gap_points"] == 65.0
    assert "gap up" in out["text"]


# ---------------- both option sides ----------------
def test_both_sides_are_priced_and_affordability_is_honest():
    now = datetime(2026, 10, 23, 10, 0, tzinfo=IST)
    expiry = date(2026, 10, 27)
    poor = options.quote_both_sides("NIFTY", 23000.0, expiry, 14.0, {"capital": 1000.0}, None, now)
    assert poor["call"]["premium"] > 0 and poor["put"]["premium"] > 0
    assert poor["affordable"] == []
    assert "Neither side fits" in poor["text"]

    rich = options.quote_both_sides("NIFTY", 23000.0, expiry, 14.0, {"capital": 10_000_000.0}, None, now)
    assert rich["affordable"] == ["call", "put"]
    for side in ("call", "put"):
        row = rich[side]
        assert row["lot_cost"] == pytest.approx(row["premium"] * row["lot_size"], rel=0.01)
        # A long option can go to zero: the worst case is the whole premium, not premium minus stop.
        assert row["worst_case"] > row["lot_cost"]
        assert row["theta_per_lot_per_day"] >= 0


def test_only_one_position_is_open_at_a_time(tmp_path):
    from backend.engine import trader
    pt = trader.PaperTrader(tmp_path / "p.json")
    settings = {"capital": 100000, "risk_per_trade_pct": 1, "max_trades_per_day": 3,
                "max_daily_loss_pct": 3, "max_open_positions": 1}
    a = _entry_analysis("2026-10-21T10:00:00+05:30")
    first = pt._process("NIFTY|engine", "Engine", "BUY", a["option"], a["plan"], a, settings,
                        settings["max_trades_per_day"])
    assert first[0]["type"] == "paper_entry"

    second = pt._process("NIFTY|orb", "First-Hour", "BUY", a["option"], a["plan"], a, settings,
                         settings["max_trades_per_day"])
    assert second[0]["type"] == "blocked"
    assert "one position at a time" in second[0]["reason"]
    assert len(pt.state["open"]) == 1

    # Raise the cap and the waiting strategy is allowed through - the guard is a setting, not a dead end.
    loose = {**settings, "max_open_positions": 2}
    third = pt._process("NIFTY|orb", "First-Hour", "BUY", a["option"], a["plan"], a, loose,
                        loose["max_trades_per_day"])
    assert third[0]["type"] == "paper_entry" and len(pt.state["open"]) == 2


def test_expiry_is_opt_in_by_owner_decision():
    # Owner call 26 Oct: the 1.41 profit factor comes from expiry days, the least trustworthy prices in
    # the record, so the Expiry slot must not paper-trade until it has banked its own honest record.
    from backend.engine.service import DEFAULT_STRATEGIES, ALL_STRATEGIES
    assert "Expiry" not in DEFAULT_STRATEGIES
    assert set(DEFAULT_STRATEGIES).issubset(ALL_STRATEGIES)
    assert set(DEFAULT_STRATEGIES) <= {"First-Hour", "First-30"}


# ---------------- failure patterns + experiment registry ----------------
def test_lessons_names_recurring_failure_shapes():
    from backend.engine.lessons import lessons

    def t(when, reason, pnl, oversize=False):
        return {"opened_at": when, "reason": reason, "pnl": pnl, "oversize": oversize, "stale": False}

    closed = [
        t("2026-10-21T14:10:00+05:30", "15:15 square-off", -1097.84),   # late chase, bled to close
        t("2026-10-26T09:48:00+05:30", "stop", -201.87),               # first-hour stop
        t("2026-10-23T10:35:00+05:30", "premium stop", -1410.35),      # decay death
        t("2026-10-23T09:45:00+05:30", "15:15 square-off", 5226.87),   # winner held to close
        t("2026-10-23T10:20:00+05:30", "stop", -1837.72, oversize=True),
    ]
    out = lessons(closed)
    assert out["counts"]["late_entry"] == 1
    assert out["counts"]["bled_to_close"] == 1
    assert out["counts"]["early_loss"] == 3
    assert out["counts"]["decay_death"] == 1
    assert out["counts"]["winners_held_to_close"] == 1
    assert out["counts"]["oversize_loss"] == 1

    # the standing warnings survive: tiny sample + concentrated profit
    names = {f["name"] for f in out["flags"]}
    assert "sample" in names and "luck" in names
    assert out["losses"] == 4

    empty = lessons([])
    assert "No paper trades yet" in empty["text"] and empty["net"] == 0.0


def test_experiment_registry_seeds_once_and_appends(tmp_path, monkeypatch):
    from backend.engine import experiments
    f = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(experiments, "FILE", f)
    n = len(experiments._seed())                                        # committed truth, whatever its size
    rows = experiments.all()
    assert len(rows) == n                                               # seeded on first read
    assert all(set(r) >= {"id", "date", "area", "name", "change", "evidence", "status", "owner"} for r in rows)
    assert [r["id"] for r in rows] == sorted({r["id"] for r in rows})   # no duplicate ids

    again = experiments.all()
    assert len(again) == n                                              # second read does NOT reseed a new copy

    new = experiments.record("process", "test row", "unit test", "evidence", "testing", "unit")
    assert new["id"] == n + 1 and len(experiments.all()) == n + 1
    assert len(experiments.all()) == n + 1                              # the failed write must not have appended


def test_experiment_registry_picks_up_rows_committed_after_it_was_created(tmp_path, monkeypatch):
    import json as _json
    from backend.engine import experiments
    f = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(experiments, "FILE", f)
    seeds = experiments._seed()
    old = seeds[:9]                                                     # an install older than rows 10+
    f.write_text("\n".join(_json.dumps(r) for r in old) + "\n", encoding="utf-8")
    rows = experiments.all()
    assert len(rows) == len(seeds) and {r["id"] for r in seeds[9:]} <= {r["id"] for r in rows}
    assert len(f.read_text(encoding="utf-8").splitlines()) == len(seeds)

    f.write_text("{not json}\n", encoding="utf-8")                      # a corrupt file is never rewritten
    assert experiments.all() == []
    assert f.read_text(encoding="utf-8") == "{not json}\n"


# ---------------- multi-capital paper experiment ----------------
def _cap_analysis(when: str = "2026-10-27T10:00:00+05:30", verdict: str = "BUY",
                  premium: float = 150.0, spot: float = 23000.0) -> dict:
    direction = 1 if verdict == "BUY" else -1
    kind = "CE" if direction > 0 else "PE"
    opt = {"side": f"BUY {kind}", "symbol_hint": f"NIFTY 27 OCT 23000 {kind}", "strike": 23000,
           "option_type": kind, "expiry": "2026-10-27", "quantity": 65, "lots": 1, "premium": premium,
           "premium_source": "model", "premium_stop": round(premium * 0.8, 2),
           "premium_target": round(premium * 1.4, 2), "greeks": {"delta": 0.5}}
    leg = {"verdict": verdict, "direction": direction,
           "stop": spot - 50 if direction > 0 else spot + 50,
           "target": spot + 100 if direction > 0 else spot - 100, "option": opt}
    return {"instrument": {"key": "NIFTY"}, "session": {"is_open": True}, "vix": {"value": 14},
            "chain": None, "chains": {}, "score": 0.6, "reasons": [], "spot_live": spot, "price": spot,
            "generated_at": when, "verdict": "NO TRADE", "option": None, "plan": {},
            "orb": leg, "first30": {},
            "sides": {"call": {"lot_cost": 9000.0, "worst_case": 9200.0},
                      "put": {"lot_cost": 9500.0, "worst_case": 9700.0}}}


def _cap_book(tmp_path, monkeypatch, cid: str):
    from backend.engine import capital_test as ct
    monkeypatch.setattr(ct, "DATA_DIR", tmp_path)
    return ct.CaseBook(next(s for s in ct.CASES if s["id"] == cid))


def _cap_settings() -> dict:
    return {"autopilot_instruments": ["NIFTY"], "autopilot_strategies": ["First-Hour", "First-30"],
            "capital": 10000, "risk_per_trade_pct": 25, "max_trades_per_day": 2,
            "max_daily_loss_pct": 25, "max_open_positions": 1}


def test_capital_cases_size_differently_and_keep_separate_files(tmp_path, monkeypatch):
    a = _cap_analysis()
    sizes = {}
    for cid in ("A", "B", "C"):
        book = _cap_book(tmp_path, monkeypatch, cid)
        ev = book.on_analysis(a, _cap_settings())["events"]
        assert ev and ev[0]["type"] == "paper_entry"
        pos = ev[0]["trade"]
        sizes[cid] = pos["quantity"]
        assert book.path.parent == tmp_path and book.path.name == f"{cid}.json"
    # risk per lot is Rs 1,950 (30 points x 65), so 20% of each stake buys 1 / 3 / 4 lots
    assert sizes == {"A": 65, "B": 195, "C": 260}
    assert len({tmp_path / "A.json", tmp_path / "B.json", tmp_path / "C.json"}) == 3
    assert not (tmp_path / "D.json").exists(), "no case may write into another case's book"


def test_capital_puts_only_case_skips_calls_and_takes_the_put(tmp_path, monkeypatch):
    book = _cap_book(tmp_path, monkeypatch, "D")
    assert book.on_analysis(_cap_analysis(verdict="BUY"), _cap_settings())["open"] == []

    ev = book.on_analysis(_cap_analysis(verdict="SELL", premium=140.0), _cap_settings())["events"]
    assert ev and ev[0]["type"] == "paper_entry"
    assert ev[0]["trade"]["option_type"] == "PE" and ev[0]["trade"]["dir"] == -1


def test_capital_second_trade_needs_a_green_first_trade(tmp_path, monkeypatch):
    from datetime import date
    book = _cap_book(tmp_path, monkeypatch, "A")
    d = date(2026, 10, 27)
    assert book.budget_today(d) == 1
    book.state["closed"].append({"pnl": -500.0, "opened_at": "2026-10-27T10:00:00+05:30",
                                "closed_at": "2026-10-27T11:00:00+05:30"})
    assert book.budget_today(d) == 1, "a losing day stops at one trade"
    book.state["closed"][0]["pnl"] = 800.0
    assert book.budget_today(d) == 2, "only a green first trade unlocks the second"


def test_capital_case_busts_resets_and_archives_the_era(tmp_path, monkeypatch):
    book = _cap_book(tmp_path, monkeypatch, "A")
    book.state["closed"].append({"pnl": -5000.0, "opened_at": "2026-10-27T10:00:00+05:30",
                                "closed_at": "2026-10-27T11:00:00+05:30", "charges": 50.0})
    book._save()
    assert book.equity() == 5000.0

    ev = book.on_analysis(_cap_analysis(verdict="NO TRADE"), _cap_settings())["events"]
    assert ev and ev[0]["type"] == "bust" and ev[0]["era"] == 1
    assert book.equity() == 10000.0 and book.state["closed"] == []
    snaps = list(tmp_path.glob("A_bust*.json"))
    assert len(snaps) == 1
    import json as _json
    assert _json.loads(snaps[0].read_text(encoding="utf-8"))["closed"][0]["pnl"] == -5000.0
    assert book.report()["busts"] == 1 and book.report()["net"] == -5000.0


def test_capital_case_never_borrows_and_never_resets_an_untraded_book(tmp_path, monkeypatch):
    book = _cap_book(tmp_path, monkeypatch, "A")
    a = _cap_analysis()
    a["sides"] = {"call": {"lot_cost": 12000.0, "worst_case": 12300.0},
                  "put": {"lot_cost": 12000.0, "worst_case": 12300.0}}
    out = book.on_analysis(a, _cap_settings())
    assert out["open"] == [] and out["events"][0]["type"] == "blocked"
    assert "no trade rather than invented money" in out["events"][0]["reason"]
    assert book.equity() == 10000.0 and not list(tmp_path.glob("A_bust*.json")), \
        "a stake that cannot fund a lot is not a loss and must not be reset"



# ---------------- A+B: cost/theta gate and time discipline (26 Oct 2026) ----------------
def _gated_option(premium: float, theta_per_day: float, lot: int = 65) -> dict:
    return {"side": "BUY CE", "symbol_hint": "NIFTY 27 OCT 23000 CE", "strike": 23000, "option_type": "CE",
            "expiry": "2026-10-27", "lots": 1, "premium": premium, "premium_stop": round(premium * 0.8, 2),
            "premium_target": round(premium * 1.4, 2), "lot_size": lot,
            "greeks": {"delta": 0.5, "theta_per_day": theta_per_day}}


def test_entry_gate_blocks_near_expiry_theta_and_cheap_contracts():
    now = datetime(2026, 10, 21, 10, 0, tzinfo=IST)
    assert options.entry_blockers(_gated_option(190.0, -16.0), 65, now) == [], \
        "a week-out ATM option pays ~8% theta and ~0.6% charges - it must pass"
    near = options.entry_blockers(_gated_option(120.0, -40.0), 65, now)
    assert [b["name"] for b in near] == ["theta"] and near[0]["value"] > 20
    cheap = options.entry_blockers(_gated_option(25.0, -1.0), 65, now)
    assert [b["name"] for b in cheap] == ["charges"], "a Rs 1,625 lot cannot carry Rs 50 of costs"
    late = options.entry_blockers(_gated_option(190.0, -16.0), 65, datetime(2026, 10, 21, 13, 5, tzinfo=IST))
    assert [b["name"] for b in late] == ["clock"]
    # Missing greeks mean "cannot judge", not "blocked": old books and hand-built tests still replay.
    assert options.entry_blockers({"premium": 190.0}, 65, now) == []


def test_entry_gate_blocks_the_trade_and_says_why(tmp_path):
    from backend.engine import trader
    pt = trader.PaperTrader(tmp_path / "p.json")
    settings = {"autopilot_strategies": ["Engine"], "capital": 100000, "risk_per_trade_pct": 1,
                "max_trades_per_day": 3, "max_daily_loss_pct": 3, "autopilot_instruments": ["NIFTY"]}
    a = _entry_analysis("2026-10-21T10:00:00+05:30")
    a["option"] = {**a["option"], "premium": 120.0, "premium_stop": 100.0,
                   "greeks": {"delta": 0.5, "theta_per_day": -40.0}}
    ev = pt.on_analysis(a, settings)["events"]
    assert ev[0]["type"] == "blocked" and "theta" in ev[0]["reason"]
    assert not pt.state["open"]
    gate = pt.summary()["last_gate"]
    assert gate["blocked"] == ["theta"] and gate["reasons"]
    assert pt.summary()["entry_rules"]["no_entry_after"] == "13:00"


def test_time_stop_closes_the_last_hour_bleed(tmp_path):
    from backend.engine import trader
    pt = trader.PaperTrader(tmp_path / "p.json")
    settings = {"autopilot_strategies": ["Engine"], "capital": 100000, "risk_per_trade_pct": 1,
                "max_trades_per_day": 3, "max_daily_loss_pct": 3, "autopilot_instruments": ["NIFTY"]}
    assert pt.on_analysis(_entry_analysis("2026-10-21T10:00:00+05:30"), settings)["events"][0]["type"] == "paper_entry"
    # Same spot, still inside stop and target, but past 14:30: the clock takes it out.
    ev = pt.on_analysis(_entry_analysis("2026-10-21T14:35:00+05:30"), settings)["events"][0]
    assert ev["type"] == "paper_exit" and ev["trade"]["reason"] == "14:30 time stop"


def test_capital_cases_inherit_the_entry_gate(tmp_path, monkeypatch):
    book = _cap_book(tmp_path, monkeypatch, "C")
    a = _cap_analysis()
    a["orb"]["option"] = {**a["orb"]["option"], "greeks": {"delta": 0.5, "theta_per_day": -40.0}}
    ev = book.on_analysis(a, _cap_settings())["events"]
    assert ev and ev[0]["type"] == "blocked" and "theta" in ev[0]["reason"]
    assert book.state["open"] == {}


# ---------------- defined-risk credit spreads ----------------
def _spread_analysis(when: str = "2026-10-28T10:00:00+05:30", spot: float = 25000.0,
                     verdict: str = "BUY") -> dict:
    return {"instrument": {"key": "NIFTY"}, "session": {"is_open": True, "expiry": "2026-11-03"},
            "vix": {"value": 15}, "chains": {}, "chain": None, "score": 0.6, "reasons": [],
            "spot_live": spot, "price": spot, "generated_at": when,
            "orb": {"verdict": verdict, "direction": 1 if verdict == "BUY" else -1}}


def test_credit_spread_is_defined_risk_and_direction_maps():
    from backend.engine import spreads
    now = datetime(2026, 10, 28, 10, 0, tzinfo=IST)
    exp = date(2026, 11, 3)
    bull = spreads.plan("NIFTY", 1, 25000.0, exp, 15, now)
    assert bull["kind"] == "bull_put" and bull["option_type"] == "PE"
    assert bull["long_strike"] < bull["short_strike"] < 25000.0
    assert bull["credit"] > 0 and bull["credit_value"] == pytest.approx(bull["credit"] * 65, rel=0.01)
    assert bull["margin"] == pytest.approx(bull["width"] * 65)          # defined risk: the width
    assert bull["max_loss"] > 0 and bull["stop_debit"] == pytest.approx(bull["credit"] * 2, rel=0.01)
    assert bull["target_debit"] == pytest.approx(bull["credit"] * 0.5, rel=0.01)
    assert bull["credit_pct_of_width"] >= 8.0

    bear = spreads.plan("NIFTY", -1, 25000.0, exp, 15, now)
    assert bear["kind"] == "bear_call" and bear["option_type"] == "CE"
    assert 25000.0 < bear["short_strike"] < bear["long_strike"]


def test_spread_book_takes_half_the_credit(tmp_path):
    from backend.engine import spreads
    b = spreads.SpreadBook(tmp_path / "s.json")
    out = b.on_analysis(_spread_analysis())
    assert out["events"][0]["type"] == "spread_entry"
    pos = out["open"]
    assert pos["margin"] <= b.equity
    # 200 points in favour closes the spread at roughly half the credit
    ev = b.on_analysis(_spread_analysis("2026-10-28T11:30:00+05:30", spot=25200.0))["events"]
    assert ev[0]["type"] == "spread_exit"
    assert ev[0]["trade"]["reason"] == "target (50% of credit)" and ev[0]["trade"]["pnl"] > 0
    assert b.report()["trades"] == 1 and b.equity > 50000.0


def test_spread_book_stops_at_twice_the_credit(tmp_path):
    from backend.engine import spreads
    b = spreads.SpreadBook(tmp_path / "s.json")
    b.on_analysis(_spread_analysis())
    ev = b.on_analysis(_spread_analysis("2026-10-28T11:30:00+05:30", spot=24700.0))["events"]
    assert ev[0]["trade"]["reason"] == "stop (2x credit)"
    assert -3500 < ev[0]["trade"]["pnl"] < 0, "the stop must cap the loss near the credit, not the width"


def test_spread_book_never_borrows_and_never_stacks(tmp_path):
    from backend.engine import spreads
    poor = spreads.SpreadBook(tmp_path / "poor.json", {"stake": 5000.0})
    out = poor.on_analysis(_spread_analysis())
    assert out["open"] is None and out["events"][0]["type"] == "blocked"
    assert "never borrowed" in out["events"][0]["reason"]

    b = spreads.SpreadBook(tmp_path / "s.json")
    b.on_analysis(_spread_analysis())
    second = b.on_analysis(_spread_analysis("2026-10-28T10:30:00+05:30", verdict="SELL"))
    assert second["events"] == [] and second["open"]["kind"] == "bull_put", "one spread at a time"


def test_spread_book_time_stop_and_one_trade_a_day(tmp_path):
    from backend.engine import spreads
    b = spreads.SpreadBook(tmp_path / "s.json")
    b.on_analysis(_spread_analysis())
    ev = b.on_analysis(_spread_analysis("2026-10-28T14:35:00+05:30"))["events"]
    assert ev[0]["trade"]["reason"] == "14:30 time stop"
    again = b.on_analysis(_spread_analysis("2026-10-28T14:45:00+05:30"))
    assert again["events"] == [] and again["open"] is None, "one spread a day"


# ---------------- the target must scale with the range, not be a fixed number ----------------
def test_fixed_points_demand_a_different_win_rate_every_day():
    from backend.engine import orb
    # Same 10-point target, three different mornings: the requirement moves with the stop.
    assert orb.breakeven_win_rate(64, 10) == 86.5
    assert orb.breakeven_win_rate(95, 10) == 90.5
    assert orb.breakeven_win_rate(178, 10) == 94.7
    # 2R demands the same number whatever the range is.
    assert orb.breakeven_win_rate(64, 128) == 33.3
    assert orb.breakeven_win_rate(178, 356) == 33.3


def test_target_plan_is_two_r_and_knows_its_break_even():
    from backend.engine import orb
    long_side = orb.target_plan(22800.0, 22704.0, 2.0)
    assert long_side["risk_points"] == 96.0
    assert long_side["target"] == 22992.0 and long_side["target_points"] == 192.0
    assert long_side["breakeven_win_rate"] == 33.3
    short_side = orb.target_plan(22800.0, 22896.0, 2.0)
    assert short_side["target"] == 22608.0
    assert short_side["breakeven_win_rate"] == 33.3
    flat = orb.target_plan(22800.0, 22800.0)
    assert flat["risk_points"] == 0 and flat["breakeven_win_rate"] is None


# ---------------- daily circuit breakers ----------------
def _closed_on(day: str, pnl: float, slot: str = "NIFTY|orb", strategy: str = "First-Hour") -> dict:
    return {"pnl": pnl, "slot": slot, "strategy": strategy, "instrument": "NIFTY",
            "opened_at": f"{day}T10:00:00+05:30", "closed_at": f"{day}T11:00:00+05:30"}


def _day_settings(capital: float = 10000.0, profit_pct: float = 20.0, loss_pct: float = 25.0) -> dict:
    return {"autopilot_strategies": ["Engine"], "capital": capital, "risk_per_trade_pct": 25,
            "max_trades_per_day": 3, "max_daily_loss_pct": loss_pct,
            "daily_profit_pct": profit_pct, "autopilot_instruments": ["NIFTY"]}


def test_day_stops_once_the_profit_target_is_banked(tmp_path):
    from backend.engine import trader
    pt = trader.PaperTrader(tmp_path / "p.json")
    pt.state["closed"].append(_closed_on("2026-10-21", 2000.0))       # +20% of Rs 10k
    ev = pt.on_analysis(_entry_analysis("2026-10-21T14:00:00+05:30"), _day_settings())["events"]
    assert ev[0]["type"] == "blocked" and "profit target" in ev[0]["reason"]
    assert not pt.state["open"]
    assert pt.state["day_rules"]["profit_stop"] == 2000.0


def test_a_trade_cannot_risk_more_than_the_day_has_left(tmp_path):
    from backend.engine import trader
    # Rs 10k book, 25% daily loss limit = Rs 2,500. The trade below risks (150-120)*65 = Rs 1,950.
    pt = trader.PaperTrader(tmp_path / "p.json")
    pt.state["closed"].append(_closed_on("2026-10-21", -2000.0))      # only Rs 500 of room left
    ev = pt.on_analysis(_entry_analysis("2026-10-21T12:00:00+05:30"), _day_settings())["events"]
    assert ev[0]["type"] == "blocked" and "only Rs 500" in ev[0]["reason"]
    assert not pt.state["open"], "a trade that could breach the day must never be opened"

    fits = trader.PaperTrader(tmp_path / "q.json")
    fits.state["closed"].append(_closed_on("2026-10-21", -400.0))     # Rs 2,100 of room, trade needs 1,950
    ev = fits.on_analysis(_entry_analysis("2026-10-21T12:00:00+05:30"), _day_settings())["events"]
    assert ev[0]["type"] == "paper_entry"


def test_day_state_reports_the_room_and_the_stop(tmp_path):
    from datetime import date as _d
    from backend.engine import trader
    pt = trader.PaperTrader(tmp_path / "p.json")
    pt.state["closed"].append(_closed_on("2026-10-21", -1200.0))
    pt.on_analysis(_entry_analysis("2026-10-21T14:00:00+05:30"), _day_settings())   # records the rules
    day = pt.summary(day=_d(2026, 10, 21))["day"]
    assert day["pnl"] == -1200.0 and day["room"] == 1300.0 and day["stopped"] is None
    assert day["profit_stop"] == 2000.0 and day["loss_stop"] == 2500.0



# ---------------- decision engine ----------------
def _feature_frame(days: int = 30, per_day: int = 2) -> "pd.DataFrame":
    """Synthetic training table: a real signal on range_atr, plus noise."""
    import numpy as np
    import pandas as pd
    from backend.engine.dataset import FEATURES

    rng = np.random.default_rng(7)
    rows = []
    for d in range(days):
        for k in range(per_day):
            f = {name: float(rng.normal()) for name in FEATURES}
            signal = f["range_atr"]
            win = 1 if signal > 0.4 else 0
            rows.append({"day": f"2026-08-{d + 1:02d}", "time": f"2026-08-{d + 1:02d}T10:{k}5:00",
                         "slice": "NIFTY First-Hour", **f, "win": win,
                         "pnl": 2000.0 if win else -1000.0, "r": 2.0 if win else -1.0,
                         "is_first30": float(k)})
    return pd.DataFrame(rows)


def test_auc_is_one_for_perfect_separation_and_zero_for_inverted():
    import numpy as np
    from backend.engine.decision import _auc

    y = np.array([0, 0, 1, 1], dtype=float)
    assert _auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert _auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0
    assert abs(_auc(y, np.array([0.5, 0.5, 0.5, 0.5])) - 0.5) < 1e-9


def test_walk_forward_only_scores_days_it_did_not_train_on():
    from backend.engine import decision

    df = _feature_frame()
    wf = decision.walk_forward(df)
    assert wf["ok"] is True
    assert wf["oos_trades"] == len(df), "every row is scored exactly once, out of sample"
    for f in wf["folds"]:
        assert f["train_days"] + f["test_days"] == 30, "folds are a partition of the sessions"
        assert f["train_days"] > 0 and f["test_days"] > 0
    assert wf["oos_auc"] > 0.7, "a clean synthetic signal must survive walk-forward"
    # Both heads are reported, and the EV head is the one promotion depends on.
    assert "win_filters" in wf and "ev_filters" in wf


def test_decision_cannot_trade_below_the_sample_floor(tmp_path, monkeypatch):
    import json

    from backend.engine import decision

    monkeypatch.setattr(decision, "MODEL_FILE", tmp_path / "m.json")
    card = {"version": "t", "status": "active", "samples": decision.MIN_LIVE - 1,
            "w": [0.0] + [0.0] * len(decision.MODEL_FEATURES), "w_ev": [0.0] + [0.0] * len(decision.MODEL_FEATURES),
            "mu": [0.0] * len(decision.MODEL_FEATURES), "sd": [1.0] * len(decision.MODEL_FEATURES),
            "breakeven": 0.33, "threshold": 0.0}
    (tmp_path / "m.json").write_text(json.dumps(card), encoding="utf-8")
    out = decision.decide({"range_atr": 1.0}, "First-Hour")
    assert out["action"] == "SHADOW", "a promoted-looking model under the floor still cannot decide"
    assert out["confidence"] in ("none", "low")


def test_a_promoted_model_answers_go_or_no_go_on_expected_r(tmp_path, monkeypatch):
    import json

    from backend.engine import decision

    monkeypatch.setattr(decision, "MODEL_FILE", tmp_path / "m.json")
    n = len(decision.MODEL_FEATURES)
    card = {"version": "t", "status": "active", "samples": decision.MIN_LIVE,
            "w": [0.0] * (n + 1), "w_ev": [0.5] + [0.0] * n,
            "mu": [0.0] * n, "sd": [1.0] * n, "breakeven": 0.33, "threshold": 0.0}
    (tmp_path / "m.json").write_text(json.dumps(card), encoding="utf-8")
    go = decision.decide({"range_atr": 1.0}, "First-Hour")
    assert go["action"] == "GO" and go["ev_r"] > 0
    card["w_ev"] = [-0.5] + [0.0] * n
    (tmp_path / "m.json").write_text(json.dumps(card), encoding="utf-8")
    no = decision.decide({"range_atr": 1.0}, "First-Hour")
    assert no["action"] == "NO_GO" and no["ev_r"] < 0


def test_features_never_read_the_bar_they_fill_on():
    """The entry fills at bar i0's open, so nothing from i0 onwards may enter the feature vector."""
    import numpy as np
    import pandas as pd

    from backend.engine.dataset import features

    idx = pd.date_range("2026-10-28 09:15", periods=30, freq="5min", tz="Asia/Kolkata")
    rng = np.random.default_rng(3)
    close = 22600 + np.cumsum(rng.normal(0, 3, len(idx)))
    day = pd.DataFrame({"open": close, "high": close + 4, "low": close - 4,
                        "close": close, "volume": 0.0}, index=idx)
    ctx = {"hist": day, "day_start": 0, "pdh": 22700.0, "pdl": 22500.0, "pdc": 22600.0,
           "vix": 13.0, "expiry": None}
    before = features(day, 20, ctx, 1, 22600.0, float(day.open.iloc[20]))

    future = day.copy()
    future.iloc[21:, :] = future.iloc[21:, :] * 1.10  # rewrite every bar AFTER the fill
    ctx2 = {**ctx, "hist": future}
    after = features(future, 20, ctx2, 1, 22600.0, float(day.open.iloc[20]))

    assert before is not None and after is not None
    assert before == after, "a feature that changes when future bars change is lookahead"



def test_a_paper_entry_carries_the_shadow_decision(tmp_path):
    """The model records its read next to every fill. It must never be able to block one."""
    from backend.engine import trader
    pt = trader.PaperTrader(tmp_path / "p.json")
    settings = {"autopilot_strategies": ["Engine"], "capital": 100000, "risk_per_trade_pct": 1,
                "max_trades_per_day": 3, "max_daily_loss_pct": 3, "autopilot_instruments": ["NIFTY"]}
    ev = pt.on_analysis(_entry_analysis("2026-10-21T10:00:00+05:30"), settings)["events"][0]
    assert ev["type"] == "paper_entry", "the decision engine must not veto an entry while in shadow"
    assert "decision" in ev["trade"], "every fill records what the model thought of it"



def test_shadow_scorecard_compares_what_it_said_to_what_happened():
    from backend.engine import decision

    def trade(p, ev, pnl, risk):
        return {"pnl": pnl, "entry_premium": risk, "premium_stop": 0.0, "quantity": 1.0,
                "decision": {"p_win": p, "ev_r": ev}}

    closed = [trade(0.30, -0.2, -1000, 1000), trade(0.55, 0.6, 1000, 1000),
              trade(0.70, 0.9, 2000, 1000), {"pnl": 500, "decision": None}]
    sc = decision.scorecard(closed)
    assert sc["trades"] == 3, "trades without a recorded decision are not scored"
    assert sc["actual_win_rate"] == 66.7
    assert sc["predicted_p"] == 51.7
    assert sc["rank_corr"] == 1.0, "the model ranked the loser last and the biggest winner first"
    assert sc["net"] == 2000
    assert decision.scorecard([])["trades"] == 0



def test_refit_refuses_to_train_on_a_worse_feed():
    """The weekly cron runs unattended. One broker outage must not silently replace a
    broker-feed model with a shorter delayed-feed one."""
    from backend.engine import decision

    prev = {"w": [0.5], "source": "angel_one", "sessions": 64, "version": "lr-old"}
    assert decision._downgrade(prev, "yahoo_delayed", 60), "delayed feed is a downgrade"
    assert decision._downgrade(prev, "angel_one", 40), "same source, 40 vs 64 sessions is a shrink"
    assert decision._downgrade(prev, "angel_one", 70) is None, "more history is a normal refit"
    assert decision._downgrade(prev, "angel_one", 60) is None, "a small shrink is tolerated"
    upgraded = {"w": [0.5], "source": "yahoo_delayed", "sessions": 60}
    assert decision._downgrade(upgraded, "angel_one", 64) is None, "the broker feed is an upgrade"
    assert decision._downgrade(None, "yahoo_delayed", 10) is None, "the first fit has nothing to lose"
    weightless = {"source": "angel_one", "sessions": 64}
    assert decision._downgrade(weightless, "yahoo_delayed", 60) is None, "no weights, no model to protect"

    kept = decision._kept(prev, "feed downgraded")
    assert kept["ok"] is False
    assert kept["refit_refused"] == "feed downgraded"
    assert kept["w"] == [0.5] and kept["version"] == "lr-old", "the working model survives a refusal"



def test_daily_summary_groups_by_the_day_the_trade_opened():
    from backend.engine import daily

    closed = [
        {"opened_at": "2026-10-28T09:45:00+05:30", "pnl": -653, "strategy": "First-Hour"},
        {"opened_at": "2026-10-28T10:20:00+05:30", "pnl": -5090, "strategy": "First-Hour"},
        {"opened_at": "2026-10-27T09:50:00+05:30", "pnl": 1200, "strategy": "First-30"},
    ]
    days = daily.by_day(closed)
    assert [d["date"] for d in days] == ["2026-10-28", "2026-10-27"], "newest day first"
    assert days[0]["trades"] == 2 and days[0]["pnl"] == -5743 and days[0]["wins"] == 0
    assert days[1]["wins"] == 1 and days[1]["win_rate"] == 100.0

    paper = {"closed": closed, "today": {"trades": 2, "pnl": -5743, "wins": 0},
             "all_time": {"trades": 3, "pnl": -4543, "win_rate": 33.3},
             "open": [], "day_rules": {"profit_stop": 2000, "loss_stop": 2500},
             "day": {"pnl": -5743, "stopped": "loss"}}
    rep = daily.report(paper, day="2026-10-28")
    assert rep["trades"] == 2 and rep["pnl"] == -5743 and rep["stopped"] == "loss"
    assert rep["days"][0]["date"] == "2026-10-28"

    body = daily.text(rep)
    assert "2 trade(s)" in body and "Rs -5,743" in body, "the number the owner asked for is in the first line"
    assert "LOSS limit hit" in body and "All time: 3 trades" in body
    assert all(ord(ch) < 128 for ch in body), "phone messages stay ASCII"


def test_daily_summary_says_so_when_nothing_traded():
    from backend.engine import daily

    rep = daily.report({"closed": [], "today": {"trades": 0, "pnl": 0, "wins": 0},
                        "all_time": {"trades": 0, "pnl": 0, "win_rate": None}}, day="2026-10-28")
    body = daily.text(rep)
    assert "0 trade(s)" in body
    assert "No trades today" in body



def test_registry_moves_a_status_but_never_rewrites_evidence(tmp_path, monkeypatch):
    import json

    from backend.engine import experiments

    monkeypatch.setattr(experiments, "FILE", tmp_path / "experiments.jsonl")
    seeds = experiments._seed()
    stale = [dict(r) for r in seeds]
    stale = [dict(r, status="proposed") if r["id"] == 15 else r for r in stale]
    experiments.FILE.write_text("\n".join(json.dumps(r) for r in stale) + "\n", encoding="utf-8")

    old_evidence = next(r["evidence"] for r in stale if r["id"] == 15)
    rows = experiments.all()
    row15 = next(r for r in rows if r["id"] == 15)
    assert row15["status"] == "testing", "the code can move a row out of proposed"
    assert row15["evidence"] == old_evidence, "the evidence column is history and stays put"

    rows = experiments.all()
    assert next(r for r in rows if r["id"] == 15)["evidence"] == old_evidence, "stable across reads"

