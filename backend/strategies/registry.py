from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Literal, Optional

import numpy as np
import pandas as pd

from backend.ict_smart_money import ICTSmartMoney
from backend.market_data import calculate_atr, calculate_rsi, calculate_sma

TradeDirection = Literal["BUY", "SELL", "HOLD"]


@dataclass
class StrategySignal:
    strategy_id: str
    direction: TradeDirection
    confidence: float
    score: float
    rationale: str
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class StrategyContext:
    ticker: str
    df: pd.DataFrame
    regime: str = "Range-bound"
    news_bias: float = 0.0


class BaseStrategy:
    strategy_id = "base_strategy"

    def __init__(self, weight: float = 1.0):
        self.weight = float(weight)

    def generate_signals(self, context: StrategyContext) -> List[StrategySignal]:
        raise NotImplementedError


class FVGStrategy(BaseStrategy):
    strategy_id = "fvg"

    def generate_signals(self, context: StrategyContext) -> List[StrategySignal]:
        df = context.df
        if df is None or df.empty or len(df) < 30:
            return []

        ict = ICTSmartMoney(df)
        fvgs = ict.detect_fair_value_gaps()
        if not fvgs:
            return []

        price = float(df["Close"].iloc[-1])
        atr_series = calculate_atr(df["High"], df["Low"], df["Close"], 14)
        atr = float(atr_series.iloc[-1]) if len(atr_series) else price * 0.01
        atr = atr if np.isfinite(atr) and atr > 0 else price * 0.01

        candidates: List[StrategySignal] = []
        for fvg in fvgs[-50:]:
            top = float(fvg["top"])
            bottom = float(fvg["bottom"])
            mid = (top + bottom) / 2.0
            padding = max(atr * 0.15, price * 0.0006)
            near_zone = (bottom - padding) <= price <= (top + padding)
            if not near_zone:
                continue

            distance = abs(price - mid) / max(atr, 1e-6)
            proximity = max(0.0, 0.2 - min(distance, 0.2))
            base_conf = 0.62 + proximity

            if fvg["type"] == "bullish":
                direction: TradeDirection = "BUY"
                rationale = "Price interacting with bullish FVG support zone."
            else:
                direction = "SELL"
                rationale = "Price interacting with bearish FVG supply zone."

            confidence = float(min(0.9, base_conf))
            candidates.append(
                StrategySignal(
                    strategy_id=self.strategy_id,
                    direction=direction,
                    confidence=confidence,
                    score=confidence * self.weight,
                    rationale=rationale,
                    metadata={
                        "zone_top": top,
                        "zone_bottom": bottom,
                        "zone_mid": mid,
                        "atr": atr,
                    },
                )
            )

        if not candidates:
            return []
        candidates.sort(key=lambda s: s.confidence, reverse=True)
        return [candidates[0]]


class IFVGStrategy(BaseStrategy):
    strategy_id = "ifvg"

    def _to_ts(self, value: object) -> Optional[pd.Timestamp]:
        try:
            ts = pd.Timestamp(value)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            return ts
        except Exception:
            return None

    def generate_signals(self, context: StrategyContext) -> List[StrategySignal]:
        df = context.df
        if df is None or df.empty or len(df) < 40:
            return []

        local = df.copy()
        if local.index.tz is None:
            local.index = local.index.tz_localize("UTC")
        else:
            local.index = local.index.tz_convert("UTC")

        ict = ICTSmartMoney(local)
        fvgs = ict.detect_fair_value_gaps()
        if not fvgs:
            return []

        price = float(local["Close"].iloc[-1])
        atr_series = calculate_atr(local["High"], local["Low"], local["Close"], 14)
        atr = float(atr_series.iloc[-1]) if len(atr_series) else price * 0.01
        atr = atr if np.isfinite(atr) and atr > 0 else price * 0.01
        zone_padding = max(atr * 0.2, price * 0.0008)

        candidates: List[StrategySignal] = []

        for fvg in fvgs[-60:]:
            top = float(fvg["top"])
            bottom = float(fvg["bottom"])
            end_ts = self._to_ts(fvg.get("end_time"))
            if end_ts is None:
                continue

            future = local[local.index > end_ts]
            if future.empty:
                continue

            # Inverse FVG logic:
            # - Bullish FVG invalidated to downside -> becomes bearish IFVG.
            # - Bearish FVG invalidated to upside -> becomes bullish IFVG.
            if fvg["type"] == "bullish":
                invalidated = bool((future["Low"] < bottom).any())
                if not invalidated:
                    continue
                retested = (bottom - zone_padding) <= price <= (top + zone_padding)
                if not retested:
                    continue

                candidates.append(
                    StrategySignal(
                        strategy_id=self.strategy_id,
                        direction="SELL",
                        confidence=0.72,
                        score=0.72 * self.weight,
                        rationale="Bullish FVG invalidated and acting as inverse bearish resistance (IFVG).",
                        metadata={
                            "ifvg_type": "bearish_inverse",
                            "zone_top": top,
                            "zone_bottom": bottom,
                            "invalidated": True,
                        },
                    )
                )
            else:
                invalidated = bool((future["High"] > top).any())
                if not invalidated:
                    continue
                retested = (bottom - zone_padding) <= price <= (top + zone_padding)
                if not retested:
                    continue

                candidates.append(
                    StrategySignal(
                        strategy_id=self.strategy_id,
                        direction="BUY",
                        confidence=0.72,
                        score=0.72 * self.weight,
                        rationale="Bearish FVG invalidated and acting as inverse bullish support (IFVG).",
                        metadata={
                            "ifvg_type": "bullish_inverse",
                            "zone_top": top,
                            "zone_bottom": bottom,
                            "invalidated": True,
                        },
                    )
                )

        if not candidates:
            return []
        candidates.sort(key=lambda s: s.confidence, reverse=True)
        return [candidates[0]]


