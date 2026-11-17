import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi import HTTPException

from stock_predictor_server.api import main, routes
from stock_predictor_server.api.routes import _normalize_price_history
from stock_predictor_server.core import forecast_service
from stock_predictor_server.core.prediction_engine import generate_forecast
from stock_predictor_server.db import connection
from stock_predictor_server.services.news_fetcher import RSSNewsSource


class PriceHistoryNormalizationTests(unittest.TestCase):
    def test_long_history_forecast_generates_all_horizons(self):
        data = pd.DataFrame(
            {"close": [40.0 + index for index in range(25)]},
            index=pd.date_range("2025-01-01", periods=25),
        )

        forecast = generate_forecast("ACME", data, [], {}, "2025-01-26T00:00:00Z")

        self.assertEqual(len(forecast["predictions"]), 9)
        self.assertIn("historical price trends", forecast["predictions"]["1d"]["key_assumptions"])

    def test_short_history_forecast_uses_latest_close_not_fixed_price(self):
        data = pd.DataFrame(
            {"close": [42.75]},
            index=[pd.Timestamp("2025-01-02")],
        )

        forecast = generate_forecast("ACME", data, [], {}, "2025-01-03T00:00:00Z")

        self.assertEqual(forecast["predictions"]["1d"]["predicted_price"], 42.75)
        self.assertIn("Insufficient historical data", forecast["predictions"]["1d"]["key_assumptions"])

    def test_normalizes_yfinance_multiindex_columns(self):
        columns = pd.MultiIndex.from_tuples(
            [
                ("Open", "ACME"),
                ("High", "ACME"),
                ("Low", "ACME"),
                ("Close", "ACME"),
                ("Volume", "ACME"),
            ]
        )
        data = pd.DataFrame(
            [[10.0, 12.0, 9.0, 11.0, 100]],
            columns=columns,
            index=[pd.Timestamp("2025-01-02")],
        )

        self.assertEqual(
            _normalize_price_history("ACME", data),
            [("ACME", "2025-01-02", 10.0, 12.0, 9.0, 11.0, 100)],
        )

    def test_rejects_market_data_without_required_fields(self):
        data = pd.DataFrame({"Close": [11.0]}, index=[pd.Timestamp("2025-01-02")])

        with self.assertRaises(HTTPException) as error:
            _normalize_price_history("ACME", data)

        self.assertEqual(error.exception.status_code, 502)

    def test_price_history_route_fetches_and_persists_missing_history(self):
        data = pd.DataFrame(
            {
                "Open": [10.0],
                "High": [12.0],
                "Low": [9.0],
                "Close": [11.0],
                "Volume": [100],
            },
            index=[pd.Timestamp("2025-01-02")],
        )
        stored_rows = [
            {
                "date": "2025-01-02",
                "open": 10.0,
                "high": 12.0,
                "low": 9.0,
                "close": 11.0,
                "volume": 100,
            }
        ]
        fetch_args = {}

        class FakeFetcher:
            def __init__(self, _sources):
                pass

            def fetch_ohlcv(self, _ticker, start, end):
                fetch_args["range"] = (start, end)
                return data

        with patch.object(routes, "fetch_all", return_value=stored_rows) as fetch:
            with patch.object(routes, "executemany") as insert:
                with patch.object(routes.market_data, "DataFetcher", FakeFetcher):
                    result = routes.get_price_history("ACME")

        self.assertEqual(result, stored_rows)
        self.assertNotIn("LIMIT", fetch.call_args.args[0].upper())
        self.assertEqual(insert.call_args.args[1][0][1], "2025-01-02")
        today = datetime.now(timezone.utc).date()
        try:
            expected_start = today.replace(year=today.year - 99)
        except ValueError:
            expected_start = today.replace(year=today.year - 99, day=28)
        self.assertEqual(
            fetch_args["range"],
            (expected_start.isoformat(), (today + timedelta(days=1)).isoformat()),
        )


