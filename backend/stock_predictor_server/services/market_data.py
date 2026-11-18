import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
import pandas as pd

logger = logging.getLogger(__name__)
SOURCE_PRIORITY = ["yfinance", "alpha_vantage", "finnhub"]


class DataFetchError(Exception):
    """Raised when all data sources fail for a given ticker."""


class DataSource(ABC):
    @abstractmethod
    def fetch_ohlcv(self, ticker: str, start: str, end: str, interval: str = "1d") -> Optional[pd.DataFrame]:
        ...

    @abstractmethod
    def fetch_quote(self, ticker: str) -> Optional[dict[str, Any]]:
        ...


class YFinanceSource(DataSource):
    def __init__(self):
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError as e:
            logger.warning("yfinance not installed: %s", e)
            self._yf = None

    def fetch_ohlcv(self, ticker: str, start: str, end: str, interval: str = "1d") -> Optional[pd.DataFrame]:
        if self._yf is None:
            return None
        try:
            if hasattr(self._yf, "download"):
                data = self._yf.download(
                    ticker,
                    start=start,
                    end=end,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
            else:
                data = self._yf.Ticker(ticker).history(
                    start=start,
                    end=end,
                    interval=interval,
                    auto_adjust=True,
                )
            if data is not None and not data.empty:
                return data
        except Exception as e:
            logger.warning("yfinance failed for %s: %s", ticker, e)
        return None

    def fetch_quote(self, ticker: str) -> Optional[dict[str, Any]]:
        if self._yf is None:
            return None
        try:
            info = self._yf.Ticker(ticker).info
            if info:
                return info
        except Exception as e:
            logger.warning("yfinance info failed for %s: %s", ticker, e)
        return None

class DataFetcher:
    def __init__(self, sources: list[DataSource]):
        self.sources = sources

    def fetch_ohlcv(self, ticker: str, start: str, end: str, interval: str = "1d") -> Optional[pd.DataFrame]:
        for source in self.sources:
            try:
                df = source.fetch_ohlcv(ticker, start, end, interval)
                if df is not None and not df.empty:
                    logger.info("Fetched %s OHLCV from %s (%d rows)", ticker, source.__class__.__name__, len(df))
                    return df
            except Exception as e:
                logger.warning("Source %s failed for %s: %s", source.__class__.__name__, ticker, e)
        raise DataFetchError(f"All data sources failed for {ticker}")

    def fetch_quote(self, ticker: str) -> Optional[dict[str, Any]]:
        for source in self.sources:
            try:
                quote = source.fetch_quote(ticker)
                if quote:
                    return quote
            except Exception as e:
                logger.warning("Quote source %s failed for %s: %s", source.__class__.__name__, ticker, e)
        return None


class AlphaVantageSource(DataSource):
    def __init__(self, api_key: str, base_url: str = "https://www.alphavantage.co/query"):
        self.api_key = api_key
        self.base_url = base_url
        self._session = None
        try:
            import requests
            self._session = requests.Session()
        except ImportError:
            self._session = None

    def _get(self, params: dict) -> Optional[dict]:
        if self._session is None:
            return None
        params = dict(params)
        params["apikey"] = self.api_key
        try:
            resp = self._session.get(self.base_url, params=params, timeout=15)
            return resp.json()
        except Exception as e:
            logger.warning("Alpha Vantage error: %s", e)
            return None

    def fetch_ohlcv(self, ticker: str, start: str, end: str, interval: str = "1d") -> Optional[pd.DataFrame]:
        resp = self._get({"function": "TIME_SERIES_DAILY", "symbol": ticker, "outputsize": "full"})
        if not resp or "Time Series (Daily)" not in resp:
            return None
        ts = resp["Time Series (Daily)"]
        data = {
            "date": list(ts.keys()),
            "open": [float(v["1. open"]) for v in ts.values()],
            "high": [float(v["2. high"]) for v in ts.values()],
            "low": [float(v["3. low"]) for v in ts.values()],
            "close": [float(v["4. close"]) for v in ts.values()],
            "volume": [int(v["5. volume"]) for v in ts.values()],
        }
        df = pd.DataFrame(data).set_index("date")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        if start and end:
            mask = (df.index >= start) & (df.index <= end)
            df = df[mask]
        return df if not df.empty else None

    def fetch_quote(self, ticker: str) -> Optional[dict[str, Any]]:
        resp = self._get({"function": "GLOBAL_QUOTE", "symbol": ticker})
        if not resp or "Global Quote" not in resp:
            return None
        return resp["Global Quote"]


class FinnhubSource(DataSource):
    def __init__(self, api_key: str, base_url: str = "https://finnhub.io/api/v1"):
        self.api_key = api_key

class RSSSource(DataSource):
    def __init__(self, feeds: Optional[list[str]] = None):
        self.feeds = feeds or self._default_feeds()
        self._session = None
        try:
            import requests
            self._session = requests.Session()
        except ImportError:
            self._session = None
        try:
            import feedparser
            self._feedparser = feedparser
        except ImportError:
            self._feedparser = None

    def _default_feeds(self) -> list[str]:
        return [
            "https://finance.yahoo.com/rss/news",
            "https://www.reuters.com/feeds/news/markets.rss",
            "https://www.marketwatch.com/rss/?OutputType=atom",
        ]

    def fetch_ohlcv(self, ticker: str, start: str, end: str, interval: str = "1d") -> Optional[pd.DataFrame]:
        return None

    def fetch_quote(self, ticker: str) -> Optional[dict[str, Any]]:
        return None

        self.base_url = base_url
        self._session = None
        try:
            import requests
            self._session = requests.Session()
        except ImportError:
            self._session = None

    def _get(self, endpoint: str, params: dict) -> Optional[dict]:
        if self._session is None:
            return None
        params = dict(params)
        params["token"] = self.api_key
        try:
            resp = self._session.get(f"{self.base_url}/{endpoint}", params=params, timeout=15)
            return resp.json()
        except Exception as e:
            logger.warning("Finnhub error: %s", e)
            return None

    def fetch_quote(self, ticker: str) -> Optional[dict[str, Any]]:
        resp = self._get("stock/token", {"symbol": ticker})
        if not resp or "c" not in resp:
            resp = self._get("stock/metric", {"symbol": ticker, "metric": "price"})
        return resp if resp else None

    def fetch_ohlcv(self, ticker: str, start: str, end: str, interval: str = "1d") -> Optional[pd.DataFrame]:
        resp = self._get("stock/candle", {"symbol": ticker, "resolution": "D", "from": start, "to": end})
        if not resp or "s" not in resp or resp.get("s") != "ok":
            return None
        df = pd.DataFrame(
            {
                "open": resp.get("o", []),
                "high": resp.get("h", []),
                "low": resp.get("l", []),
                "close": resp.get("c", []),
                "volume": resp.get("v", []),
            },
            index=pd.to_datetime(resp.get("t", [])),
        )
        return df.sort_index() if not df.empty else None