class OrderBlockStrategy(BaseStrategy):
    strategy_id = "order_block"

    def generate_signals(self, context: StrategyContext) -> List[StrategySignal]:
        df = context.df
        if df is None or df.empty or len(df) < 30:
            return []

        ict = ICTSmartMoney(df)
        order_blocks = ict.detect_order_blocks()
        if not order_blocks:
            return []

        price = float(df["Close"].iloc[-1])
        atr_series = calculate_atr(df["High"], df["Low"], df["Close"], 14)
        atr = float(atr_series.iloc[-1]) if len(atr_series) else price * 0.01
        atr = atr if np.isfinite(atr) and atr > 0 else price * 0.01

        candidates: List[StrategySignal] = []
        for ob in order_blocks[-40:]:
            top = float(ob["top"])
            bottom = float(ob["bottom"])
            near_zone = (bottom - atr * 0.15) <= price <= (top + atr * 0.15)
            if not near_zone:
                continue

            if ob["type"] == "bullish_ob":
                direction: TradeDirection = "BUY"
                rationale = "Price near bullish order block demand zone."
            else:
                direction = "SELL"
                rationale = "Price near bearish order block supply zone."

            candidates.append(
                StrategySignal(
                    strategy_id=self.strategy_id,
                    direction=direction,
                    confidence=0.66,
                    score=0.66 * self.weight,
                    rationale=rationale,
                    metadata={"zone_top": top, "zone_bottom": bottom},
                )
            )

        if not candidates:
            return []
        candidates.sort(key=lambda s: s.confidence, reverse=True)
        return [candidates[0]]


class MomentumAlignmentStrategy(BaseStrategy):
    strategy_id = "momentum_alignment"

    def generate_signals(self, context: StrategyContext) -> List[StrategySignal]:
        df = context.df
        if df is None or df.empty or len(df) < 60:
            return []

        close = df["Close"]
        sma_21 = calculate_sma(close, 21)
        sma_50 = calculate_sma(close, 50)
        rsi = calculate_rsi(close, 14)

        last_s21 = float(sma_21.iloc[-1]) if np.isfinite(sma_21.iloc[-1]) else None
        last_s50 = float(sma_50.iloc[-1]) if np.isfinite(sma_50.iloc[-1]) else None
        last_rsi = float(rsi.iloc[-1]) if np.isfinite(rsi.iloc[-1]) else 50.0

        if last_s21 is None or last_s50 is None:
            return []

        if last_s21 > last_s50 and 45 <= last_rsi <= 72:
            return [
                StrategySignal(
                    strategy_id=self.strategy_id,
                    direction="BUY",
                    confidence=0.62,
                    score=0.62 * self.weight,
                    rationale="SMA21 above SMA50 with healthy RSI trend momentum.",
                    metadata={"sma21": last_s21, "sma50": last_s50, "rsi": last_rsi},
                )
            ]

        if last_s21 < last_s50 and 28 <= last_rsi <= 55:
            return [
                StrategySignal(
                    strategy_id=self.strategy_id,
                    direction="SELL",
                    confidence=0.62,
                    score=0.62 * self.weight,
                    rationale="SMA21 below SMA50 with bearish momentum alignment.",
                    metadata={"sma21": last_s21, "sma50": last_s50, "rsi": last_rsi},
                )
            ]

        return []


class StrategyRegistry:
    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        self._strategies[strategy.strategy_id] = strategy

    def list_ids(self) -> List[str]:
        return list(self._strategies.keys())

    def run(self, context: StrategyContext) -> Dict[str, object]:
        signals: List[StrategySignal] = []
        by_strategy: Dict[str, List[Dict[str, object]]] = {}

        for strategy_id, strategy in self._strategies.items():
            try:
                strategy_signals = strategy.generate_signals(context)
            except Exception as exc:
                strategy_signals = [
                    StrategySignal(
                        strategy_id=strategy_id,
                        direction="HOLD",
                        confidence=0.0,
                        score=0.0,
                        rationale=f"Strategy error: {exc}",
                        metadata={"error": str(exc)},
                    )
                ]

            cleaned = [s for s in strategy_signals if s.direction != "HOLD"]
            signals.extend(cleaned)
            by_strategy[strategy_id] = [asdict(s) for s in cleaned]

        buy_score = float(sum(s.score for s in signals if s.direction == "BUY"))
        sell_score = float(sum(s.score for s in signals if s.direction == "SELL"))
        total_conf = float(sum(s.confidence for s in signals))
        count = max(len(signals), 1)
        avg_confidence = total_conf / count

        net = buy_score - sell_score
        if net > 0.12:
            action: TradeDirection = "BUY"
        elif net < -0.12:
            action = "SELL"
        else:
            action = "HOLD"

        return {
            "signals": [asdict(s) for s in signals],
            "by_strategy": by_strategy,
            "buy_score": round(buy_score, 4),
            "sell_score": round(sell_score, 4),
            "net_score": round(net, 4),
            "avg_confidence": round(avg_confidence, 4),
            "action": action,
        }


def build_default_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(FVGStrategy(weight=1.0))
    registry.register(IFVGStrategy(weight=1.05))
    registry.register(OrderBlockStrategy(weight=0.95))
    registry.register(MomentumAlignmentStrategy(weight=0.8))
    return registry
