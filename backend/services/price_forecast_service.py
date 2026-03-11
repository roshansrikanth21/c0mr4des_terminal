"""
Price forecasting service using supervised ML on historical OHLCV data.
Train and predict next close price with time-series-safe splitting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime
import pickle
import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class PriceForecastService:
    def __init__(self):
        repo_root = Path(__file__).resolve().parents[2]
        self.model_dir = repo_root / "backend" / "models" / "price_forecast"
        self.model_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_ticker(ticker: str) -> str:
        safe = (ticker or "").strip().replace("^", "IDX_").replace(":", "_")
        safe = safe.replace("/", "_").replace("\\", "_")
        return "".join(ch if (ch.isalnum() or ch in {"_", "-", "."}) else "_" for ch in safe)

    @staticmethod
    def _next_timestamp(ts: pd.Timestamp, interval: str) -> pd.Timestamp:
        mapping = {
            "1m": pd.Timedelta(minutes=1),
            "2m": pd.Timedelta(minutes=2),
            "5m": pd.Timedelta(minutes=5),
            "15m": pd.Timedelta(minutes=15),
            "30m": pd.Timedelta(minutes=30),
            "60m": pd.Timedelta(minutes=60),
            "90m": pd.Timedelta(minutes=90),
            "1h": pd.Timedelta(hours=1),
            "1d": pd.Timedelta(days=1),
            "1wk": pd.Timedelta(days=7),
            "1mo": pd.Timedelta(days=30),
        }
        step = mapping.get(interval, pd.Timedelta(days=1))
        return ts + step

    def _model_path(self, ticker: str, interval: str) -> Path:
        return self.model_dir / f"{self._sanitize_ticker(ticker)}__{interval}.pkl"

    @staticmethod
    def _build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty or "Close" not in df.columns:
            return pd.DataFrame()

        close = pd.to_numeric(df["Close"], errors="coerce").astype(float)
        if "Volume" in df.columns:
            volume = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0).astype(float)
        else:
            volume = pd.Series(0.0, index=df.index)

        features = pd.DataFrame(index=df.index)
        features["ret_1"] = close.pct_change()

        for lag in (1, 2, 3, 5, 10):
            features[f"close_lag_{lag}"] = close.shift(lag)
            features[f"ret_lag_{lag}"] = features["ret_1"].shift(lag)

        features["sma_5"] = close.rolling(5).mean()
        features["sma_10"] = close.rolling(10).mean()
        features["sma_20"] = close.rolling(20).mean()
        features["volatility_10"] = features["ret_1"].rolling(10).std()
        features["volume_lag_1"] = volume.shift(1)
        features["volume_ma_10"] = volume.rolling(10).mean()

        features = features.replace([np.inf, -np.inf], np.nan).dropna()
        return features

    def train_and_save(self, ticker: str, interval: str, df: pd.DataFrame) -> Dict[str, Any]:
        features = self._build_feature_matrix(df)
        if features.empty:
            raise ValueError("Insufficient data to build forecasting features.")

        target = pd.to_numeric(df["Close"], errors="coerce").shift(-1)
        dataset = features.copy()
        dataset["target_next_close"] = target.reindex(features.index)
        dataset = dataset.dropna()

        if len(dataset) < 120:
            raise ValueError(f"Need at least 120 rows to train robustly, got {len(dataset)}.")

        split_idx = int(len(dataset) * 0.8)
        split_idx = min(max(split_idx, 80), len(dataset) - 1)

        X = dataset.drop(columns=["target_next_close"])
        y = dataset["target_next_close"]

        X_train = X.iloc[:split_idx]
        y_train = y.iloc[:split_idx]
        X_test = X.iloc[split_idx:]
        y_test = y.iloc[split_idx:]

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        model = RandomForestRegressor(
            n_estimators=300,
            random_state=42,
            n_jobs=-1,
            min_samples_leaf=2,
        )
        model.fit(X_train_scaled, y_train)

        preds = model.predict(X_test_scaled)
        mae = mean_absolute_error(y_test, preds)
        rmse = np.sqrt(mean_squared_error(y_test, preds))

        # Percentage error where actual != 0
        safe_actual = y_test.values
        nonzero = np.where(np.abs(safe_actual) > 1e-9, safe_actual, np.nan)
        mape = float(np.nanmean(np.abs((safe_actual - preds) / nonzero)) * 100)
        if np.isnan(mape):
            mape = 0.0

        # Directional accuracy: sign(next_close - current_close)
        current_close = dataset["close_lag_1"].iloc[split_idx:].values
        actual_dir = np.sign(y_test.values - current_close)
        pred_dir = np.sign(preds - current_close)
        directional_accuracy = float((actual_dir == pred_dir).mean() * 100) if len(actual_dir) else 0.0

        artifact = {
            "ticker": ticker,
            "interval": interval,
            "trained_at": datetime.utcnow().isoformat() + "Z",
            "feature_columns": list(X.columns),
            "model": model,
            "scaler": scaler,
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "metrics": {
                "mae": float(mae),
                "rmse": float(rmse),
                "mape_percent": float(mape),
                "directional_accuracy_percent": float(directional_accuracy),
            },
        }

        path = self._model_path(ticker, interval)
        with open(path, "wb") as f:
            pickle.dump(artifact, f)

        return {
            "status": "success",
            "ticker": ticker,
            "interval": interval,
            "model_path": str(path),
            "trained_at": artifact["trained_at"],
            "train_rows": artifact["train_rows"],
            "test_rows": artifact["test_rows"],
            "metrics": artifact["metrics"],
        }

    def _load_artifact(self, ticker: str, interval: str) -> Dict[str, Any]:
        path = self._model_path(ticker, interval)
        if not path.exists():
            raise FileNotFoundError(f"No saved model found for {ticker} [{interval}]")
        with open(path, "rb") as f:
            return pickle.load(f)

    def predict_next(self, ticker: str, interval: str, df: pd.DataFrame, horizon: int = 1) -> Dict[str, Any]:
        if horizon < 1 or horizon > 50:
            raise ValueError("horizon must be between 1 and 50.")

        artifact = self._load_artifact(ticker, interval)
        model = artifact["model"]
        scaler = artifact["scaler"]
        feature_columns: List[str] = artifact["feature_columns"]

        history = df.copy()
        if history.empty or "Close" not in history.columns:
            raise ValueError("Need non-empty OHLCV data with Close column for prediction.")

        if not isinstance(history.index, pd.DatetimeIndex):
            history.index = pd.to_datetime(history.index, errors="coerce")
        history = history.sort_index()
        if history.index.tz is None:
            history.index = history.index.tz_localize("UTC")
        else:
            history.index = history.index.tz_convert("UTC")

        predictions: List[Dict[str, Any]] = []

        for _ in range(horizon):
            features = self._build_feature_matrix(history)
            if features.empty:
                raise ValueError("Not enough historical rows to construct prediction features.")

            latest = features.iloc[-1]
            latest = latest.reindex(feature_columns)
            latest_df = pd.DataFrame([latest.values], columns=feature_columns)
            X_latest = scaler.transform(latest_df)
            pred_close = float(model.predict(X_latest)[0])

            next_ts = self._next_timestamp(history.index[-1], interval)
            predictions.append({"timestamp": next_ts.isoformat(), "predicted_close": pred_close})

            # Append synthetic next candle for recursive multi-step prediction.
            last_volume = float(history["Volume"].iloc[-1]) if "Volume" in history.columns else 0.0
            new_row = pd.DataFrame(
                {
                    "Open": [pred_close],
                    "High": [pred_close],
                    "Low": [pred_close],
                    "Close": [pred_close],
                    "Volume": [last_volume],
                },
                index=[next_ts],
            )
            history = pd.concat([history, new_row])

        return {
            "status": "success",
            "ticker": ticker,
            "interval": interval,
            "horizon": int(horizon),
            "model_trained_at": artifact.get("trained_at"),
            "predictions": predictions,
        }


price_forecast_service = PriceForecastService()
