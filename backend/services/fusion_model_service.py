from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, brier_score_loss, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class FusionModelService:
    def __init__(self):
        root = Path(__file__).resolve().parents[2]
        self.model_dir = root / "backend" / "models" / "fusion"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.latest_model_path = self.model_dir / "fusion_classifier.joblib"
        self.latest_meta_path = self.model_dir / "fusion_classifier.meta.json"

    @staticmethod
    def _load_dataset(path: str) -> pd.DataFrame:
        df = pd.read_csv(path)
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
            df = df.dropna(subset=["datetime"]).set_index("datetime")
        return df

    @staticmethod
    def _select_feature_columns(df: pd.DataFrame) -> List[str]:
        excluded = {"target_return", "target_direction", "target_drawdown"}
        cols = []
        for col in df.columns:
            if col in excluded:
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                cols.append(col)
        return cols

    def train_from_dataset(self, dataset_path: str, target: str = "target_direction") -> Dict[str, Any]:
        df = self._load_dataset(dataset_path)
        if df.empty or target not in df.columns:
            return {
                "status": "error",
                "message": f"Invalid dataset or missing target column '{target}'",
            }

        feature_cols = self._select_feature_columns(df)
        if len(feature_cols) < 4:
            return {"status": "error", "message": "Not enough numeric features for training"}

        model_df = df[feature_cols + [target]].dropna().copy()
        if model_df.empty or model_df[target].nunique() < 2:
            return {"status": "error", "message": "Target labels are insufficient or single-class"}

        split_idx = int(len(model_df) * 0.8)
        split_idx = max(split_idx, 30)
        train_df = model_df.iloc[:split_idx]
        test_df = model_df.iloc[split_idx:]
        if test_df.empty:
            test_df = model_df.iloc[-max(10, int(len(model_df) * 0.2)) :]

        X_train = train_df[feature_cols]
        y_train = train_df[target].astype(int)
        X_test = test_df[feature_cols]
        y_test = test_df[target].astype(int)

        numeric_transform = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]
        )
        preprocessor = ColumnTransformer(
            transformers=[("num", numeric_transform, feature_cols)],
            remainder="drop",
        )

        base_model = GradientBoostingClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=3,
            random_state=42,
        )

        pipe = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                ("classifier", base_model),
            ]
        )

        calibrated = CalibratedClassifierCV(pipe, method="sigmoid", cv=3)
        calibrated.fit(X_train, y_train)

        pred = calibrated.predict(X_test)
        pred_prob = calibrated.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy": float(accuracy_score(y_test, pred)),
            "precision": float(precision_score(y_test, pred, zero_division=0)),
            "recall": float(recall_score(y_test, pred, zero_division=0)),
            "brier": float(brier_score_loss(y_test, pred_prob)),
        }

        joblib.dump({"model": calibrated, "feature_columns": feature_cols}, self.latest_model_path)

        meta = {
            "trained_at": datetime.utcnow().isoformat() + "Z",
            "dataset_path": dataset_path,
            "target": target,
            "rows": int(len(model_df)),
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "feature_columns": feature_cols,
            "metrics": metrics,
        }
        self.latest_meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return {
            "status": "success",
            "model_path": str(self.latest_model_path),
            "meta_path": str(self.latest_meta_path),
            "metrics": metrics,
            "feature_count": len(feature_cols),
        }

    def _load_model_bundle(self) -> Dict[str, Any]:
        if not self.latest_model_path.exists():
            raise FileNotFoundError("Fusion model has not been trained yet")
        return joblib.load(self.latest_model_path)

    def get_latest_meta(self) -> Dict[str, Any]:
        if not self.latest_meta_path.exists():
            return {
                "status": "error",
                "message": "Fusion model metadata not found",
            }
        try:
            return {
                "status": "success",
                "meta": json.loads(self.latest_meta_path.read_text(encoding="utf-8")),
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to load fusion model metadata: {exc}",
            }

    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        bundle = self._load_model_bundle()
        model = bundle["model"]
        feature_cols = bundle["feature_columns"]

        row = {col: float(features.get(col, np.nan)) for col in feature_cols}
        X = pd.DataFrame([row], columns=feature_cols)

        proba = float(model.predict_proba(X)[:, 1][0])
        pred = int(proba >= 0.5)

        return {
            "status": "success",
            "prediction": pred,
            "probability_up": round(proba, 6),
            "probability_down": round(1.0 - proba, 6),
        }

    def score_dataset(self, dataset_path: str) -> Dict[str, Any]:
        bundle = self._load_model_bundle()
        model = bundle["model"]
        feature_cols = bundle["feature_columns"]

        df = self._load_dataset(dataset_path)
        if df.empty or "target_direction" not in df.columns:
            return {"status": "error", "message": "Dataset missing target_direction"}

        eval_df = df[feature_cols + ["target_direction"]].dropna()
        if eval_df.empty:
            return {"status": "error", "message": "No valid rows to score"}

        X = eval_df[feature_cols]
        y = eval_df["target_direction"].astype(int)

        pred = model.predict(X)
        pred_prob = model.predict_proba(X)[:, 1]

        return {
            "status": "success",
            "rows": int(len(eval_df)),
            "metrics": {
                "accuracy": float(accuracy_score(y, pred)),
                "precision": float(precision_score(y, pred, zero_division=0)),
                "recall": float(recall_score(y, pred, zero_division=0)),
                "brier": float(brier_score_loss(y, pred_prob)),
            },
        }


fusion_model_service = FusionModelService()
