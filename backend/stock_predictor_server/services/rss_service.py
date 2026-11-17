"""RSS feed aggregator (zero-key fallback for news)."""

import logging
from typing import Optional

import feedparser

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    "https://finance.yahoo.com/rss/news",
    "https://www.reuters.com/feeds/news/markets.rss",
    "https://www.marketwatch.com/rss/?OutputType=atom",
]


def fetch_rss_feeds(feeds: Optional[list[str]] = None, query: Optional[str] = None,
                    limit: int = 20) -> list[dict]:
    """Parse RSS feeds and filter by query keyword."""
    feed_list = feeds or DEFAULT_FEEDS
    results = []

    for url in feed_list:
        try:
            feed = feedparser.parse(url)
            for entry in feed.get("entries", [])[: limit // len(feed_list) + 1]:
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
            logger.warning("RSS fetch error for %s: %s", url, e)
    return results
