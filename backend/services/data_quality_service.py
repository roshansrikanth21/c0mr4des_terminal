from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd

from backend.services.historical_data_service import historical_data_service


@dataclass
class DataQualityAssessment:
    score: float
    status: str
    freshness_seconds: Optional[float]
    expected_interval_seconds: Optional[float]
    issues: list[str]
    report: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "score": round(float(self.score), 4),
            "status": self.status,
            "freshness_seconds": None if self.freshness_seconds is None else round(float(self.freshness_seconds), 2),
            "expected_interval_seconds": (
                None if self.expected_interval_seconds is None else round(float(self.expected_interval_seconds), 2)
            ),
            "issues": list(self.issues),
            "report": self.report,
        }


class DataQualityService:
    """
    Produces a defensive quality score for market data so trading decisions can
    explicitly downgrade stale, gappy, or malformed inputs.
    """

    @staticmethod
    def _expected_seconds(interval: str) -> Optional[float]:
        delta = historical_data_service._expected_delta(interval)
        return None if delta is None else float(delta.total_seconds())

    @staticmethod
    def _freshness_seconds(index: pd.Index) -> Optional[float]:
        if not isinstance(index, pd.DatetimeIndex) or len(index) == 0:
            return None
        last_ts = index.max()
        if pd.isna(last_ts):
            return None
        if getattr(last_ts, "tzinfo", None) is None:
            last_ts = last_ts.tz_localize("UTC")
        else:
            last_ts = last_ts.tz_convert("UTC")
        now = datetime.now(timezone.utc)
        return max((now - last_ts.to_pydatetime()).total_seconds(), 0.0)

    def assess_dataframe(self, df: pd.DataFrame, interval: str) -> Dict[str, Any]:
        report = historical_data_service.quality_report(df, interval)
        issues: list[str] = []

        if report.get("is_empty"):
            return DataQualityAssessment(
                score=0.0,
                status="critical",
                freshness_seconds=None,
                expected_interval_seconds=self._expected_seconds(interval),
                issues=["No market data available."],
                report=report,
            ).as_dict()

        score = 1.0
        row_count = int(report.get("row_count", 0) or 0)
        gap_count = int(report.get("large_gap_count", 0) or 0)
        missing_intervals = int(report.get("missing_intervals_est", 0) or 0)
        invalid_rows = int(report.get("invalid_price_rows", 0) or 0)
        inverted_rows = int(report.get("high_low_inversion_rows", 0) or 0)
        duplicate_rows = int(report.get("duplicate_index_rows", 0) or 0)

        expected_seconds = self._expected_seconds(interval)
        freshness_seconds = self._freshness_seconds(df.index)

        if row_count < 120:
            score -= 0.12
            issues.append("Limited sample size reduces confidence.")
        elif row_count < 300:
            score -= 0.05

        if missing_intervals > 0:
            gap_ratio = missing_intervals / max(row_count, 1)
            score -= min(0.30, gap_ratio * 4.0)
            issues.append(f"Estimated missing candles: {missing_intervals}.")

        if gap_count > 0 and gap_count / max(row_count, 1) > 0.01:
            score -= 0.08
            issues.append("Detected repeated time gaps in the series.")

        malformed_rows = invalid_rows + inverted_rows + duplicate_rows
        if malformed_rows > 0:
            score -= min(0.20, malformed_rows / max(row_count, 1) * 8.0)
            issues.append("Malformed OHLC rows were detected in the dataset.")

        if expected_seconds and freshness_seconds is not None:
            freshness_multiple = freshness_seconds / max(expected_seconds, 1.0)
            if freshness_multiple > 24:
                score -= 0.28
                issues.append("Market data is critically stale for the selected interval.")
            elif freshness_multiple > 8:
                score -= 0.14
                issues.append("Market data is stale relative to the selected interval.")
            elif freshness_multiple > 4:
                score -= 0.06

        score = max(0.0, min(score, 1.0))
        if score >= 0.85:
            status = "excellent"
        elif score >= 0.70:
            status = "good"
        elif score >= 0.50:
            status = "warning"
        elif score >= 0.30:
            status = "degraded"
        else:
            status = "critical"

        if not issues:
            issues.append("No material data quality issues detected.")

        return DataQualityAssessment(
            score=score,
            status=status,
            freshness_seconds=freshness_seconds,
            expected_interval_seconds=expected_seconds,
            issues=issues,
            report=report,
        ).as_dict()


data_quality_service = DataQualityService()
