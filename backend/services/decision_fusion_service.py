from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from backend.market_data import (
    calculate_atr,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    get_market_regime_async,
)
from backend.monte_carlo import quick_risk_assessment
from backend.quant_engine import get_quant_analysis
from backend.services.market_data_service import get_sync_market_data, normalize_period_for_interval
from backend.services.data_quality_service import data_quality_service
from backend.services.memory_service import memory_service
from backend.strategies import StrategyContext, StrategyRegistry, build_default_registry


@dataclass
class FusionWeights:
    strategy: float = 0.30
    ml_confirmation: float = 0.20
    regime: float = 0.15
    quant: float = 0.15
    news: float = 0.10
    risk_penalty: float = 0.10


class DecisionFusionService:
    """
    Unified decision layer that fuses:
    - Strategy registry signals (FVG/IFVG/OB/Momentum)
    - Regime diagnostics
    - Quant diagnostics
    - News impact sentiment
    - Monte Carlo forward risk
    """

    def __init__(self, registry: Optional[StrategyRegistry] = None, weights: Optional[FusionWeights] = None):
        self.registry = registry or build_default_registry()
        self.weights = weights or FusionWeights()

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        local = df.copy()
        if isinstance(local.columns, pd.MultiIndex):
            local.columns = local.columns.get_level_values(0)
        local.columns = [str(c).capitalize() for c in local.columns]
        if "Adj close" in local.columns and "Close" not in local.columns:
            local["Close"] = local["Adj close"]
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in local.columns:
                return pd.DataFrame()
            local[col] = pd.to_numeric(local[col], errors="coerce")
        local = local.dropna(subset=["Open", "High", "Low", "Close"])
        local["Volume"] = local["Volume"].fillna(0.0)
        return local

    def _load_market_data(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        period = normalize_period_for_interval(period, interval)
        df = get_sync_market_data(ticker=ticker, period=period, interval=interval)
        return self._normalize_df(df)

    @staticmethod
    async def _fetch_news_items(ticker: str, interval: str) -> List[Dict[str, Any]]:
        try:
            from backend.services.news_ml_service import news_ml_service
            return await news_ml_service.get_global_news_impact(benchmark_ticker=ticker, interval=interval)
        except Exception:
            # News pipeline is optional for fusion fallback mode.
            return []

    @staticmethod
    def _safe_last(series: pd.Series, default: float = 0.0) -> float:
        if series is None or len(series) == 0:
            return float(default)
        val = series.iloc[-1]
        if not np.isfinite(val):
            return float(default)
        return float(val)

    @staticmethod
    def _session_bucket(df: pd.DataFrame) -> str:
        if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
            return "unknown"
        ts = df.index[-1]
        if getattr(ts, "tzinfo", None) is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        hour = int(ts.hour)
        if 9 <= hour < 11:
            return "open"
        if 11 <= hour < 14:
            return "midday"
        if 14 <= hour < 16:
            return "close"
        return "offhours"

    @staticmethod
    def _derive_setup_family(strategy_pack: Dict[str, Any]) -> Optional[str]:
        signals = list(strategy_pack.get("signals", []) or [])
        if not signals:
            return None
        first = signals[0] or {}
        pattern = str(first.get("pattern") or first.get("strategy") or first.get("signal") or "").strip().lower()
        if "ifvg" in pattern:
            return "ifvg"
        if "fvg" in pattern:
            return "fvg"
        if "order block" in pattern or pattern == "ob":
            return "order_block"
        if "sweep" in pattern or "liquidity" in pattern or "stop hunt" in pattern:
            return "liquidity_sweep"
        return pattern or None

    @staticmethod
    def _build_memory_query(
        ticker: str,
        regime_payload: Dict[str, Any],
        strategy_pack: Dict[str, Any],
        news_summary: Dict[str, Any],
    ) -> str:
        parts = [ticker]
        regime = str(regime_payload.get("regime") or "").strip()
        if regime:
            parts.append(regime)
        action = str(strategy_pack.get("action") or "").strip()
        if action:
            parts.append(action)
        setup_family = DecisionFusionService._derive_setup_family(strategy_pack)
        if setup_family:
            parts.append(setup_family)
        if float(news_summary.get("avg_affect_rate", 0.0) or 0.0) >= 40.0:
            parts.append("high impact news")
        return " ".join(part for part in parts if part)

    def _extract_ml_features(self, df: pd.DataFrame, news_summary: Dict[str, Any]) -> Dict[str, float]:
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        sma20 = calculate_sma(close, 20)
        sma50 = calculate_sma(close, 50)
        rsi14 = calculate_rsi(close, 14)
        atr14 = calculate_atr(high, low, close, 14)
        macd, macd_signal = calculate_macd(close)

        vol_std = close.pct_change().rolling(20).std()
        vol_mean = volume.rolling(20).mean()
        vol_std20 = volume.rolling(20).std().replace(0, np.nan)

        features = {
            "ret_1": self._safe_last(close.pct_change(1), 0.0),
            "ret_3": self._safe_last(close.pct_change(3), 0.0),
            "ret_5": self._safe_last(close.pct_change(5), 0.0),
            "volatility_20": self._safe_last(vol_std, 0.0),
            "sma20_dist": self._safe_last((close - sma20) / sma20.replace(0, np.nan), 0.0),
            "sma50_dist": self._safe_last((close - sma50) / sma50.replace(0, np.nan), 0.0),
            "sma_trend": self._safe_last((sma20 - sma50) / sma50.replace(0, np.nan), 0.0),
            "rsi_14": self._safe_last(rsi14, 50.0),
            "atr_norm": self._safe_last(atr14 / close.replace(0, np.nan), 0.0),
            "macd": self._safe_last(macd, 0.0),
            "macd_signal": self._safe_last(macd_signal, 0.0),
            "macd_hist": self._safe_last(macd - macd_signal, 0.0),
            "volume_z20": self._safe_last((volume - vol_mean) / vol_std20, 0.0),
            "news_affect": float(news_summary.get("avg_affect_rate", 0.0) or 0.0),
            "news_bias": float(news_summary.get("directional_bias", 0.0) or 0.0),
            "news_crash_ratio": float(news_summary.get("crash_warning_ratio", 0.0) or 0.0),
        }
        return {k: float(v if np.isfinite(v) else 0.0) for k, v in features.items()}

    @staticmethod
    def _get_ml_confirmation(features: Dict[str, float]) -> Dict[str, Any]:
        try:
            from backend.services.fusion_model_service import fusion_model_service

            pred = fusion_model_service.predict(features)
            if pred.get("status") != "success":
                return {
                    "available": False,
                    "action": "HOLD",
                    "confidence": 0.0,
                    "component": 0.0,
                    "probability_up": 0.5,
                    "reason": pred.get("message", "Model unavailable"),
                }

            prob_up = float(pred.get("probability_up", 0.5))
            component = float(np.clip((prob_up - 0.5) * 2.0, -1.0, 1.0))
            if component > 0.06:
                action = "BUY"
            elif component < -0.06:
                action = "SELL"
            else:
                action = "HOLD"

            return {
                "available": True,
                "action": action,
                "confidence": round(abs(component), 4),
                "component": round(component, 4),
                "probability_up": round(prob_up, 6),
                "reason": "ok",
            }
        except Exception as exc:
            return {
                "available": False,
                "action": "HOLD",
                "confidence": 0.0,
                "component": 0.0,
                "probability_up": 0.5,
                "reason": f"Model unavailable: {exc}",
            }

    @staticmethod
    def _regime_score(regime_payload: Dict[str, Any]) -> float:
        regime = str(regime_payload.get("regime", "Range-bound")).lower()
        conf = float(regime_payload.get("confidence", 0.5) or 0.5)

        mapping = {
            "strong uptrend": 0.75,
            "uptrend": 0.55,
            "strong downtrend": -0.75,
            "downtrend": -0.55,
            "volatility expansion": 0.0,
            "range-bound": 0.0,
        }

        base = 0.0
        for key, val in mapping.items():
            if key in regime:
                base = val
                break
        return float(base * conf)

    @staticmethod
    def _quant_score(quant_payload: Dict[str, Any]) -> float:
        if not quant_payload or quant_payload.get("error"):
            return 0.0

        score = 0.0
        regime_status = str((quant_payload.get("regime") or {}).get("status", "")).lower()
        if "stable" in regime_status:
            score += 0.15
        if "drift" in regime_status or "shift" in regime_status:
            score -= 0.15

        risk = quant_payload.get("risk_assessment") or {}
        var95 = float(risk.get("var_95", 0.0) or 0.0)
        exp_ret = float(risk.get("expected_return", 0.0) or 0.0)

        # Lower VaR loss and positive expected return improve score.
        score += 0.20 if var95 < 4.0 else (-0.20 if var95 > 8.0 else 0.0)
        score += 0.20 if exp_ret > 0 else -0.10

        return float(np.clip(score, -1.0, 1.0))

    @staticmethod
    def _news_summary(news_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not news_items:
            return {
                "headline_count": 0,
                "avg_affect_rate": 0.0,
                "directional_bias": 0.0,
                "crash_warning_ratio": 0.0,
            }

        top = news_items[:12]
        affect = np.array([float(item.get("affect_rate", 0.0) or 0.0) for item in top], dtype=float)
        dirs = [str(item.get("market_direction", "NEUTRAL")).upper() for item in top]

        bullish = sum(1 for d in dirs if d == "BULLISH")
        bearish = sum(1 for d in dirs if d in {"BEARISH", "CRASH_WARNING"})
        crash = sum(1 for d in dirs if d == "CRASH_WARNING")
        total = max(len(top), 1)

        directional_bias = (bullish - bearish) / total

        return {
            "headline_count": len(top),
            "avg_affect_rate": float(np.mean(affect)) if len(affect) else 0.0,
            "directional_bias": float(np.clip(directional_bias, -1.0, 1.0)),
            "crash_warning_ratio": float(crash / total),
        }

    @staticmethod
    def _risk_penalty(mc_payload: Dict[str, Any], news_summary: Dict[str, Any]) -> float:
        if not mc_payload or mc_payload.get("error"):
            return 0.35

        prob_down_10 = float(mc_payload.get("probability_down_10%", 0.0) or 0.0)
        var_pct = float(((mc_payload.get("risk_metrics") or {}).get("var_percent", 0.0)) or 0.0)
        var_norm = float(np.clip(abs(var_pct) / 15.0, 0.0, 1.0))

        news_shock = float(news_summary.get("avg_affect_rate", 0.0) / 100.0)
        crash_ratio = float(news_summary.get("crash_warning_ratio", 0.0))

        penalty = 0.45 * prob_down_10 + 0.35 * var_norm + 0.15 * news_shock + 0.05 * crash_ratio
        return float(np.clip(penalty, 0.0, 1.0))

    def _build_adaptive_weights(
        self,
        strategy_pack: Dict[str, Any],
        ml_confirmation: Dict[str, Any],
        quant_payload: Dict[str, Any],
        news_summary: Dict[str, Any],
        news_runtime: Dict[str, Any],
        data_quality: Dict[str, Any],
        execution_quality: Dict[str, Any],
        ticker: str,
    ) -> Dict[str, Any]:
        base = self.weights
        components = {
            "strategy": float(base.strategy),
            "ml_confirmation": float(base.ml_confirmation),
            "regime": float(base.regime),
            "quant": float(base.quant),
            "news": float(base.news),
        }
        notes: List[str] = []

        strategy_conf = float(strategy_pack.get("avg_confidence", 0.0) or 0.0)
        signal_count = int(len(strategy_pack.get("signals", [])))
        if signal_count >= 2 and strategy_conf >= 0.55:
            components["strategy"] *= 1.12
            notes.append("Strategy layer boosted due to multi-signal structural alignment.")
        elif signal_count == 0:
            components["strategy"] *= 0.72
            notes.append("Strategy layer reduced because no structure setup is active.")

        ml_meta = {}
        try:
            from backend.services.fusion_model_service import fusion_model_service

            ml_meta_result = fusion_model_service.get_latest_meta()
            if ml_meta_result.get("status") == "success":
                ml_meta = ml_meta_result.get("meta") or {}
        except Exception:
            ml_meta = {}

        if not ml_confirmation.get("available"):
            components["ml_confirmation"] *= 0.20
            notes.append("ML confirmation reduced because no trained fusion model is available.")
        else:
            metrics = ml_meta.get("metrics") or {}
            accuracy = float(metrics.get("accuracy", 0.0) or 0.0)
            brier = float(metrics.get("brier", 0.5) or 0.5)
            if accuracy >= 0.58 and brier <= 0.22:
                components["ml_confirmation"] *= 1.18
                notes.append("ML confirmation boosted by recent calibration/accuracy metrics.")
            elif accuracy < 0.52 or brier >= 0.26:
                components["ml_confirmation"] *= 0.58
                notes.append("ML confirmation reduced because model metrics are weak.")

        if quant_payload.get("error"):
            components["quant"] *= 0.35
            notes.append("Quant layer reduced because quant diagnostics returned an error.")

        news_mode = str(news_runtime.get("last_mode", "")).lower()
        headline_count = int(news_summary.get("headline_count", 0) or 0)
        if news_mode == "synthetic_fallback":
            components["news"] *= 0.15
            notes.append("News weight heavily reduced because the feed is synthetic.")
        elif headline_count < 3:
            components["news"] *= 0.45
            notes.append("News weight reduced because headline coverage is too thin.")

        quality_score = float(data_quality.get("score", 0.0) or 0.0)
        quality_status = str(data_quality.get("status", "critical")).lower()
        risk_penalty = float(base.risk_penalty)
        if quality_status in {"degraded", "critical"}:
            damp = 0.72 if quality_status == "degraded" else 0.50
            for key in components:
                components[key] *= damp
            risk_penalty *= 1.45 if quality_status == "critical" else 1.20
            notes.append("All directional modules were damped because input market data quality is weak.")
        elif quality_score < 0.75:
            risk_penalty *= 1.10
            notes.append("Risk penalty increased due to minor data-quality issues.")

        execution_summary = execution_quality.get("summary") or {}
        execution_score = float(execution_summary.get("quality_score", 1.0) or 1.0)
        reject_rate = float(execution_summary.get("reject_rate", 0.0) or 0.0)
        avg_slippage_bps = float(execution_summary.get("avg_slippage_bps", 0.0) or 0.0)
        total_orders = int(execution_summary.get("total_orders", 0) or 0)
        if total_orders >= 6:
            if execution_score < 0.52 or reject_rate >= 20.0:
                for key in components:
                    components[key] *= 0.84
                risk_penalty *= 1.22
                notes.append("Directional modules reduced because live execution quality is degraded.")
            elif avg_slippage_bps >= 10.0:
                components["strategy"] *= 0.92
                components["ml_confirmation"] *= 0.92
                risk_penalty *= 1.10
                notes.append("Execution slippage is elevated, so entry-sensitive layers were damped.")
            elif execution_score >= 0.82 and reject_rate <= 5.0:
                components["strategy"] *= 1.04
                components["ml_confirmation"] *= 1.04
                notes.append("Execution quality is strong, allowing a modest confidence boost.")

        live_component_rows: List[Dict[str, Any]] = []
        try:
            from backend.services.live_signal_tracker_service import live_signal_tracker_service

            live_summary = live_signal_tracker_service.get_summary(ticker=ticker)
            live_component_rows = list(live_summary.get("component_reliability", []) or [])
            for row in live_component_rows:
                name = str(row.get("component", ""))
                samples = int(row.get("samples", 0) or 0)
                hit_rate = float(row.get("hit_rate", 0.0) or 0.0)
                if name not in components or samples < 8:
                    continue
                if hit_rate >= 58.0:
                    components[name] *= 1.10
                    notes.append(f"Live scorecard boosted {name} after {samples} settled samples.")
                elif hit_rate <= 45.0:
                    components[name] *= 0.72
                    notes.append(f"Live scorecard reduced {name} after weak settled performance.")
        except Exception:
            live_component_rows = []

        comp_target = float(base.strategy + base.ml_confirmation + base.regime + base.quant + base.news)
        comp_sum = float(sum(components.values()))
        if comp_sum <= 0:
            components = {
                "strategy": comp_target,
                "ml_confirmation": 0.0,
                "regime": 0.0,
                "quant": 0.0,
                "news": 0.0,
            }
        else:
            scale = comp_target / comp_sum
            components = {key: float(val * scale) for key, val in components.items()}

        adapted = FusionWeights(
            strategy=components["strategy"],
            ml_confirmation=components["ml_confirmation"],
            regime=components["regime"],
            quant=components["quant"],
            news=components["news"],
            risk_penalty=float(np.clip(risk_penalty, 0.05, 0.24)),
        )
        return {
            "weights": adapted,
            "notes": notes or ["Base fusion weights applied."],
            "ml_meta": ml_meta,
            "live_component_reliability": live_component_rows,
        }

    def _fuse_scores(
        self,
        strategy_pack: Dict[str, Any],
        ml_confirmation: Dict[str, Any],
        regime_payload: Dict[str, Any],
        quant_payload: Dict[str, Any],
        news_summary: Dict[str, Any],
        mc_payload: Dict[str, Any],
        weights: Optional[FusionWeights] = None,
        data_quality: Optional[Dict[str, Any]] = None,
        execution_quality: Optional[Dict[str, Any]] = None,
        memory_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        strategy_component = float(np.clip(strategy_pack.get("net_score", 0.0), -1.0, 1.0))
        ml_component = float(np.clip(ml_confirmation.get("component", 0.0), -1.0, 1.0))
        regime_component = self._regime_score(regime_payload)
        quant_component = self._quant_score(quant_payload)
        news_component = float(np.clip(news_summary.get("directional_bias", 0.0), -1.0, 1.0))
        penalty = self._risk_penalty(mc_payload, news_summary)
        memory_influence = (memory_context or {}).get("influence") or {}
        memory_alignment_bias = float(np.clip(memory_influence.get("alignment_bias", 0.0) or 0.0, -0.25, 0.25))
        memory_risk_bias = float(np.clip(memory_influence.get("risk_bias", 0.0) or 0.0, -0.18, 0.18))
        penalty = float(np.clip(penalty + memory_risk_bias, 0.0, 1.0))

        w = weights or self.weights
        raw_score = (
            w.strategy * strategy_component
            + w.ml_confirmation * ml_component
            + w.regime * regime_component
            + w.quant * quant_component
            + w.news * news_component
            - w.risk_penalty * penalty
        )
        raw_score += memory_alignment_bias * 0.06
        raw_score = float(np.clip(raw_score, -1.0, 1.0))

        strategy_action = str(strategy_pack.get("action", "HOLD")).upper()
        strategy_conf = float(strategy_pack.get("avg_confidence", 0.0) or 0.0)
        ml_action = str(ml_confirmation.get("action", "HOLD")).upper()
        ml_conf = float(ml_confirmation.get("confidence", 0.0) or 0.0)

        coordination_notes: List[str] = []
        conflict_detected = False

        # Conflict dampener: if structure and ML strongly disagree, do not force trades.
        if (
            strategy_action in {"BUY", "SELL"}
            and ml_action in {"BUY", "SELL"}
            and strategy_action != ml_action
            and strategy_conf >= 0.55
            and ml_conf >= 0.35
        ):
            conflict_detected = True
            raw_score *= 0.55
            coordination_notes.append("Strong conflict between structure signal and ML confirmation.")

        if int(memory_influence.get("memory_count", 0) or 0) > 0:
            coordination_notes.extend(list(memory_influence.get("notes", [])[:2]))

        # Hard risk veto for extreme downside / shock conditions.
        risk_veto = bool(penalty > 0.78 or float(news_summary.get("crash_warning_ratio", 0.0)) >= 0.34)
        risk_veto_reason = ""
        if risk_veto:
            risk_veto_reason = "Risk veto: elevated Monte Carlo downside or crash-warning news regime."
            action = "HOLD"
            coordination_notes.append(risk_veto_reason)
        else:
            if raw_score > 0.10:
                action = "BUY"
            elif raw_score < -0.10:
                action = "SELL"
            else:
                action = "HOLD"

        # Setup gate: require either structural setup or strong ML conviction.
        if (
            not risk_veto
            and action != "HOLD"
            and strategy_action == "HOLD"
            and ml_conf < 0.35
        ):
            action = "HOLD"
            coordination_notes.append("No structural setup and ML conviction is too weak.")

        if not risk_veto and action != "HOLD" and strategy_action in {"BUY", "SELL"} and action != strategy_action:
            if abs(raw_score) < 0.22:
                action = "HOLD"
                coordination_notes.append("Direction disagreement resolved to HOLD due to low net edge.")

        quality_status = str((data_quality or {}).get("status", "")).lower()
        quality_score = float((data_quality or {}).get("score", 1.0) or 1.0)
        execution_summary = (execution_quality or {}).get("summary") or {}
        execution_score = float(execution_summary.get("quality_score", 1.0) or 1.0)
        reject_rate = float(execution_summary.get("reject_rate", 0.0) or 0.0)
        avg_slippage_bps = float(execution_summary.get("avg_slippage_bps", 0.0) or 0.0)
        total_orders = int(execution_summary.get("total_orders", 0) or 0)
        if action != "HOLD" and quality_status == "critical":
            action = "HOLD"
            coordination_notes.append("Trading veto: data quality is critical.")
        elif action != "HOLD" and quality_score < 0.35:
            action = "HOLD"
            coordination_notes.append("Trading veto: data quality score is too low.")
        elif action != "HOLD" and total_orders >= 8 and execution_score < 0.30:
            action = "HOLD"
            coordination_notes.append("Trading veto: live execution quality is too poor.")

        confidence = float(np.clip(0.35 + abs(raw_score) * 0.9, 0.0, 0.98))
        if conflict_detected:
            confidence *= 0.75
        if quality_score < 0.75:
            confidence *= float(np.clip(quality_score + 0.15, 0.35, 1.0))
        risk_budget = float(np.clip(1.0 - penalty * 0.65, 0.20, 1.15))
        if quality_score < 0.70:
            risk_budget *= float(np.clip(quality_score + 0.20, 0.30, 1.0))
        if total_orders >= 6:
            if execution_score < 0.55:
                damp = float(np.clip(execution_score + 0.20, 0.25, 0.82))
                confidence *= damp
                risk_budget *= damp
                coordination_notes.append("Execution quality damped confidence and risk budget.")
            if reject_rate >= 15.0:
                risk_budget *= 0.78
                coordination_notes.append("Broker reject rate is elevated, so risk size was reduced.")
            if avg_slippage_bps >= 12.0:
                risk_budget *= 0.88
                coordination_notes.append("High realized slippage reduced position size.")
        position_multiplier = float(np.clip(confidence * risk_budget, 0.10, 1.10))

        return {
            "action": action,
            "raw_score": round(raw_score, 4),
            "confidence": round(confidence, 4),
            "risk_budget": round(risk_budget, 4),
            "position_multiplier": round(position_multiplier, 4),
            "components": {
                "strategy": round(strategy_component, 4),
                "ml_confirmation": round(ml_component, 4),
                "regime": round(regime_component, 4),
                "quant": round(quant_component, 4),
                "news": round(news_component, 4),
                "risk_penalty": round(penalty, 4),
                "memory_alignment": round(memory_alignment_bias, 4),
                "memory_risk_bias": round(memory_risk_bias, 4),
            },
            "coordination": {
                "strategy_action": strategy_action,
                "strategy_confidence": round(strategy_conf, 4),
                "ml_action": ml_action,
                "ml_confidence": round(ml_conf, 4),
                "conflict_detected": conflict_detected,
                "risk_veto": risk_veto,
                "risk_veto_reason": risk_veto_reason or None,
                "notes": coordination_notes,
            },
        }

    def _apply_memory_guidance(self, adaptive: Dict[str, Any], memory_context: Dict[str, Any]) -> Dict[str, Any]:
        influence = (memory_context or {}).get("influence") or {}
        count = int(influence.get("memory_count", 0) or 0)
        if count <= 0:
            return adaptive

        hints = influence.get("component_hints") or {}
        weights = adaptive.get("weights") or self.weights
        components = {
            "strategy": float(weights.strategy) * float(np.clip(hints.get("strategy", 1.0), 0.94, 1.08)),
            "ml_confirmation": float(weights.ml_confirmation) * float(np.clip(hints.get("ml_confirmation", 1.0), 0.96, 1.04)),
            "regime": float(weights.regime) * float(np.clip(hints.get("regime", 1.0), 0.95, 1.06)),
            "quant": float(weights.quant) * float(np.clip(hints.get("quant", 1.0), 0.96, 1.04)),
            "news": float(weights.news) * float(np.clip(hints.get("news", 1.0), 0.94, 1.08)),
        }
        target_sum = float(sum(components.values()))
        baseline_sum = float(weights.strategy + weights.ml_confirmation + weights.regime + weights.quant + weights.news)
        if target_sum > 0:
            scale = baseline_sum / target_sum
            components = {key: float(value * scale) for key, value in components.items()}

        memory_risk_bias = float(np.clip(influence.get("risk_bias", 0.0) or 0.0, -0.08, 0.08))
        notes = list(adaptive.get("notes", []) or [])
        notes.extend(list(influence.get("notes", []) or []))
        notes.append(f"Memory layer attached {count} scoped memories as advisory context.")

        adaptive["weights"] = FusionWeights(
            strategy=components["strategy"],
            ml_confirmation=components["ml_confirmation"],
            regime=components["regime"],
            quant=components["quant"],
            news=components["news"],
            risk_penalty=float(np.clip(float(weights.risk_penalty) + memory_risk_bias, 0.05, 0.24)),
        )
        adaptive["notes"] = notes
        adaptive["memory_influence"] = influence
        return adaptive

    async def generate_decision(
        self,
        ticker: str = "^NSEI",
        period: str = "60d",
        interval: str = "15m",
        capital: float = 100000.0,
    ) -> Dict[str, Any]:
        period = normalize_period_for_interval(period, interval)
        df = self._load_market_data(ticker=ticker, period=period, interval=interval)
        if df.empty:
            return {"status": "error", "message": f"No market data available for {ticker}"}

        news_task = asyncio.create_task(self._fetch_news_items(ticker=ticker, interval=interval))
        regime_task = asyncio.create_task(get_market_regime_async(ticker))

        quant_payload = get_quant_analysis(ticker=ticker, period="1y", interval="1d")
        mc_payload = quick_risk_assessment(ticker=ticker, days_ahead=10, n_simulations=2000)

        news_items = await news_task
        regime_payload = await regime_task

        news_summary = self._news_summary(news_items)
        data_quality = data_quality_service.assess_dataframe(df, interval)
        session_bucket = self._session_bucket(df)
        strategy_context = StrategyContext(
            ticker=ticker,
            df=df,
            regime=str(regime_payload.get("regime", "Range-bound")),
            news_bias=float(news_summary.get("directional_bias", 0.0)),
        )
        strategy_pack = self.registry.run(strategy_context)
        setup_family = self._derive_setup_family(strategy_pack)
        ml_features = self._extract_ml_features(df, news_summary)
        ml_confirmation = self._get_ml_confirmation(ml_features)
        memory_context = memory_service.build_context(
            ticker=ticker,
            interval=interval,
            regime=str(regime_payload.get("regime", "") or ""),
            session_bucket=session_bucket,
            setup_family=setup_family,
            query=self._build_memory_query(
                ticker=ticker,
                regime_payload=regime_payload,
                strategy_pack=strategy_pack,
                news_summary=news_summary,
            ),
            limit=6,
        )
        news_runtime = {}
        news_event_study = {}
        execution_quality = {}
        try:
            from backend.services.news_ml_service import news_ml_service

            news_runtime = news_ml_service.get_runtime_status()
        except Exception:
            news_runtime = {}
        try:
            from backend.services.news_event_study_service import news_event_study_service

            news_event_study = news_event_study_service.get_latest(benchmark_ticker=ticker, interval=interval)
        except Exception:
            news_event_study = {}
        try:
            from backend.services.execution_quality_service import execution_quality_service

            execution_quality = execution_quality_service.get_summary(ticker=ticker)
        except Exception:
            execution_quality = {}
        adaptive = self._build_adaptive_weights(
            strategy_pack=strategy_pack,
            ml_confirmation=ml_confirmation,
            quant_payload=quant_payload,
            news_summary=news_summary,
            news_runtime=news_runtime,
            data_quality=data_quality,
            execution_quality=execution_quality,
            ticker=ticker,
        )
        adaptive = self._apply_memory_guidance(adaptive, memory_context)

        fused = self._fuse_scores(
            strategy_pack=strategy_pack,
            ml_confirmation=ml_confirmation,
            regime_payload=regime_payload,
            quant_payload=quant_payload,
            news_summary=news_summary,
            mc_payload=mc_payload,
            weights=adaptive["weights"],
            data_quality=data_quality,
            execution_quality=execution_quality,
            memory_context=memory_context,
        )

        execution_forecast = {
            "status": "success",
            "forecast": {
                "sample_count": 0,
                "basis": "none",
                "session_bucket": None,
                "quality_score": 0.5,
                "expected_slippage_bps": 0.0,
                "expected_reject_rate": 0.0,
                "expected_pending_rate": 0.0,
                "expected_fill_ratio": 1.0,
                "expected_time_to_fill_ms": 0.0,
                "expected_latency_ms": 0.0,
                "risk_multiplier": 1.0,
                "recommendation": "no_history",
            },
        }
        routing_directive = {"status": "success", "directive": "proceed", "reason": "No routing adjustment.", "snapshot": {}}
        if fused.get("action") in {"BUY", "SELL"}:
            try:
                from backend.services.execution_quality_service import execution_quality_service
                from backend.services.routing_service import routing_service
                from backend.services.service_manager import service_manager

                broker_name = type(service_manager.execution_engine.broker).__name__
                routing_directive = routing_service.get_execution_directive(ticker=ticker)
                execution_forecast = execution_quality_service.forecast_execution(
                    symbol=ticker,
                    side=str(fused.get("action")),
                    broker=broker_name,
                    order_type="MARKET",
                )
                forecast = execution_forecast.get("forecast") or {}
                forecast_samples = int(forecast.get("sample_count", 0) or 0)
                forecast_multiplier = float(forecast.get("risk_multiplier", 1.0) or 1.0)
                if forecast_samples >= 4:
                    fused["confidence"] = round(float(fused.get("confidence", 0.0) or 0.0) * forecast_multiplier, 4)
                    fused["risk_budget"] = round(float(fused.get("risk_budget", 0.0) or 0.0) * forecast_multiplier, 4)
                    fused["position_multiplier"] = round(
                        float(np.clip(float(fused["confidence"]) * float(fused["risk_budget"]), 0.10, 1.10)),
                        4,
                    )
                    fused["coordination"]["notes"].append("Pre-trade execution forecast adjusted confidence and risk sizing.")
                if forecast.get("recommendation") == "avoid" and forecast_samples >= 8:
                    fused["action"] = "HOLD"
                    fused["coordination"]["notes"].append("Pre-trade execution forecast vetoed the setup.")
                directive = str(routing_directive.get("directive", "proceed"))
                if directive == "halt":
                    fused["action"] = "HOLD"
                    fused["coordination"]["notes"].append(str(routing_directive.get("reason", "Routing layer halted execution.")))
                elif directive == "reduce_size":
                    fused["risk_budget"] = round(float(fused.get("risk_budget", 0.0) or 0.0) * 0.78, 4)
                    fused["position_multiplier"] = round(
                        float(np.clip(float(fused.get("confidence", 0.0) or 0.0) * float(fused["risk_budget"]), 0.10, 1.10)),
                        4,
                    )
                    fused["coordination"]["notes"].append(str(routing_directive.get("reason", "Routing layer reduced size.")))
                elif directive == "prefer_alternate":
                    fused["risk_budget"] = round(float(fused.get("risk_budget", 0.0) or 0.0) * 0.92, 4)
                    fused["position_multiplier"] = round(
                        float(np.clip(float(fused.get("confidence", 0.0) or 0.0) * float(fused["risk_budget"]), 0.10, 1.10)),
                        4,
                    )
                    fused["coordination"]["notes"].append(str(routing_directive.get("reason", "Alternate execution route is preferable.")))
            except Exception:
                execution_forecast = execution_forecast

        price = float(df["Close"].iloc[-1])
        atr_series = calculate_atr(df["High"], df["Low"], df["Close"], 14)
        atr = float(atr_series.iloc[-1]) if len(atr_series) else price * 0.01
        atr = atr if np.isfinite(atr) and atr > 0 else price * 0.01

        if fused["action"] == "BUY":
            stop_loss = price - 1.8 * atr
            take_profit = price + 2.4 * atr
        elif fused["action"] == "SELL":
            stop_loss = price + 1.8 * atr
            take_profit = price - 2.4 * atr
        else:
            stop_loss = price - 1.0 * atr
            take_profit = price + 1.0 * atr

        notional_risk = capital * 0.01 * fused["position_multiplier"]

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "ticker": ticker,
            "market": {
                "price": round(price, 4),
                "atr": round(float(atr), 4),
                "interval": interval,
                "period": period,
            },
            "decision": {
                **fused,
                "entry": round(price, 4),
                "stop_loss": round(float(stop_loss), 4),
                "take_profit": round(float(take_profit), 4),
                "notional_risk": round(float(notional_risk), 4),
            },
            "strategy_pack": strategy_pack,
            "data_quality": data_quality,
            "adaptive_weights": {
                "strategy": round(adaptive["weights"].strategy, 4),
                "ml_confirmation": round(adaptive["weights"].ml_confirmation, 4),
                "regime": round(adaptive["weights"].regime, 4),
                "quant": round(adaptive["weights"].quant, 4),
                "news": round(adaptive["weights"].news, 4),
                "risk_penalty": round(adaptive["weights"].risk_penalty, 4),
                "notes": adaptive["notes"],
                "live_component_reliability": adaptive.get("live_component_reliability", []),
                "memory_influence": adaptive.get("memory_influence", {}),
            },
            "memory_context": memory_context,
            "ml_confirmation": {
                **ml_confirmation,
                "features": ml_features,
                "model_meta": adaptive.get("ml_meta") or {},
            },
            "regime": regime_payload,
            "quant": quant_payload,
            "news": {
                "summary": news_summary,
                "top_headlines": news_items[:5],
                "runtime": news_runtime,
                "event_study": news_event_study,
            },
            "execution_quality": execution_quality,
            "execution_forecast": execution_forecast,
            "routing": routing_directive,
            "monte_carlo": mc_payload,
            "module_status": {
                "strategy_registry": {
                    "available": True,
                    "strategies": self.registry.list_ids(),
                    "signals_count": len(strategy_pack.get("signals", [])),
                },
                "ml_confirmation_model": {
                    "available": bool(ml_confirmation.get("available")),
                    "action": ml_confirmation.get("action"),
                    "reason": ml_confirmation.get("reason"),
                },
                "regime_engine": {
                    "available": True,
                    "regime": regime_payload.get("regime"),
                },
                "quant_engine": {
                    "available": not bool(quant_payload.get("error")),
                    "error": quant_payload.get("error"),
                },
                "news_engine": {
                    "available": bool(len(news_items) > 0),
                    "headlines_used": int(news_summary.get("headline_count", 0)),
                },
                "risk_engine": {
                    "available": not bool(mc_payload.get("error")),
                    "error": mc_payload.get("error"),
                },
                "data_quality": {
                    "available": True,
                    "status": data_quality.get("status"),
                    "score": data_quality.get("score"),
                },
                "execution_quality": {
                    "available": bool((execution_quality or {}).get("status") == "success"),
                    "quality_score": ((execution_quality or {}).get("summary") or {}).get("quality_score"),
                    "reject_rate": ((execution_quality or {}).get("summary") or {}).get("reject_rate"),
                },
            },
        }

    def get_runtime_status(self) -> Dict[str, Any]:
        ml_available = False
        ml_reason = "not_checked"
        try:
            from backend.services.fusion_model_service import fusion_model_service

            ml_available = bool(getattr(fusion_model_service, "latest_model_path").exists())
            ml_reason = "trained" if ml_available else "model_not_trained"
        except Exception as exc:
            ml_available = False
            ml_reason = f"unavailable: {exc}"

        news_status: Dict[str, Any] = {"available": False}
        try:
            from backend.services.news_ml_service import news_ml_service

            news_status = {
                "available": True,
                "runtime": news_ml_service.get_runtime_status(),
            }
        except Exception as exc:
            news_status = {"available": False, "error": str(exc)}

        event_study_status: Dict[str, Any] = {"available": False}
        try:
            from backend.services.news_event_study_service import news_event_study_service

            latest = news_event_study_service.get_latest(benchmark_ticker="^NSEI", interval="15m")
            event_study_status = {
                "available": latest.get("status") == "success",
                "latest": latest,
            }
        except Exception as exc:
            event_study_status = {"available": False, "error": str(exc)}

        live_signal_status: Dict[str, Any] = {"available": False}
        try:
            from backend.services.live_signal_tracker_service import live_signal_tracker_service

            live_signal_status = {
                "available": True,
                "summary": live_signal_tracker_service.get_summary(ticker="^NSEI"),
            }
        except Exception as exc:
            live_signal_status = {"available": False, "error": str(exc)}

        execution_quality_status: Dict[str, Any] = {"available": False}
        try:
            from backend.services.execution_quality_service import execution_quality_service

            execution_quality_status = {
                "available": True,
                "summary": execution_quality_service.get_summary(ticker="^NSEI"),
            }
        except Exception as exc:
            execution_quality_status = {"available": False, "error": str(exc)}

        memory_status: Dict[str, Any] = {"available": False}
        try:
            memory_status = {
                "available": True,
                "runtime": memory_service.get_runtime_status(),
            }
        except Exception as exc:
            memory_status = {"available": False, "error": str(exc)}

        return {
            "status": "success",
            "fusion_weights": {
                "strategy": self.weights.strategy,
                "ml_confirmation": self.weights.ml_confirmation,
                "regime": self.weights.regime,
                "quant": self.weights.quant,
                "news": self.weights.news,
                "risk_penalty": self.weights.risk_penalty,
            },
            "strategy_registry": {
                "count": len(self.registry.list_ids()),
                "strategies": self.registry.list_ids(),
            },
            "ml_confirmation_model": {
                "available": ml_available,
                "reason": ml_reason,
            },
            "news_engine": news_status,
            "news_event_study": event_study_status,
            "live_signal_tracker": live_signal_status,
            "execution_quality": execution_quality_status,
            "memory_engine": memory_status,
            "data_quality": {
                "service": "available",
            },
        }


fusion_service = DecisionFusionService()
