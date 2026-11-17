"""REST route handlers for forecasts, daily runner, error analytics, and assets."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from ..core import error_auditor, forecast_service
from ..core.prediction_engine import generate_forecast
from ..db.connection import fetch_all, execute
from ..services import market_data, news_fetcher

router = APIRouter(prefix="/api", tags=["core"])
logger = logging.getLogger(__name__)


# --- Asset management -------------------------------------------------------------------

@router.get("/assets")
def list_assets():
    rows = fetch_all("SELECT id, ticker, asset_type, name, purchase_price, quantity, date_added, notes, updated_at FROM assets ORDER BY ticker")
    return [dict(r) for r in rows]


@router.post("/assets")
def add_asset(asset: dict[str, Any]):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        rid = execute(
            """INSERT INTO assets (ticker, asset_type, name, purchase_price, quantity, date_added, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset["ticker"].upper(), asset.get("asset_type", "stock"), asset.get("name", ""),
             float(asset.get("purchase_price", 0)), float(asset.get("quantity", 0)),
             asset.get("date_added", now), asset.get("notes", ""), now, now),
            fetch=False,
        )
        return {"id": rid, "ticker": asset["ticker"].upper(), "message": "Asset added"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/assets/{ticker}/price-history")
def get_price_history(ticker: str, days: int = 365):
    rows = fetch_all(
        "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT ?",
        (ticker.upper(), days * 2),
    )
    return [dict(r) for r in rows]


@router.get("/assets/{ticker}/catalysts")
def get_catalysts(ticker: str):
    rows = fetch_all("SELECT id, event_date, event_type, title, summary, source, confidence FROM catalyst_events WHERE ticker = ? ORDER BY event_date DESC", (ticker.upper(),))
    return [dict(r) for r in rows]


@router.post("/forecast")
def generate_forecast(payload: dict[str, Any]):
    """Generate forecasts for a ticker. Expects: ticker, price_history (optional), news_context (optional)."""
    ticker = payload.get("ticker", "").upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")

    rows = fetch_all(
        "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 1000",
        (ticker,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price history for {ticker}")

    import pandas as pd
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[["open", "high", "low", "close", "volume"]]

    news_query = payload.get("news_query", ticker)
    news_results = payload.get("news_context", [])
    if isinstance(news_results, list) and news_results:
        news_context = news_results
    else:
        news_context = [{"title": f"Relevant news for {news_query}", "summary": ""}]

    calibration = forecast_service._load_calibration_context(ticker, "tech" if "tech" in news_query.lower() else "general")

    result = generate_forecast(ticker, df, news_context, calibration, datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
    forecast_service.save_prediction(result)

    return result


@router.post("/run-daily-forecast")
def run_daily_forecast():
    """Run the full daily pipeline: audit matured predictions + generate new forecasts."""
    from ..core import error_auditor, forecast_service
    from collections import defaultdict

    audit_summary = error_auditor.audit_predictions()
    logger.info("Daily audit: %s", audit_summary)

    assets = fetch_all("SELECT id, ticker, asset_type, name, notes FROM assets")
    results = []
    for asset in assets:
        ticker = asset["ticker"]
        try:
            rows = fetch_all(
                "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date DESC LIMIT 2000",
                (ticker,),
            )
            if not rows:
                continue
            import pandas as pd
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            df = df[["open", "high", "low", "close", "volume"]]

            news = [{"title": f"News for {ticker}", "summary": ""}]
            cal = forecast_service._load_calibration_context(ticker, "general")

            from ..core.prediction_engine import generate_forecast
            fc = generate_forecast(ticker, df, news, cal, datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
            forecast_service.save_prediction(fc)
            results.append({"ticker": ticker, "forecasts_generated": 9})
        except Exception as e:
            logger.warning("Forecast failed for %s: %s", ticker, e)
            results.append({"ticker": ticker, "error": str(e)})

    audits = fetch_all("SELECT ticker, horizon, percentage_error, directional_correct FROM error_audits JOIN predictions USING (prediction_id)")
    agg = defaultdict(lambda: {"errors": [], "correct": 0, "total": 0})
    for a in audits:
        key = (a["ticker"], a["horizon"])
        agg[key]["errors"].append(a["percentage_error"] or 0)
        agg[key]["total"] += 1
        if a["directional_correct"] == 1:
            agg[key]["correct"] += 1
    for (ticker, horizon), vals in agg.items():
        mape = sum(vals["errors"]) / len(vals["errors"]) if vals["errors"] else 0
        hit_rate = vals["correct"] / vals["total"] if vals["total"] else 0
        forecast_service.upsert_forecast_accuracy(ticker, horizon, mape, hit_rate, sum(vals["errors"])/len(vals["errors"]) if vals["errors"] else 0, vals["total"])

    return {"status": "ok", "audit_summary": audit_summary, "forecasts_generated": len(results), "results": results}


@router.get("/errors/audits/{ticker}")
def get_error_audits(ticker: str):
    from ..db.connection import fetch_all
    rows = fetch_all(
        "SELECT a.*, p.prediction_date, p.horizon, p.predicted_price FROM error_audits a "
        "JOIN predictions p ON a.prediction_id = p.id "
        "WHERE p.ticker = ? ORDER BY a.audit_date DESC LIMIT 100",
        (ticker,),
    )
    return [dict(r) for r in rows]


@router.get("/errors/audit-summary/{ticker}")
def get_error_summary(ticker: str):
    from ..db.connection import fetch_all
    rows = fetch_all(
        "SELECT p.horizon, AVG(a.percentage_error) as avg_pct, "
        "AVG(a.absolute_error) as avg_abs, "
        "SUM(CASE WHEN a.directional_correct = 1 THEN 1 ELSE 0 END) as correct, "
        "COUNT(*) as total, "
        "SUM(CASE WHEN a.directional_correct = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as hit_rate "
        "FROM error_audits a JOIN predictions p ON a.prediction_id = p.id "
        "WHERE p.ticker = ? AND a.audit_date >= date('now', '-30 days') "
        "GROUP BY p.horizon ORDER BY p.horizon",
        (ticker,),
    )
    return [dict(r) for r in rows]
