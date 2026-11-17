#!/usr/bin/env python3
"""
Startup script to create the SQLite DB, apply migrations, and launch the FastAPI backend.

Usage:
    python start_server.py            # start the dev server
    python start_server.py --daily    # run one daily pipeline and exit
    python start_server.py --migrate  # create tables and exit
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure backend dir is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from stock_predictor_server.db.connection import DB_DIR, DB_PATH, initialize_database
from stock_predictor_server.api.main import app


def init_db():
    """Create directory and tables if they don't exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()
    logging.info("Database initialized: %s", DB_PATH)


def run_daily():
    """One-shot daily pipeline."""
    init_db()
    from stock_predictor_server.core import error_auditor, forecast_service
    from stock_predictor_server.core.prediction_engine import generate_forecast
    from stock_predictor_server.services import market_data, news_fetcher
    from datetime import datetime, timezone

    sources = [
        market_data.YFinanceSource(),
        news_fetcher.RSSNewsSource(),
    ]
    fetcher = market_data.DataFetcher(sources)
    news_fetcher_ = news_fetcher.NewsFetcher(sources + [news_fetcher.RSSNewsSource()])

    from stock_predictor_server.db.connection import fetch_all
    assets = fetch_all("SELECT ticker, asset_type, name, notes FROM assets")
    if not assets:
        logging.warning("No assets found in the database.")
        return

    results = []
    for asset in assets:
        ticker = asset["ticker"]
        try:
            df = fetcher.fetch_ohlcv(ticker, start="2019-01-01",
                                     end=datetime.now(timezone.utc).strftime("%Y-%m-%d"), interval="1d")
            if df is None or df.empty:
                logging.warning("No price data for %s", ticker)
                results.append({"ticker": ticker, "error": "No data"})
                continue

            news = news_fetcher_.search(ticker, from_date="2026-11-01", limit=10)
            cal = forecast_service._load_calibration_context(ticker, "general")

            from datetime import datetime as dt
            today = dt.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            from stock_predictor_server.core.prediction_engine import generate_forecast
            fc = generate_forecast(ticker, df, news, cal, today)
            forecast_service.save_prediction(fc)
            results.append({"ticker": ticker, "forecasts_generated": 9,
                            "horizons": list(fc["predictions"].keys())})
        except Exception as e:
            logging.warning("Forecast failed for %s: %s", ticker, e)
            results.append({"ticker": ticker, "error": str(e)})

    logging.info("Daily pipeline complete. Results: %s", results)
    for r in results:
        print(f"  {r['ticker']}: {r}")


def main():
    parser = argparse.ArgumentParser(description="Stock Predictor: Startup & Backend")
    parser.add_argument("--migrate", action="store_true", help="Create tables and exit")
    parser.add_argument("--daily", action="store_true", help="Run one daily pipeline and exit")
    parser.add_argument("--host", default="127.0.0.1", help="Uvicorn host")
    parser.add_argument("--port", type=int, default=8000, help="Uvicorn port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    if args.migrate:
        init_db()
        print(f"Database initialized at {DB_PATH}")
        return

    if args.daily:
        run_daily()
        return

    import uvicorn
    logging.info("Starting Stock Predictor API on http://%s:%d", args.host, args.port)
    uvicorn.run("stock_predictor_server.api.main:app", host=args.host, port=args.port,
                reload=args.reload)


if __name__ == "__main__":
    main()
