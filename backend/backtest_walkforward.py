from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.market_data import calculate_atr, calculate_macd, calculate_rsi, calculate_sma
from backend.services.market_data_service import get_sync_market_data


@dataclass
class WalkForwardConfig:
    ticker: str = "^NSEI"
    interval: str = "15m"
    period: str = "1y"
    horizon: int = 5
    train_window: int = 320
    test_window: int = 80
    step_size: int = 40
    slippage_bps: float = 3.0
    transaction_cost_bps: float = 2.0


class WalkForwardBacktester:
    def __init__(self, cfg: WalkForwardConfig):
        self.cfg = cfg

    @staticmethod
    def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        local = df.copy()
        if isinstance(local.columns, pd.MultiIndex):
            local.columns = local.columns.get_level_values(0)
        local.columns = [str(c).capitalize() for c in local.columns]
        req = ["Open", "High", "Low", "Close", "Volume"]
        for col in req:
            if col not in local.columns:
                return pd.DataFrame()
            local[col] = pd.to_numeric(local[col], errors="coerce")
        local = local.dropna(subset=["Open", "High", "Low", "Close"])
        local["Volume"] = local["Volume"].fillna(0.0)
        return local.sort_index()

    def _build_feature_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        f = pd.DataFrame(index=df.index)
        f["ret_1"] = close.pct_change(1)
        f["ret_3"] = close.pct_change(3)
        f["ret_5"] = close.pct_change(5)
        f["volatility_20"] = close.pct_change().rolling(20).std()

        sma_20 = calculate_sma(close, 20)
        sma_50 = calculate_sma(close, 50)
        rsi_14 = calculate_rsi(close, 14)
        atr_14 = calculate_atr(high, low, close, 14)
        macd, macd_signal = calculate_macd(close)

        f["sma20_dist"] = (close - sma_20) / sma_20.replace(0, np.nan)
        f["sma50_dist"] = (close - sma_50) / sma_50.replace(0, np.nan)
        f["trend_gap"] = (sma_20 - sma_50) / sma_50.replace(0, np.nan)
        f["rsi_14"] = rsi_14
        f["atr_norm"] = atr_14 / close.replace(0, np.nan)
        f["macd"] = macd
        f["macd_signal"] = macd_signal
        f["macd_hist"] = macd - macd_signal
        f["volume_z20"] = (volume - volume.rolling(20).mean()) / volume.rolling(20).std().replace(0, np.nan)

        f["future_return"] = close.shift(-self.cfg.horizon) / close - 1.0
        f["target"] = (f["future_return"] > 0).astype(int)

        f = f.replace([np.inf, -np.inf], np.nan).dropna()
        return f

    @staticmethod
    def _max_drawdown(equity_curve: pd.Series) -> float:
        if equity_curve.empty:
            return 0.0
        roll_max = equity_curve.cummax()
        drawdown = (equity_curve / roll_max) - 1.0
        return float(drawdown.min())

    def run(self) -> Dict[str, Any]:
        df = get_sync_market_data(self.cfg.ticker, period=self.cfg.period, interval=self.cfg.interval)
        df = self._normalize_df(df)
        if df.empty:
            return {"status": "error", "message": f"No data for {self.cfg.ticker}"}

        feature_df = self._build_feature_frame(df)
        if len(feature_df) < (self.cfg.train_window + self.cfg.test_window + 20):
            return {
                "status": "error",
                "message": "Insufficient rows for walk-forward backtest",
                "rows": int(len(feature_df)),
            }

        feature_cols = [c for c in feature_df.columns if c not in {"future_return", "target"}]
        model_pipe = Pipeline(
            steps=[
                (
                    "preprocess",
                    ColumnTransformer(
                        transformers=[
                            (
                                "num",
                                Pipeline(
                                    steps=[
                                        ("imputer", SimpleImputer(strategy="median")),
                                        ("scaler", StandardScaler()),
                                    ]
                                ),
                                feature_cols,
                            )
                        ],
                        remainder="drop",
                    ),
                ),
                (
                    "model",
                    GradientBoostingClassifier(
                        n_estimators=160,
                        learning_rate=0.05,
                        max_depth=3,
                        random_state=42,
                    ),
                ),
            ]
        )

        fold_reports: List[Dict[str, Any]] = []
        all_returns = []
        equity = [1.0]
        total_trades = 0

        start = 0
        while start + self.cfg.train_window + self.cfg.test_window <= len(feature_df):
            train_slice = feature_df.iloc[start : start + self.cfg.train_window]
            test_slice = feature_df.iloc[
                start + self.cfg.train_window : start + self.cfg.train_window + self.cfg.test_window
            ]

            X_train = train_slice[feature_cols]
            y_train = train_slice["target"].astype(int)
            X_test = test_slice[feature_cols]
            y_test = test_slice["target"].astype(int)

            if y_train.nunique() < 2:
                start += self.cfg.step_size
                continue

            model_pipe.fit(X_train, y_train)
            prob_up = model_pipe.predict_proba(X_test)[:, 1]

            position = np.where(prob_up > 0.55, 1.0, np.where(prob_up < 0.45, -1.0, 0.0))
            next_ret = test_slice["future_return"].values

            changes = np.abs(np.diff(np.concatenate([[0.0], position])))
            trade_cost = changes * ((self.cfg.slippage_bps + self.cfg.transaction_cost_bps) / 10000.0)
            pnl = position * next_ret - trade_cost

            total_trades += int(np.sum(changes > 0))
            pnl_series = pd.Series(pnl, index=test_slice.index)
            all_returns.append(pnl_series)

            for r in pnl:
                equity.append(equity[-1] * (1.0 + float(r)))

            hit_rate = float(np.mean((position * next_ret) > 0)) if len(position) else 0.0
            fold_reports.append(
                {
                    "train_start": str(train_slice.index.min()),
                    "train_end": str(train_slice.index.max()),
                    "test_start": str(test_slice.index.min()),
                    "test_end": str(test_slice.index.max()),
                    "samples": int(len(test_slice)),
                    "hit_rate": round(hit_rate, 4),
                    "avg_prob_up": round(float(np.mean(prob_up)), 4),
                    "pnl_sum": round(float(np.sum(pnl)), 6),
                }
            )

            start += self.cfg.step_size

        if not all_returns:
            return {"status": "error", "message": "Walk-forward produced no evaluable folds"}

        ret_series = pd.concat(all_returns)
        # Handle overlaps if step_size < test_window
        ret_series = ret_series[~ret_series.index.duplicated(keep='first')]
        equity_curve = pd.Series(equity)

        daily_returns = ret_series.groupby(ret_series.index.date).sum()
        mean_ret = float(daily_returns.mean())
        std_ret = float(daily_returns.std()) if float(daily_returns.std()) > 0 else 0.0
        sharpe = float((mean_ret / std_ret) * np.sqrt(252)) if std_ret > 0 else 0.0

        total_return = float(equity_curve.iloc[-1] - 1.0)
        max_dd = self._max_drawdown(equity_curve)
        win_rate = float((ret_series > 0).mean())

        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "config": {
                "ticker": self.cfg.ticker,
                "interval": self.cfg.interval,
                "period": self.cfg.period,
                "horizon": self.cfg.horizon,
                "train_window": self.cfg.train_window,
                "test_window": self.cfg.test_window,
                "step_size": self.cfg.step_size,
                "slippage_bps": self.cfg.slippage_bps,
                "transaction_cost_bps": self.cfg.transaction_cost_bps,
            },
            "summary": {
                "folds": len(fold_reports),
                "total_samples": int(len(ret_series)),
                "total_trades": int(total_trades),
                "total_return": round(total_return, 6),
                "win_rate": round(win_rate, 6),
                "sharpe": round(sharpe, 6),
                "max_drawdown": round(max_dd, 6),
                "ending_equity": round(float(equity_curve.iloc[-1]), 6),
            },
            "folds": fold_reports,
        }
