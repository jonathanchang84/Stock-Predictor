"""Automated auditing: score matured predictions against actual closes."""

import logging
from datetime import date, datetime, timezone
from typing import Any

from ..db.connection import fetch_all, fetch_one, execute

logger = logging.getLogger(__name__)


def get_unaudited_predictions(ticker: str = None, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch predictions whose target date has passed and not yet audited."""
    target_date_sql = """
        CASE p.horizon
            WHEN '1d' THEN date(p.prediction_date, '+1 day')
            WHEN '7d' THEN date(p.prediction_date, '+7 days')
            WHEN '1m' THEN date(p.prediction_date, '+30 days')
            WHEN '6m' THEN date(p.prediction_date, '+180 days')
            WHEN '1y' THEN date(p.prediction_date, '+365 days')
            WHEN '3y' THEN date(p.prediction_date, '+1095 days')
            WHEN '5y' THEN date(p.prediction_date, '+1825 days')
            WHEN '10y' THEN date(p.prediction_date, '+3650 days')
            WHEN '20y' THEN date(p.prediction_date, '+7300 days')
        END
    """
    ticker_filter = "AND p.ticker = ?" if ticker else ""
    params = [ticker] if ticker else []
    params.append(max(limit, 1))
    return fetch_all(
        f"""SELECT matured.* FROM (
                SELECT p.*, {target_date_sql} AS target_date
                FROM predictions p
                LEFT JOIN error_audits a ON p.id = a.prediction_id
                WHERE a.id IS NULL {ticker_filter}
            ) matured
            WHERE matured.target_date <= date('now')
            ORDER BY matured.prediction_date DESC
            LIMIT ?""",
        params,
    )


def fetch_actual_close(ticker: str, target_date: str) -> tuple[float, str] | None:
    """Get the first available closing price on or shortly after the target date."""
    row = fetch_one(
        "SELECT close, date FROM price_history "
        "WHERE ticker = ? AND date >= ? AND date <= date(?, '+7 days') "
        "ORDER BY date LIMIT 1",
        (ticker, target_date, target_date),
    )
    if row:
        return float(row["close"]), row["date"]
    return None


def audit_predictions(ticker: str = None) -> dict[str, int | float]:
    """Audit all un-audited predictions and save results. Returns summary stats."""
    predictions = get_unaudited_predictions(ticker)
    if not predictions:
        return {"audited": 0, "skipped": 0, "message": "No un-audited predictions found."}

    summary = {"audited": 0, "skipped": 0, "total": len(predictions)}

    for p in predictions:
        p = dict(p)
        actual_result = fetch_actual_close(p["ticker"], p["target_date"])
        if actual_result is None:
            logger.warning("No actual close for %s on %s; skipping audit",
                           p["ticker"], p["target_date"])
            summary["skipped"] += 1
            continue
        actual, actual_date = actual_result

        pred_price = p["predicted_price"]
        abs_err = abs(actual - pred_price)
        pct_err = (abs_err / actual * 100.0) if actual != 0 else 0.0

        prediction_date = date.fromisoformat(p["prediction_date"][:10]).isoformat()
        prev_row = fetch_one(
            "SELECT close FROM price_history WHERE ticker = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            (p["ticker"], prediction_date),
        )
        baseline = float(prev_row["close"]) if prev_row else pred_price
        predicted_direction = 1 if pred_price >= baseline else 0
        actual_direction = 1 if prev_row and actual >= float(prev_row["close"]) else 0

        directional_correct = 1 if predicted_direction == actual_direction else 0

        audit = {
            "prediction_id": p["id"],
            "audit_date": actual_date,
            "actual_close": actual,
            "absolute_error": round(abs_err, 4),
            "percentage_error": round(pct_err, 4),
            "directional_correct": directional_correct,
            "notes": f"Predicted {pred_price}, Actual {actual}, {p.get('horizon', 'N/A')} horizon",
            "audited_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
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
