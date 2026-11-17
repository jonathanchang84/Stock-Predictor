"""Combines volatility spikes with news/events to create CatalystEvents."""

import logging
from datetime import datetime, timezone
from typing import Any

from ..db.connection import execute, fetch_all
from .volatility_detector import detect_significant_movements

logger = logging.getLogger(__name__)


def build_catalyst_events(ticker: str, price_df: dict[str, Any]) -> list[dict[str, Any]]:
    """Build catalyst events from detected price movements + news feed.

    ``price_df`` is a dict with keys: date, open, high, low, close, volume (list-like).
    Returns a list of event records ready for DB insertion.
    """
    if not price_df:
        logger.warning("No price data for %s; skipping catalyst detection", ticker)
        return []

    # Build DataFrame from dict
    import pandas as pd
    df = pd.DataFrame(price_df)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df = df.sort_index()

    # Drop rows with missing close
    df = df.dropna(subset=["close"])

    events = detect_significant_movements(df, ticker)

    # Classify and enrich each event (news cross-reference would go here).
    # For now, return raw detected events.
    enriched = []
    for ev in events:
        enriched.append(
            {
                "ticker": ticker,
                "event_date": ev["date"],
                "event_type": ev["event_type"],
                "title": f"{ticker} {ev['direction'].upper()} {abs(ev['daily_pct']):.2f}% move",
                "summary": f"{ev['direction']} {abs(ev['daily_pct']):.2f}% single-day move "
                           f"(z-score {ev['daily_log_return']:.2f}, "
                           f"rolling sigma {ev['rolling_std']:.4f})",
                "source": "volatility_detector",
                "confidence": None,
            }
        )

    return enriched


def save_catalyst_events(events: list[dict[str, Any]]) -> int:
    """Insert catalyst events into the database. Returns count inserted."""
    if not events:
        return 0

    params_list = []
    for ev in events:
        params_list.append(
            (
                ev["ticker"],
                ev["event_date"],
                ev["event_type"],
                ev["title"],
                ev["summary"],
                ev["source"],
                ev["confidence"] if ev["confidence"] is not None else 0.5,
            )
        )

    query = """
        INSERT OR REPLACE INTO catalyst_events
        (ticker, event_date, event_type, title, summary, source, confidence, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    params_list = [(p[0], p[1], p[2], p[3], p[4], p[5], p[6], now) for p in params_list]

    return execute(query, params_list, fetch=False)  # Actually returns rowcount
