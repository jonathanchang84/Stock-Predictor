import tempfile
import unittest
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi import HTTPException

from stock_predictor_server.api import main, routes
from stock_predictor_server.api.routes import _normalize_price_history
from stock_predictor_server.core.backtester import walk_forward_backtest
from stock_predictor_server.core import error_auditor, forecast_service
from stock_predictor_server.core.context_signals import build_context_signals
from stock_predictor_server.core.prediction_engine import MODEL_VERSION, generate_forecast
from stock_predictor_server.db import connection
from stock_predictor_server.services.market_data import YFinanceSource
from stock_predictor_server.services import market_context as market_context_service
from stock_predictor_server.services.news_fetcher import RSSNewsSource, YahooFinanceNewsSource


class MarketContextTests(unittest.TestCase):
    def test_normalizes_yahoo_fundamentals_and_only_future_events(self):
        class FakeTicker:
            def get_info(self):
                return {
                    "shortName": "Example Corp",
                    "quoteType": "EQUITY",
                    "sector": "Technology",
                    "marketCap": 1_000_000_000,
                    "revenueGrowth": 0.12,
                    "earningsTimestampStart": int(
                        datetime(2025, 1, 20, tzinfo=timezone.utc).timestamp()
                    ),
                }

            @property
            def calendar(self):
                return pd.DataFrame(
                    {
                        "Value": [
                            pd.Timestamp("2025-01-20"),
                            pd.Timestamp("2024-12-15"),
                        ]
                    },
                    index=["Earnings Date", "Ex-Dividend Date"],
                )

        with patch("yfinance.Ticker", return_value=FakeTicker()):
            context = market_context_service._load_market_context(
                "ACME",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(context["fundamentals"]["sector"], "Technology")
        self.assertEqual(context["fundamentals"]["revenue_growth"], 0.12)
        self.assertEqual(len(context["upcoming_events"]), 1)
        self.assertEqual(context["upcoming_events"][0]["type"], "earnings")
        self.assertEqual(context["upcoming_events"][0]["date"], "2025-01-20")

    def test_dividend_payment_date_is_not_treated_as_ex_dividend_date(self):
        events = market_context_service._normalize_calendar(
            pd.DataFrame(
                {"Value": [pd.Timestamp("2025-02-01")]},
                index=["Dividend Date"],
            ),
            {},
            datetime(2025, 1, 1).date(),
        )

        self.assertEqual(events[0]["type"], "dividend")
        self.assertEqual(events[0]["label"], "Dividend")

    def test_quote_type_only_context_reports_missing_fundamental_metrics(self):
        class FakeTicker:
            def get_info(self):
                return {"quoteType": "ETF"}

            @property
            def calendar(self):
                return {}

        with patch("yfinance.Ticker", return_value=FakeTicker()):
            context = market_context_service._load_market_context(
                "FUND",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
            )

        self.assertEqual(context["fundamentals"]["quote_type"], "ETF")
        self.assertIn(
            "Yahoo Finance returned no usable fundamental metrics",
            context["warnings"],
        )

    def test_news_fundamentals_and_events_produce_separate_bounded_signals(self):
        signal = build_context_signals(
            [
                {
                    "title": "Company beats estimates and raises guidance",
                    "summary": "",
                    "url": "https://example.test/news",
                    "published": "2025-04-10T12:00:00Z",
                },
                {
                    "title": "Company misses estimates",
                    "summary": "",
                    "url": "https://example.test/old",
                    "published": "2025-03-20T12:00:00Z",
                },
                {
                    "title": "Future article should not be used",
                    "summary": "Strong growth",
                    "url": "https://example.test/future",
                    "published": "2025-04-11T12:00:00Z",
                },
            ],
            {
                "fundamentals": {
                    "quote_type": "EQUITY",
                    "revenue_growth": 0.2,
                    "earnings_growth": 0.2,
                    "profit_margin": 0.2,
                    "return_on_equity": 0.2,
                },
                "upcoming_events": [
                    {
                        "type": "earnings",
                        "date": "2025-04-15",
                        "label": "Earnings",
                        "source": "Yahoo Finance",
                    }
                ],
            },
            365,
            "2025-04-10T20:00:00Z",
        )

        self.assertEqual(signal["news_articles_used"], 1)
        self.assertEqual(signal["news_sentiment_score"], 0.3333)
        self.assertEqual(signal["news_adjustment_pct"], 0.0)
        self.assertGreater(signal["fundamental_score"], 0)
        self.assertGreater(signal["fundamental_annualized_adjustment_pct"], 0)
        self.assertEqual(signal["event_risk_multiplier"], 1.25)

    def test_fundamental_overlay_does_not_treat_funds_as_companies(self):
        signal = build_context_signals(
            [],
            {
                "fundamentals": {
                    "quote_type": "ETF",
                    "revenue_growth": 0.3,
                    "earnings_growth": 0.3,
                    "profit_margin": 0.2,
                },
                "upcoming_events": [],
            },
            365,
            "2025-04-10T20:00:00Z",
        )

        self.assertIsNone(signal["fundamental_score"])
        self.assertEqual(signal["fundamental_annualized_adjustment_pct"], 0.0)

    def test_tracked_fund_type_overrides_incomplete_provider_quote_type(self):
        signal = build_context_signals(
            [],
            {
                "asset_type": "index_fund",
                "fundamentals": {
                    "quote_type": "EQUITY",
                    "revenue_growth": 0.3,
                    "earnings_growth": 0.3,
                    "profit_margin": 0.2,
                },
                "upcoming_events": [],
            },
            365,
            "2025-04-10T20:00:00Z",
        )

        self.assertIsNone(signal["fundamental_score"])
        self.assertEqual(signal["fundamental_annualized_adjustment_pct"], 0.0)


class PriceHistoryNormalizationTests(unittest.TestCase):
    def test_long_history_forecast_generates_all_horizons(self):
        data = pd.DataFrame(
            {"close": [40.0 + index for index in range(25)]},
            index=pd.date_range("2025-01-01", periods=25),
        )

        forecast = generate_forecast("ACME", data, [], {}, "2025-01-26T00:00:00Z")

        self.assertEqual(len(forecast["predictions"]), 9)
        self.assertIn("annualized volatility was", forecast["predictions"]["1d"]["key_assumptions"])
        self.assertIn("close was", forecast["predictions"]["1d"]["key_assumptions"])

    def test_forecast_uses_distinct_short_and_long_horizon_models(self):
        closes = [100.0 + index * 0.1 for index in range(1500)]
        data = pd.DataFrame(
            {"close": closes},
            index=pd.bdate_range("2018-01-01", periods=len(closes)),
        )

        forecast = generate_forecast("ACME", data, [], {}, "2025-01-01T00:00:00Z")
        predictions = forecast["predictions"]

        self.assertGreater(
            predictions["20y"]["predicted_price"],
            predictions["1d"]["predicted_price"] * 2,
        )
        self.assertIn("recent 20-session momentum", predictions["1m"]["key_assumptions"])
        self.assertIn("nominal baseline", predictions["20y"]["key_assumptions"])
        self.assertIn("capped at -8% to +12%", predictions["20y"]["key_assumptions"])
        self.assertGreater(predictions["20y"]["high"], predictions["20y"]["low"])
        self.assertEqual(predictions["20y"]["interval_coverage"], 0.9)
        self.assertIn("not backtest-calibrated", predictions["20y"]["interval_method"])
        annualized_20y_change = (
            (predictions["20y"]["predicted_price"] / closes[-1]) ** (365.25 / 7300) - 1
        )
        self.assertLessEqual(annualized_20y_change, 0.1201)

    def test_signed_horizon_residuals_correct_only_matching_forecasts(self):
        closes = [100.0 + index * 0.1 for index in range(1500)]
        data = pd.DataFrame(
            {"close": closes},
            index=pd.bdate_range("2018-01-01", periods=len(closes)),
        )
        history = {"residuals": [0.1] * 20}

        baseline = generate_forecast("ACME", data, [], {}, "2025-01-01T00:00:00Z")
        corrected = generate_forecast(
            "ACME",
            data,
            [],
            {"horizons": {"1d": history, "7d": {"residuals": [0.1]}}},
            "2025-01-01T00:00:00Z",
        )

        self.assertGreater(
            corrected["predictions"]["1d"]["predicted_price"],
            baseline["predictions"]["1d"]["predicted_price"],
        )
        self.assertEqual(
            corrected["predictions"]["7d"]["predicted_price"],
            baseline["predictions"]["7d"]["predicted_price"],
        )
        self.assertEqual(corrected["predictions"]["1d"]["interval_sample_size"], 20)
        self.assertIn("historical 90%", corrected["predictions"]["1d"]["interval_method"])
        self.assertIn(
            "Recent forecast-error calibration was applied.",
            corrected["predictions"]["1d"]["key_assumptions"],
        )
        self.assertNotIn(
            "Recent forecast-error calibration was applied.",
            corrected["predictions"]["7d"]["key_assumptions"],
        )

    def test_forecast_uses_bounded_news_fundamental_and_event_context(self):
        data = pd.DataFrame(
            {"close": [100.0 + index * 0.001 for index in range(100)]},
            index=pd.date_range("2025-01-01", periods=100),
        )
        as_of = "2025-04-11T20:00:00Z"
        news = [
            {
                "title": "Company beats estimates and raises guidance",
                "summary": "",
                "url": "https://example.test/news",
                "source": "Example",
                "published": "2025-04-11T12:00:00Z",
            }
        ]
        context = {
            "ticker": "ACME",
            "source": "Yahoo Finance",
            "captured_at": as_of,
            "fundamentals": {
                "quote_type": "EQUITY",
                "revenue_growth": 0.2,
                "earnings_growth": 0.2,
                "profit_margin": 0.2,
                "return_on_equity": 0.2,
            },
            "upcoming_events": [
                {
                    "type": "earnings",
                    "date": "2025-04-18",
                    "label": "Earnings",
                    "source": "Yahoo Finance",
                }
            ],
            "warnings": [],
        }

        baseline = generate_forecast("ACME", data, [], {}, as_of)
        contextual = generate_forecast("ACME", data, news, {}, as_of, context)

        self.assertGreater(
            contextual["predictions"]["1d"]["predicted_price"],
            baseline["predictions"]["1d"]["predicted_price"],
        )
        self.assertGreater(
            contextual["predictions"]["1y"]["predicted_price"],
            baseline["predictions"]["1y"]["predicted_price"],
        )
        self.assertIn(
            "widened for scheduled-event risk",
            contextual["predictions"]["1y"]["interval_method"],
        )
        self.assertIn(
            "Recent headline sentiment",
            contextual["predictions"]["1d"]["key_assumptions"],
        )
        self.assertIn(
            "fundamentals score",
            contextual["predictions"]["1y"]["key_assumptions"],
        )
        self.assertLessEqual(
            contextual["context_signals"]["1d"]["news_adjustment_pct"],
            0.5,
        )
        self.assertLessEqual(
            contextual["context_signals"]["1y"]["fundamental_annualized_adjustment_pct"],
            1.0,
        )

    def test_forecast_returns_only_sourced_http_news_context(self):
        data = pd.DataFrame(
            {"close": [40.0 + index for index in range(25)]},
            index=pd.date_range("2025-01-01", periods=25),
        )

        forecast = generate_forecast(
            "ACME",
            data,
            [
                {"title": "Quarterly results", "url": "https://example.test/results", "source": "Example"},
                {"title": "Unsafe link", "url": "javascript:alert(1)", "source": "Example"},
                "not-an-article",
            ],
            {},
            "2025-01-26T00:00:00Z",
        )

        self.assertEqual(
            forecast["news_context"],
            [
                {
                    "title": "Quarterly results",
                    "summary": "",
                    "url": "https://example.test/results",
                    "source": "Example",
                    "published": "",
                }
            ],
        )

    def test_walk_forward_backtest_uses_past_only_and_compares_flat_baseline(self):
        data = pd.DataFrame(
            {"close": [50.0 + index * 0.05 for index in range(800)]},
            index=pd.bdate_range("2022-01-03", periods=800),
        )
        forecast_dates = []

        def fake_forecast(_ticker, history, _news, _calibration, today, market_context=None):
            forecast_dates.append((history.index[-1], today, market_context))
            return {
                "predictions": {
                    horizon: {
                        "predicted_price": float(history["close"].iloc[-1]),
                        "low": float(history["close"].iloc[-1] * 0.9),
                        "high": float(history["close"].iloc[-1] * 1.1),
                    }
                    for horizon in ("1d", "7d", "1m", "6m", "1y", "3y", "5y", "10y", "20y")
                }
            }

        first_origin = data.index[251]
        snapshots = [
            {
                "captured_at": (first_origin - timedelta(days=45)).strftime("%Y-%m-%dT23:00:00Z"),
                "context": {
                    "market_context": {"fundamentals": {"sector": "Technology"}},
                    "news_context": [],
                },
            },
            {
                "captured_at": (first_origin + timedelta(days=2)).strftime("%Y-%m-%dT23:00:00Z"),
                "context": {
                    "market_context": {"fundamentals": {"sector": "Future"}},
                    "news_context": [],
                },
            },
        ]
        with patch("stock_predictor_server.core.backtester.generate_forecast", fake_forecast):
            result = walk_forward_backtest(
                "ACME",
                data,
                minimum_train_rows=252,
                step_rows=63,
                context_snapshots=snapshots,
            )

        self.assertGreater(result["horizons"]["1d"]["sample_size"], 0)
        self.assertIsNotNone(result["horizons"]["1d"]["baseline"])
        self.assertEqual(result["horizons"]["20y"]["sample_size"], 0)
        self.assertTrue(
            all(
                history_date.strftime("%Y-%m-%d") == today[:10]
                for history_date, today, _ in forecast_dates
            )
        )
        self.assertEqual(result["horizons"]["1d"]["context_sample_size"], 2)
        self.assertEqual(
            forecast_dates[0][2]["fundamentals"]["sector"],
            "Technology",
        )
        self.assertEqual(forecast_dates[1][2]["fundamentals"]["sector"], "Future")
        self.assertIsNone(forecast_dates[-1][2])
        self.assertIn("90 days old", result["methodology"])

    def test_backtest_route_evaluates_saved_price_history(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "backtest-route.db"
                connection.initialize_database()
                start = datetime(2024, 1, 1)
                connection.execute(
                    "INSERT INTO assets (ticker, asset_type, name, date_added) VALUES (?, ?, ?, ?)",
                    ("ACME", "stock", "Example", "2024-01-01"),
                )
                connection.executemany(
                    "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
                    [
                        ("ACME", (start + timedelta(days=index)).date().isoformat(), 50 + index * 0.05)
                        for index in range(300)
                    ],
                )

                result = routes.backtest_forecasts("acme")

                self.assertEqual(result["ticker"], "ACME")
                self.assertEqual(result["model_version"], MODEL_VERSION)
                self.assertGreater(result["horizons"]["1d"]["sample_size"], 0)
                self.assertIn("flat last-close baseline", result["methodology"])
        finally:
            connection.DB_PATH = original_path

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

    def test_yfinance_fetches_split_and_dividend_adjusted_ohlcv(self):
        class FakeYFinance:
            kwargs = None

            def download(self, _ticker, **kwargs):
                self.kwargs = kwargs
                return pd.DataFrame({"Close": [10.0]})

        source = YFinanceSource()
        source._yf = FakeYFinance()

        result = source.fetch_ohlcv("ACME", "2025-01-01", "2025-02-01")

        self.assertIsNotNone(result)
        self.assertTrue(source._yf.kwargs["auto_adjust"])

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
        self.assertEqual(main.app.version, "0.1.6")

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

            def raise_for_status(self):
                pass

        class FakeSession:
            urls = []

            def get(self, _url, timeout):
                self.urls.append(_url)
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
        self.assertTrue(any("news.google.com/rss/search" in url for url in FakeSession.urls))

    def test_yahoo_finance_news_source_maps_search_results(self):
        class FakeSearch:
            def __init__(self, _query, **_kwargs):
                self.news = [
                    {
                        "title": "Markets move",
                        "publisher": "Example News",
                        "link": "https://example.test/markets",
                        "providerPublishTime": 1735776000,
                    }
                ]

        with patch("yfinance.Search", FakeSearch):
            articles = YahooFinanceNewsSource().search("markets", limit=1)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source"], "Example News")
        self.assertEqual(articles[0]["title"], "Markets move")
        self.assertTrue(articles[0]["published"].startswith("2025-01-02"))

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
                "YahooFinanceNewsSource",
                return_value=FakeNewsSource(),
            ):
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

    def test_migrates_existing_prediction_table_with_new_forecast_metadata(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "old-schema.db"
                with sqlite3.connect(connection.DB_PATH) as conn:
                    conn.execute(
                        """CREATE TABLE predictions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            prediction_date TEXT NOT NULL,
                            ticker TEXT NOT NULL,
                            horizon TEXT NOT NULL,
                            predicted_price REAL NOT NULL DEFAULT 0,
                            low REAL NOT NULL DEFAULT 0,
                            high REAL NOT NULL DEFAULT 0,
                            confidence_interval REAL NOT NULL DEFAULT 0.95,
                            sentiment_score REAL NOT NULL DEFAULT 0,
                            key_assumptions TEXT NOT NULL DEFAULT '',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )"""
                    )
                    conn.execute(
                        "INSERT INTO predictions (prediction_date, ticker, horizon, predicted_price) "
                        "VALUES (?, ?, ?, ?)",
                        ("2025-01-01", "ACME", "1d", 100.0),
                    )

                connection.initialize_database()

                columns = {
                    row["name"]
                    for row in connection.fetch_all("PRAGMA table_info(predictions)")
                }
                legacy = connection.fetch_one(
                    "SELECT model_version, interval_coverage, interval_method FROM predictions"
                )
                self.assertTrue(
                    {
                        "model_version",
                        "interval_coverage",
                        "interval_method",
                        "context_snapshot_id",
                    } <= columns
                )
                self.assertEqual(legacy["model_version"], "legacy")
                self.assertEqual(legacy["interval_method"], "legacy")
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
                    "SELECT predicted_price, interval_coverage, interval_method, model_version "
                    "FROM predictions WHERE ticker = ?",
                    ("ACME",),
                )

                self.assertEqual(inserted, 1)
                self.assertEqual(rows[0]["predicted_price"], 42.75)
                self.assertEqual(rows[0]["interval_coverage"], 0.9)
                self.assertEqual(rows[0]["model_version"], "legacy")
                self.assertEqual(
                    forecast_service._load_calibration_context("ACME", "general"),
                    {"horizons": {}},
                )
        finally:
            connection.DB_PATH = original_path

    def test_calibration_uses_signed_horizon_residuals_from_current_model_only(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "forecast-calibration.db"
                connection.initialize_database()
                connection.execute(
                    "INSERT INTO assets (ticker, asset_type, name, date_added) VALUES (?, ?, ?, ?)",
                    ("ACME", "stock", "Example", "2025-01-01"),
                )
                forecast_service.save_prediction(
                    {
                        "ticker": "ACME",
                        "model_version": MODEL_VERSION,
                        "predictions": {
                            horizon: {
                                "prediction_date": "2025-01-02T00:00:00Z",
                                "predicted_price": 100.0,
                                "interval_coverage": 0.9,
                                "interval_method": "test",
                                "low": 90.0,
                                "high": 110.0,
                            }
                            for horizon in ("1d", "7d")
                        },
                    }
                )
                current = connection.fetch_all(
                    "SELECT id, horizon FROM predictions WHERE model_version = ?",
                    (MODEL_VERSION,),
                )
                for prediction in current:
                    actual = 90.0 if prediction["horizon"] == "1d" else 110.0
                    connection.execute(
                        "INSERT INTO error_audits "
                        "(prediction_id, audit_date, actual_close, absolute_error, percentage_error, directional_correct) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (prediction["id"], "2025-01-03", actual, 10.0, 10.0, 0),
                    )

                legacy_id = connection.execute(
                    "INSERT INTO predictions "
                    "(ticker, horizon, prediction_date, predicted_price, model_version) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("ACME", "1d", "2025-01-02T00:00:00Z", 50.0, "legacy"),
                )
                connection.execute(
                    "INSERT INTO error_audits "
                    "(prediction_id, audit_date, actual_close, absolute_error, percentage_error, directional_correct) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (legacy_id, "2025-01-03", 100.0, 50.0, 50.0, 1),
                )

                context = forecast_service._load_calibration_context("ACME", "general")

                self.assertAlmostEqual(context["horizons"]["1d"]["residuals"][0], -0.1)
                self.assertAlmostEqual(context["horizons"]["7d"]["residuals"][0], 0.1)
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

                with patch.object(
                    routes,
                    "_search_news_articles",
                    return_value=[
                        {
                            "title": "Company update",
                            "url": "https://example.test/news",
                            "source": "Example",
                            "published": "2025-01-02",
                        }
                    ],
                ):
                    with patch.object(
                        routes.market_context_service,
                        "fetch_market_context",
                        return_value={
                            "ticker": "ACME",
                            "source": "Yahoo Finance",
                            "captured_at": "2025-01-26T00:00:00Z",
                            "fundamentals": {"sector": "Technology"},
                            "upcoming_events": [],
                            "warnings": [],
                        },
                    ):
                        result = routes.generate_forecast({"ticker": "ACME"})

                self.assertEqual(len(result["predictions"]), 9)
                self.assertEqual(result["news_context"][0]["title"], "Company update")
                self.assertIsNotNone(result["context_snapshot_id"])
                self.assertEqual(
                    connection.fetch_one("SELECT COUNT(*) AS count FROM predictions")["count"],
                    9,
                )
                self.assertEqual(
                    connection.fetch_one(
                        "SELECT COUNT(*) AS count FROM market_context_snapshots"
                    )["count"],
                    1,
                )
        finally:
            connection.DB_PATH = original_path

    def test_daily_forecast_queries_all_stored_price_history(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "daily-forecast.db"
                connection.initialize_database()
                connection.execute(
                    "INSERT INTO assets (ticker, asset_type, name, date_added) VALUES (?, ?, ?, ?)",
                    ("ACME", "stock", "Example", "2025-01-01"),
                )
                connection.execute(
                    "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
                    ("ACME", "2025-01-02", 42.0),
                )
                original_fetch_all = routes.fetch_all
                queries = []

                def tracked_fetch_all(query, *args, **kwargs):
                    queries.append(query)
                    return original_fetch_all(query, *args, **kwargs)

                with patch.object(routes, "_fetch_and_store_price_history"):
                    with patch.object(routes, "_search_news_articles", return_value=[]):
                        with patch.object(
                            routes.market_context_service,
                            "fetch_market_context",
                            return_value={
                                "ticker": "ACME",
                                "source": "Yahoo Finance",
                                "captured_at": "2025-01-03T00:00:00Z",
                                "fundamentals": {},
                                "upcoming_events": [],
                                "warnings": [],
                            },
                        ):
                            with patch.object(
                                forecast_service,
                                "save_market_context_snapshot",
                                return_value=1,
                            ):
                                with patch.object(error_auditor, "audit_predictions", return_value={"audited": 0}):
                                    with patch.object(routes, "fetch_all", side_effect=tracked_fetch_all):
                                        with patch(
                                            "stock_predictor_server.core.prediction_engine.generate_forecast",
                                            return_value={
                                                "ticker": "ACME",
                                                "predictions": {},
                                                "market_context": {},
                                                "news_context": [],
                                            },
                                        ):
                                            with patch.object(forecast_service, "save_prediction"):
                                                routes.run_daily_forecast()

                price_queries = [
                    query for query in queries if "FROM price_history" in query
                ]
                self.assertEqual(len(price_queries), 1)
                self.assertNotIn("LIMIT", price_queries[0].upper())
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
                connection.execute(
                    "INSERT INTO catalyst_events (ticker, event_date, event_type, title) "
                    "VALUES (?, ?, ?, ?)",
                    ("ACME", "2025-01-02", "news", "Example event"),
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
                forecast_service.save_market_context_snapshot(
                    "ACME",
                    {
                        "ticker": "ACME",
                        "source": "Yahoo Finance",
                        "captured_at": "2025-01-02T00:00:00Z",
                        "fundamentals": {},
                        "upcoming_events": [],
                        "warnings": [],
                    },
                    [],
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

                for table in (
                    "assets",
                    "price_history",
                    "catalyst_events",
                    "predictions",
                    "error_audits",
                    "forecast_accuracy",
                    "market_context_snapshots",
                ):
                    count = connection.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"]
                    self.assertEqual(count, 0, table)
        finally:
            connection.DB_PATH = original_path

    def test_forecast_audit_uses_horizon_and_records_actual_deviation(self):
        original_path = connection.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                connection.DB_PATH = Path(directory) / "forecast-audit.db"
                connection.initialize_database()
                connection.execute(
                    "INSERT INTO assets (ticker, asset_type, name, date_added) VALUES (?, ?, ?, ?)",
                    ("ACME", "stock", "Example", "2025-01-01"),
                )
                connection.execute(
                    "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
                    ("ACME", "2025-01-01", 100.0),
                )
                connection.execute(
                    "INSERT INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
                    ("ACME", "2025-01-03", 108.0),
                )
                connection.execute(
                    "INSERT INTO predictions (ticker, horizon, prediction_date, predicted_price) "
                    "VALUES (?, ?, ?, ?)",
                    ("ACME", "1d", "2025-01-01T00:00:00Z", 110.0),
                )

                result = error_auditor.audit_predictions("ACME")
                audit = connection.fetch_one(
                    "SELECT audit_date, actual_close, percentage_error FROM error_audits"
                )

                self.assertEqual(result["audited"], 1)
                self.assertEqual(audit["audit_date"], "2025-01-03")
                self.assertEqual(audit["actual_close"], 108.0)
                self.assertEqual(audit["percentage_error"], round(2 / 108 * 100, 4))
        finally:
            connection.DB_PATH = original_path