class RSSNewsSourceTests(unittest.TestCase):
    def test_search_routes_are_published_in_openapi(self):
        paths = main.app.openapi()["paths"]

        self.assertIn("/api/news/search", paths)
        self.assertIn("/api/assets/search", paths)

    def test_search_assets_returns_ticker_and_name(self):
        class FakeSearch:
            def __init__(self, query, **_kwargs):
                self.quotes = [
                    {
                        "symbol": "UBSSNP.JO",
                        "shortname": "UBS S&P 500",
                        "quoteType": "ETF",
                        "exchDisp": "Johannesburg",
                    }
                ]

        with patch("yfinance.Search", FakeSearch):
            results = routes.search_assets("UBS S&P 500")

        self.assertEqual(
            results,
            [
                {
                    "ticker": "UBSSNP.JO",
                    "name": "UBS S&P 500",
                    "asset_type": "etf",
                    "exchange": "Johannesburg",
                }
            ],
        )

    def test_add_asset_rejects_a_fund_name_as_a_ticker(self):
        with self.assertRaises(HTTPException) as error:
            routes.add_asset({"ticker": "UBS S&P 500"})

        self.assertEqual(error.exception.status_code, 400)

    def test_s_and_p_500_search_always_returns_matching_funds(self):
        results = routes.search_assets("S&P 500")

        self.assertIn("SPY", {result["ticker"] for result in results})
        self.assertIn("VOO", {result["ticker"] for result in results})
        self.assertTrue(all(result["asset_type"] == "etf" for result in results))

    def test_returns_matching_entries_from_rss(self):
        class FakeResponse:
            content = b"<rss />"

        class FakeSession:
            def get(self, _url, timeout):
                return FakeResponse()

        class FakeFeedParser:
            @staticmethod
            def parse(_content):
                return {
                    "entries": [
                        {
                            "title": "Chip makers rally",
                            "link": "https://example.test/article",
                            "summary": "Semiconductor shares rose.",
                            "published": "2025-01-02",
                        }
                    ]
                }

        source = RSSNewsSource(feeds=["https://example.test/feed"])
        source._session = FakeSession()
        source._feedparser = FakeFeedParser()

        results = source.search("semiconductor", limit=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Chip makers rally")

    def test_news_route_normalizes_article_fields(self):
        class FakeNewsSource:
            def search(self, _query, from_date=None, to_date=None, limit=20):
                return [
                    {
                        "headline": "Markets move",
                        "source": {"name": "Example News"},
                        "published": "2025-01-02",
                        "url": "https://example.test/markets",
                    }
                ]

        with patch.object(routes, "fetch_all", return_value=[]):
            with patch.object(
                routes.news_fetcher,
                "RSSNewsSource",
                return_value=FakeNewsSource(),
            ):
                articles = routes.search_news("markets")

        self.assertEqual(
            articles,
            [
                {
                    "source": "Example News",
                    "title": "Markets move",
                    "summary": "",
                    "url": "https://example.test/markets",
                    "published": "2025-01-02",
                }
            ],
        )


class DatabaseInitializationTests(unittest.TestCase):
    def test_initializes_schema_in_configured_database_path(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "isolated.db"
                connection.initialize_database()
                tables = connection.fetch_all(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'assets'"
                )
                self.assertEqual(len(tables), 1)
        finally:
            connection.DB_PATH = original_path

    def test_prediction_saves_and_calibration_uses_schema_columns(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "forecast.db"
                connection.initialize_database()
                connection.execute(
                    "INSERT INTO assets (ticker, asset_type, name, date_added) VALUES (?, ?, ?, ?)",
                    ("ACME", "stock", "Example", "2025-01-01"),
                )

                inserted = forecast_service.save_prediction(
                    {
                        "ticker": "ACME",
                        "predictions": {
                            "1d": {
                                "prediction_date": "2025-01-02T00:00:00Z",
                                "predicted_price": 42.75,
                                "confidence_interval": 40.0,
                                "sentiment_score": 0.0,
                                "key_assumptions": "test",
                            }
                        },
                    }
                )
                rows = connection.fetch_all(
                    "SELECT predicted_price FROM predictions WHERE ticker = ?",
                    ("ACME",),
                )

                self.assertEqual(inserted, 1)
                self.assertEqual(rows[0]["predicted_price"], 42.75)
                self.assertEqual(
                    forecast_service._load_calibration_context("ACME", "general"),
                    {"bias_correction": 0.0, "temper_bullish": False},
                )
        finally:
            connection.DB_PATH = original_path

    def test_manual_forecast_reads_sqlite_rows_with_named_columns(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "forecast-route.db"
                connection.initialize_database()
                connection.execute(
                    "INSERT INTO assets (ticker, asset_type, name, date_added) VALUES (?, ?, ?, ?)",
                    ("ACME", "stock", "Example", "2025-01-01"),
                )
                for index in range(25):
                    day = datetime(2025, 1, 1) + timedelta(days=index)
                    price = 40.0 + index
                    connection.execute(
                        "INSERT INTO price_history (ticker, date, open, high, low, close, volume) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ("ACME", day.date().isoformat(), price, price, price, price, 1000),
                    )

                result = routes.generate_forecast({"ticker": "ACME"})

                self.assertEqual(len(result["predictions"]), 9)
                self.assertEqual(
                    connection.fetch_one("SELECT COUNT(*) AS count FROM predictions")["count"],
                    9,
                )
        finally:
            connection.DB_PATH = original_path

    def test_updating_and_deleting_assets_manages_related_data(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "asset-crud.db"
                connection.initialize_database()
                connection.execute(
                    "INSERT INTO assets (ticker, asset_type, name, date_added) VALUES (?, ?, ?, ?)",
                    ("ACME", "stock", "Example", "2025-01-01"),
                )
                connection.execute(
                    "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
                    ("ACME", "2025-01-02", 42.0),
                )
                prediction_id = connection.execute(
                    "INSERT INTO predictions (ticker, horizon, prediction_date, predicted_price) "
                    "VALUES (?, ?, ?, ?)",
                    ("ACME", "1d", "2025-01-02", 43.0),
                )
                connection.execute(
                    "INSERT INTO error_audits "
                    "(prediction_id, audit_date, actual_close, absolute_error, percentage_error, directional_correct) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (prediction_id, "2025-01-03", 42.0, 1.0, 0.02, 1),
                )
                connection.execute(
                    "INSERT INTO forecast_accuracy (ticker, horizon) VALUES (?, ?)",
                    ("ACME", "1d"),
                )

                routes.update_asset(
                    "ACME",
                    {"name": "Updated Example", "asset_type": "etf", "notes": "watch"},
                )
                updated = connection.fetch_one(
                    "SELECT name, asset_type, notes FROM assets WHERE ticker = ?",
                    ("ACME",),
                )
                self.assertEqual(tuple(updated), ("Updated Example", "etf", "watch"))

                routes.delete_asset("ACME")

                for table in ("assets", "price_history", "predictions", "error_audits", "forecast_accuracy"):
                    count = connection.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"]
                    self.assertEqual(count, 0, table)
        finally:
            connection.DB_PATH = original_path
