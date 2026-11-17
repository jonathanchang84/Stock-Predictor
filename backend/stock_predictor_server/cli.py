"""CLI entry point for the Stock Predictor daily runner and service."""

import argparse
import logging
from datetime import datetime, timezone

import uvicorn

from .api.main import app
from .db.connection import get_connection
from .db.connection import DB_PATH

logger = logging.getLogger(__name__)


def run_daily():
    """Run the full daily pipeline: audit + forecast."""
    from .core import error_auditor, forecast_service
    from .core.prediction_engine import generate_forecast
    from .services import market_data, news_fetcher

    # Ensure SQLite is initialized
    conn = get_connection()
    conn.close()

    # Build data sources
    sources = [
        market_data.YFinanceSource(),
        news_fetcher.RSSNewsSource(),
    ]
    fetcher = market_data.DataFetcher(sources)
    news_fetcher_ = news_fetcher.NewsFetcher(sources + [news_fetcher.RSSNewsSource()])

    # Load assets
    from ..db.connection import fetch_all
    assets = fetch_all("SELECT ticker, asset_type, name, notes FROM assets")
    if not assets:
        logger.warning("No assets found in the database.")
        return

    results = []
    for asset in assets:
        ticker = asset["ticker"]
        try:
            # Fetch price history (up to 5 years for CAGR + volatility)
            df = fetcher.fetch_ohlcv(ticker, start="2019-01-01", end=datetime.now(timezone.utc).strftime("%Y-%m-%d"), interval="1d")
            if df is None or df.empty:
                logger.warning("No price data for %s", ticker)
                results.append({"ticker": ticker, "error": "No data"})
                continue

            # Fetch news
            news = news_fetcher_.search(ticker, from_date="2026-11-01", limit=10)

            # Load calibration
            cal = forecast_service._load_calibration_context(ticker, "general")

            # Generate forecast
            from datetime import datetime as dt
            today = dt.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            from ..core.prediction_engine import generate_forecast
            fc = generate_forecast(ticker, df, news, cal, today)

            # Save prediction ledger
            forecast_service.save_prediction(fc)

            results.append({"ticker": ticker, "forecasts_generated": 9, "horizons": list(fc["predictions"].keys())})
        except Exception as e:
            logger.warning("Forecast failed for %s: %s", ticker, e)
            results.append({"ticker": ticker, "error": str(e)})

    logger.info("Daily pipeline complete. Results: %s", results)
    print("Daily run done.")
    for r in results:
        print(f"  {r['ticker']}: {r}")


def main():
    parser = argparse.ArgumentParser(description="Stock Predictor CLI")
    parser.add_argument("--daily", action="store_true", help="Run the daily pipeline and exit")
    parser.add_argument("--host", default="127.0.0.1", help="Uvicorn host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Uvicorn port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.daily:
        run_daily()
        return

    logger.info("Starting Stock Predictor API on http://%s:%d", args.host, args.port)
    uvicorn.run("stock_predictor_server.api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
