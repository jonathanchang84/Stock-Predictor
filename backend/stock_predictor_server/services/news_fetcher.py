"""News & global event data sources with fallback."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class NewsSource(ABC):
    """Abstract news data source."""

    @abstractmethod
    def search(self, query: str, from_date: Optional[str] = None, to_date: Optional[str] = None,
               limit: int = 20) -> list[dict[str, Any]]:
        """Return a list of news/headline dicts."""
        ...


class FinnhubNewsSource(NewsSource):
    """Finnhub free-tier news API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = None
        try:
            import requests
            self._session = requests.Session()
        except ImportError:
            self._session = None

    def search(self, query: str, from_date: Optional[str] = None, to_date: Optional[str] = None,
               limit: int = 20) -> list[dict[str, Any]]:
        if self._session is None:
            return []
        try:
            params = {"q": query, "token": self.api_key, "limit": limit}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            resp = self._session.get("https://finnhub.io/api/v1/company-news", params=params, timeout=15)
            data = resp.json()
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.warning("Finnhub news error: %s", e)
            return []


class MarketauxNewsSource(NewsSource):
    """Marketaux free-tier global news API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = None
        try:
            import requests
            self._session = requests.Session()
        except ImportError:
            self._session = None

    def search(self, query: str, from_date: Optional[str] = None, to_date: Optional[str] = None,
               limit: int = 20) -> list[dict[str, Any]]:
        if self._session is None:
            return []
        try:
            params = {"api_token": self.api_key, "q": query, "limit": limit}
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            resp = self._session.get("https://marketaux.com/api/v2/news/all", params=params, timeout=15)
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("results"), list):
                return data["results"]
            return []
        except Exception as e:
            logger.warning("Marketaux news error: %s", e)
            return []


class RSSNewsSource(NewsSource):
    """RSS feed aggregator (zero-key fallback)."""

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

    def search(self, query: str, from_date: Optional[str] = None, to_date: Optional[str] = None,
               limit: int = 20) -> list[dict[str, Any]]:
        if self._feedparser is None:
            logger.warning("feedparser not installed; RSS source unavailable")
            return []

        results = []
        try:
            for url in self.feeds:
                resp = self._session.get(url, timeout=10) if self._session else None
                if resp is None:
                    continue
                feed = self._feedparser.parse(resp.content.decode("utf-8", errors="ignore"))
                for entry in feed.get("entries", [])[: limit // len(self.feeds)]:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    summary = entry.get("summary", "") or entry.get("description", "")
                    published = entry.get("published", "")
                    if query and query.lower() not in title.lower():
                        continue
                    results.append(
                        {
                            "source": "rss_" + url.split("//")[-1].split("/")[0],
                            "title": title,
                            "url": link,
                            "summary": summary,
                            "published": published[:10] if published else "",
                        }
                    )
                    if len(results) >= limit:
                        return results
        except Exception as e:
            logger.warning("RSS search error: %s", e)

class NewsFetcher:
    """Composes news sources with priority."""

    def __init__(self, sources: list[NewsSource]):
        self.sources = sources

    def search(self, query: str, from_date: Optional[str] = None, to_date: Optional[str] = None,
               limit: int = 20) -> list[dict[str, Any]]:
        for source in self.sources:
            try:
                results = source.search(query, from_date, to_date, limit)
                if results:
                    logger.info("News search returned %d results from %s",
                                len(results), source.__class__.__name__)
                    return results
            except Exception as e:
                logger.warning("News source %s failed: %s", source.__class__.__name__, e)
        return []

        return results
