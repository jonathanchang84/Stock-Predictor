"""Forecast service: prediction ledger + calibration injection."""

import logging
from datetime import datetime, timezone
from typing import Any

from ..db.connection import fetch_all, fetch_one, execute
from .prediction_engine import HORIZONS, generate_forecast

logger = logging.getLogger(__name__)


def _load_calibration_context(ticker: str, sector: str) -> dict[str, Any]:
    """Query recent prediction errors for this ticker/sector and build bias context."""
    # Collect error_audit records for this ticker
    audits = fetch_all(
        "SELECT ticker, horizon, percentage_error, directional_correct FROM error_audits "
        "JOIN predictions USING (prediction_id) WHERE predictions.ticker = ? AND predictions.target_date <= ? "
        "ORDER BY predictions.target_date DESC LIMIT 30",
        (ticker, datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")),
    )

    context = {"bias_correction": 0.0, "temper_bullish": False}
    if not audits:
        return context

    # Compute average percentage error per horizon
    horizon_errors = {}
    for a in audits:
        h = a["horizon"]
        pct = a["percentage_error"] or 0.0
        horizon_errors[h] = horizon_errors.get(h, []) + [pct]

    if horizon_errors:
        avg_errors = {h: sum(v) / len(v) for h, v in horizon_errors.items()}
        # Find worst horizon bias
        worst_h = max(avg_errors, key=avg_errors.get)
        bias = avg_errors[worst_h]
        context["bias_correction"] = round(bias, 4)

    # Directional bias: if we're consistently wrong directionally
    correct = sum(1 for a in audits if a["directional_correct"] == 1)
    total = len(audits)
    if total >= 5 and correct / total < 0.45:
        context["temper_bullish"] = True  # over-optimistic; reduce confidence

    return context


def save_prediction(forecast: dict[str, Any]) -> int:
    """Write the prediction ledger for all horizons."""
    if not forecast.get("predictions"):
        return 0

    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    inserted = 0
    for h, pred in forecast["predictions"].items():
        params = (
            forecast["ticker"],
            h,
            pred["prediction_date"],
            pred["predicted_price"],
            pred.get("confidence_interval", 0),
            pred.get("confidence_range", 0),
            pred.get("low", 0),
            pred.get("high", 0),
            pred.get("sentiment_score", 0.0),
            pred.get("key_assumptions", ""),
            now,
        )
        query = """
            INSERT OR REPLACE INTO predictions
            (ticker, horizon, prediction_date, predicted_price, confidence_interval,
             confidence_range, low, high, sentiment_score, key_assumptions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        execute(query, params, fetch=False)
        inserted += 1
    return inserted


def save_error_audit(audit: dict[str, Any]) -> int:
    """Append one audit record to error_audits."""
    params = (
        audit["prediction_id"],
        audit["audit_date"],
        audit["actual_close"],
        audit["absolute_error"],
        audit["percentage_error"],
        1 if audit["directional_correct"] else 0,
        audit.get("notes", ""),
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    query = """
        INSERT INTO error_audits
        (prediction_id, audit_date, actual_close, absolute_error, percentage_error,
         directional_correct, notes, audited_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    return execute(query, params, fetch=False)


def upsert_forecast_accuracy(ticker: str, horizon: str, mape: float, hit_rate: float,
                             mean_abs_error: float, sample_size: int) -> int:
    """Upsert into forecast_accuracy table."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    params = (ticker, horizon, mape, hit_rate, mean_abs_error, sample_size, now)
    query = """
        INSERT OR REPLACE INTO forecast_accuracy
        (ticker, horizon, rolling_30d_mape, directional_hit_rate, mean_abs_error,
         sample_size, last_reported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    return execute(query, params, fetch=False)
