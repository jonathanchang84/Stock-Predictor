"""REST route handlers for forecasts, daily runner, error analytics, and assets."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from ..core import error_auditor, forecast_service
from ..core.prediction_engine import generate_forecast as build_forecast
from ..db.connection import execute, executemany, fetch_all, fetch_one, get_connection
from ..services import market_data, news_fetcher

router = APIRouter(prefix="/api", tags=["core"])
logger = logging.getLogger(__name__)

SP500_ASSETS = [
    {
        "ticker": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "asset_type": "etf",
        "exchange": "NYSE Arca",
    },
    {
        "ticker": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "asset_type": "etf",
        "exchange": "NYSE Arca",
    },
    {
        "ticker": "IVV",
        "name": "iShares Core S&P 500 ETF",
        "asset_type": "etf",
        "exchange": "NYSE Arca",
    },
    {
        "ticker": "SPYM",
        "name": "State Street SPDR Portfolio S&P 500 ETF",
        "asset_type": "etf",
        "exchange": "NYSE Arca",
    },
]


def _is_sp500_query(query: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", query.casefold())
    return normalized.startswith("sp500") or normalized.startswith("sandp500")


# --- Asset management -------------------------------------------------------------------

@router.get("/assets")
def list_assets():
    rows = fetch_all(
        "SELECT id, ticker, asset_type, name, purchase_price, quantity, date_added, notes, created_at, updated_at "
        "FROM assets ORDER BY ticker"
    )
    return [dict(r) for r in rows]


@router.post("/assets")
def add_asset(asset: dict[str, Any]):
    ticker = str(asset.get("ticker", "")).strip().upper()
    if not re.fullmatch(r"[A-Z0-9.^=_-]+", ticker):
        raise HTTPException(
            status_code=400,
            detail="Enter a ticker symbol or search by name and select a matching asset.",
        )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        rid = execute(
            """INSERT INTO assets (ticker, asset_type, name, purchase_price, quantity, date_added, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, asset.get("asset_type", "stock"), asset.get("name", ""),
             float(asset.get("purchase_price", 0)), float(asset.get("quantity", 0)),
             asset.get("date_added", now), asset.get("notes", ""), now, now),
            fetch=False,
        )
        return {"id": rid, "ticker": ticker, "message": "Asset added"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/assets/{ticker}")
def update_asset(ticker: str, updates: dict[str, Any]):
    normalized_ticker = ticker.strip().upper()
    allowed_fields = {"name", "asset_type", "notes"}
    unknown_fields = set(updates) - allowed_fields
    if unknown_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported asset fields: {', '.join(sorted(unknown_fields))}",
        )
    if not updates:
        raise HTTPException(status_code=400, detail="At least one asset field is required")

    values = {}
    for field in ("name", "notes"):
        if field in updates:
            if not isinstance(updates[field], str):
                raise HTTPException(status_code=400, detail=f"{field} must be a string")
            values[field] = updates[field].strip()

    if "asset_type" in updates:
        asset_type = str(updates["asset_type"]).strip().lower()
        if asset_type not in {"stock", "etf", "mutual_fund", "index_fund"}:
            raise HTTPException(status_code=400, detail="Invalid asset_type")
        values["asset_type"] = asset_type

    if not fetch_one("SELECT id FROM assets WHERE ticker = ?", (normalized_ticker,)):
        raise HTTPException(status_code=404, detail=f"Asset {normalized_ticker} not found")

    values["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    assignments = ", ".join(f"{field} = ?" for field in values)
    execute(
        f"UPDATE assets SET {assignments} WHERE ticker = ?",
        (*values.values(), normalized_ticker),
        fetch=False,
    )
    return {"ticker": normalized_ticker, "message": "Asset updated"}


@router.delete("/assets/{ticker}")
def delete_asset(ticker: str):
    normalized_ticker = ticker.strip().upper()
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM assets WHERE ticker = ?",
            (normalized_ticker,),
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Asset {normalized_ticker} not found")

        conn.execute(
            "DELETE FROM error_audits WHERE prediction_id IN "
            "(SELECT id FROM predictions WHERE ticker = ?)",
            (normalized_ticker,),
        )
        conn.execute("DELETE FROM predictions WHERE ticker = ?", (normalized_ticker,))
        conn.execute("DELETE FROM catalyst_events WHERE ticker = ?", (normalized_ticker,))
        conn.execute("DELETE FROM price_history WHERE ticker = ?", (normalized_ticker,))
        conn.execute("DELETE FROM forecast_accuracy WHERE ticker = ?", (normalized_ticker,))
        cursor = conn.execute("DELETE FROM assets WHERE ticker = ?", (normalized_ticker,))
        conn.commit()
        return {"ticker": normalized_ticker, "message": "Asset deleted"}
    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/assets/search")
def search_assets(query: str, limit: int = 10):
    search_term = query.strip()
    if not search_term:
        raise HTTPException(status_code=400, detail="query must not be empty")
    if _is_sp500_query(search_term):
        return [asset.copy() for asset in SP500_ASSETS[:min(max(limit, 1), 20)]]

    try:
        import yfinance as yf

        quotes = yf.Search(
            search_term,
            max_results=min(max(limit, 1), 20),
            news_count=0,
            lists_count=0,
            timeout=15,
        ).quotes or []
    except Exception as error:
        logger.warning("Asset search failed for %r: %s", search_term, error)
        raise HTTPException(status_code=502, detail=f"Unable to search for assets: {error}") from error

    results = []
    seen_tickers = set()
    asset_types = {"ETF": "etf", "MUTUALFUND": "mutual_fund", "INDEX": "index_fund"}
    for quote in quotes:
        ticker = str(quote.get("symbol") or "").strip().upper()
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        quote_type = str(quote.get("quoteType") or "").upper()
        results.append(
            {
                "ticker": ticker,
                "name": str(quote.get("longname") or quote.get("shortname") or ticker),
                "asset_type": asset_types.get(quote_type, "stock"),
                "exchange": str(quote.get("exchDisp") or quote.get("exchange") or ""),
            }
        )
    return results


@router.get("/assets/{ticker}/price-history")
def get_price_history(ticker: str):
    normalized_ticker = ticker.upper()
    _fetch_and_store_price_history(normalized_ticker)
    rows = fetch_all(
        "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date DESC",
        (normalized_ticker,),
    )
    return [dict(r) for r in rows]


@router.get("/assets/{ticker}/catalysts")
def get_catalysts(ticker: str):
    rows = fetch_all("SELECT id, event_date, event_type, title, summary, source, confidence FROM catalyst_events WHERE ticker = ? ORDER BY event_date DESC", (ticker.upper(),))
    return [dict(r) for r in rows]


def _normalize_price_history(ticker: str, data: Any) -> list[tuple[str, str, float, float, float, float, int]]:
    import pandas as pd

    if data is None or data.empty:
        return []

    if isinstance(data.columns, pd.MultiIndex):
        for level in range(data.columns.nlevels):
            if ticker in data.columns.get_level_values(level):
                data = data.xs(ticker, axis=1, level=level)
                break
        else:
            data.columns = data.columns.get_level_values(0)

    columns = {str(column).strip().lower().replace(" ", "_"): column for column in data.columns}
    required = ("open", "high", "low", "close", "volume")
    if any(column not in columns for column in required):
        raise HTTPException(status_code=502, detail=f"Market data for {ticker} is missing OHLCV fields")

    records = []
    for timestamp, row in data.sort_index().iterrows():
        values = [row[columns[column]] for column in required]
        if any(pd.isna(value) for value in values[:4]):
            continue
        records.append(
            (
                ticker,
                pd.to_datetime(timestamp).strftime("%Y-%m-%d"),
                float(values[0]),
                float(values[1]),
                float(values[2]),
                float(values[3]),
                int(values[4]) if not pd.isna(values[4]) else 0,
            )
        )
    return records


def _fetch_and_store_price_history(ticker: str) -> None:
    today = datetime.now(timezone.utc).date()
    try:
        start = today.replace(year=today.year - 99)
    except ValueError:
        start = today.replace(year=today.year - 99, day=28)
    end = today + timedelta(days=1)
    try:
        data = market_data.DataFetcher([market_data.YFinanceSource()]).fetch_ohlcv(
            ticker,
            start.isoformat(),
            end.isoformat(),
        )
    except market_data.DataFetchError as error:
        raise HTTPException(status_code=502, detail=f"Unable to fetch market data for {ticker}: {error}") from error

    records = _normalize_price_history(ticker, data)
    if not records:
        raise HTTPException(status_code=404, detail=f"No market data available for {ticker}")

    executemany(
        """INSERT INTO price_history (ticker, date, open, high, low, close, volume)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(ticker, date) DO UPDATE SET
               open = excluded.open,
               high = excluded.high,
               low = excluded.low,
               close = excluded.close,
               volume = excluded.volume""",
        records,
    )


def _price_history_frame(rows: list[Any]):
    import pandas as pd

    frame = pd.DataFrame([dict(row) for row in rows])
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    return frame[["open", "high", "low", "close", "volume"]]


@router.get("/news/search")
def search_news(query: str, limit: int = 20):
    search_term = query.strip()
    if not search_term:
        raise HTTPException(status_code=400, detail="query must not be empty")

    settings = {row["key"]: row["value"] for row in fetch_all("SELECT key, value FROM app_settings")}
    sources: list[news_fetcher.NewsSource] = []
    if settings.get("finnhub_api_key"):
        sources.append(news_fetcher.FinnhubNewsSource(settings["finnhub_api_key"]))
    if settings.get("marketaux_api_key"):
        sources.append(news_fetcher.MarketauxNewsSource(settings["marketaux_api_key"]))
    sources.append(news_fetcher.YahooFinanceNewsSource())
    sources.append(news_fetcher.RSSNewsSource())

    articles = news_fetcher.NewsFetcher(sources).search(search_term, limit=min(max(limit, 1), 50))
    normalized = []
    for article in articles:
        source = article.get("source") or article.get("source_name") or "News"
        if isinstance(source, dict):
            source = source.get("name") or "News"
        published = article.get("published") or article.get("published_at") or article.get("datetime") or ""
        if isinstance(published, (int, float)):
            published = datetime.fromtimestamp(published, timezone.utc).isoformat()
        normalized.append(
            {
                "source": str(source),
                "title": article.get("title") or article.get("headline") or "Untitled",
                "summary": article.get("summary") or article.get("description") or "",
                "url": article.get("url") or article.get("link") or "",
                "published": str(published),
            }
        )
    return normalized


@router.post("/forecast")
def generate_forecast(payload: dict[str, Any]):
    """Generate forecasts for a ticker. Expects: ticker, price_history (optional), news_context (optional)."""
    ticker = payload.get("ticker", "").upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")

    rows = fetch_all(
        "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date DESC",
        (ticker,),
    )
    if not rows:
        _fetch_and_store_price_history(ticker)
        rows = fetch_all(
            "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date DESC",
            (ticker,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price history for {ticker}")

    df = _price_history_frame(rows)

    news_query = payload.get("news_query", ticker)
    news_results = payload.get("news_context", [])
    if isinstance(news_results, list) and news_results:
        news_context = news_results
    else:
        news_context = [{"title": f"Relevant news for {news_query}", "summary": ""}]

    calibration = forecast_service._load_calibration_context(ticker, "tech" if "tech" in news_query.lower() else "general")

    result = build_forecast(
        ticker,
        df,
        news_context,
        calibration,
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
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
                "SELECT date, open, high, low, close, volume FROM price_history WHERE ticker = ? ORDER BY date DESC",
                (ticker,),
            )
            if not rows:
                continue
            df = _price_history_frame(rows)

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
