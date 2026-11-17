"""Automated auditing: score matured predictions against actual closes."""

import logging
from datetime import datetime, timezone
from typing import Any

from ..db.connection import fetch_all, fetch_one, execute

logger = logging.getLogger(__name__)


def get_unaudited_predictions(ticker: str = None, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch predictions whose target date has passed and not yet audited."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if ticker:
        rows = fetch_all(
            "SELECT p.*, a.actual_close FROM predictions p "
            "LEFT JOIN error_audits a ON p.id = a.prediction_id "
            "WHERE p.prediction_date <= ? AND p.target_date <= ? "
            "AND a.id IS NULL",
            (now, now),
        )
    else:
        rows = fetch_all(
            "SELECT p.*, a.actual_close FROM predictions p "
            "LEFT JOIN error_audits a ON p.id = a.prediction_id "
            "WHERE p.prediction_date <= ? AND p.target_date <= ? "
            "AND a.id IS NULL "
            "ORDER BY p.prediction_date DESC "
            "LIMIT ?",
            (now, now, limit),
        )
    return rows


def fetch_actual_close(ticker: str, target_date: str) -> float | None:
    """Get the closing price for a ticker on a specific date."""
    row = fetch_one(
        "SELECT close FROM price_history WHERE ticker = ? AND date = ?",
        (ticker, target_date),
    )
    if row:
        return float(row["close"])
    return None


def audit_predictions(ticker: str = None) -> dict[str, int | float]:
    """Audit all un-audited predictions and save results. Returns summary stats."""
    predictions = get_unaudited_predictions(ticker)
    if not predictions:
        return {"audited": 0, "skipped": 0, "message": "No un-audited predictions found."}

    summary = {"audited": 0, "skipped": 0, "total": len(predictions)}

    for p in predictions:
        actual = fetch_actual_close(p["ticker"], p["target_date"])
        if actual is None:
            logger.warning("No actual close for %s on %s; skipping audit",
                           p["ticker"], p["target_date"])
            summary["skipped"] += 1
            continue

        pred_price = p["predicted_price"]
        abs_err = abs(actual - pred_price)
        pct_err = (abs_err / actual * 100.0) if actual != 0 else 0.0

        # Determine directional accuracy by comparing predicted vs actual direction
        predicted_direction = 1 if pred_price >= p["predicted_price"] else 0
        # Prior close for actual direction
        prev_row = fetch_one(
            "SELECT close FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (p["ticker"],),
        )
        actual_direction = 1 if prev_row and actual >= float(prev_row["close"]) else 0

        directional_correct = 1 if predicted_direction == actual_direction else 0

        audit = {
            "prediction_id": p["id"],
            "audit_date": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "actual_close": actual,
            "absolute_error": round(abs_err, 4),
            "percentage_error": round(pct_err, 4),
            "directional_correct": directional_correct,
            "notes": f"Predicted {pred_price}, Actual {actual}, {p.get('horizon', 'N/A')} horizon",
        }
        execute(
            """INSERT INTO error_audits
            (prediction_id, audit_date, actual_close, absolute_error, percentage_error,
             directional_correct, notes, audited_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (audit["prediction_id"], audit["audit_date"], audit["actual_close"],
             audit["absolute_error"], audit["percentage_error"], directional_correct,
             audit["notes"], audit["audited_at"]),
            fetch=False,
        )
        summary["audited"] += 1

    return summary
