"""Convert dated headlines, fundamentals, and known events into bounded signals."""

import math
import re
from datetime import date, datetime, timezone
from typing import Any

POSITIVE_TERMS = {
    "approved",
    "approval",
    "beat",
    "beats",
    "bullish",
    "expands",
    "expansion",
    "growth",
    "improves",
    "improved",
    "launch",
    "launched",
    "outperform",
    "outperforms",
    "profit",
    "profitable",
    "raises",
    "raised",
    "record",
    "strong",
    "surge",
    "surged",
    "upgrade",
    "upgraded",
    "wins",
}
NEGATIVE_TERMS = {
    "bankruptcy",
    "bearish",
    "breach",
    "cuts",
    "decline",
    "declining",
    "default",
    "delay",
    "delayed",
    "downgrade",
    "downgraded",
    "drops",
    "falls",
    "fraud",
    "investigation",
    "lawsuit",
    "loss",
    "losses",
    "miss",
    "misses",
    "missed",
    "probe",
    "recall",
    "recalled",
    "recession",
    "risk",
    "selloff",
    "weak",
    "warning",
}


def build_context_signals(
    news_context: list[dict[str, Any]],
    market_context: dict[str, Any] | None,
    horizon_days: int,
    as_of: str,
) -> dict[str, Any]:
    """Build per-horizon signals; all adjustments are intentionally bounded."""
    forecast_date = _parse_date(as_of) or datetime.now(timezone.utc).date()
    news_score, news_articles_used = _score_news(news_context, forecast_date)
    fundamentals = (market_context or {}).get("fundamentals", {})
    fundamental_score, fundamental_metrics_used = _score_fundamentals(
        fundamentals,
        (market_context or {}).get("asset_type"),
    )

    news_adjustment_pct = (
        news_score * 0.5 * math.exp(-max(horizon_days, 0) / 30)
        if horizon_days <= 180
        else 0.0
    )
    fundamental_adjustment_pct = (
        fundamental_score * min(fundamental_metrics_used / 4, 1.0)
        if fundamental_score is not None and horizon_days >= 365
        else 0.0
    )

    relevant_events = _events_within_horizon(
        (market_context or {}).get("upcoming_events", []),
        forecast_date,
        horizon_days,
    )
    event_risk_multiplier = 1.0
    if horizon_days <= 365:
        for event in relevant_events:
            event_date = _parse_date(event.get("date", ""))
            if event_date is None:
                continue
            days_until = (event_date - forecast_date).days
            if event.get("type") == "earnings":
                multiplier = 1.25 if days_until <= 14 else 1.15 if days_until <= 45 else 1.08
                event_risk_multiplier = max(event_risk_multiplier, multiplier)
            elif event.get("type") == "ex_dividend" and days_until <= 14:
                event_risk_multiplier = max(event_risk_multiplier, 1.05)

    return {
        "news_sentiment_score": round(news_score, 4),
        "news_articles_used": news_articles_used,
        "news_adjustment_pct": round(news_adjustment_pct, 4),
        "fundamental_score": (
            round(fundamental_score, 4) if fundamental_score is not None else None
        ),
        "fundamental_metrics_used": fundamental_metrics_used,
        "fundamental_annualized_adjustment_pct": round(
            fundamental_adjustment_pct, 4
        ),
        "event_risk_multiplier": event_risk_multiplier,
        "relevant_events": relevant_events,
    }


def _score_news(
    articles: list[dict[str, Any]],
    as_of: date,
) -> tuple[float, int]:
    weighted_polarity = 0.0
    weighted_terms = 0.0
    used_articles = 0
    seen_articles: set[str] = set()

    for article in articles:
        if not isinstance(article, dict):
            continue
        article_date = _parse_date(str(article.get("published") or ""))
        if article_date is None or article_date > as_of:
            continue
        age_days = (as_of - article_date).days
        if age_days > 7:
            continue

        title = str(article.get("title") or "").strip()
        summary = str(article.get("summary") or "").strip()
        identity = str(article.get("url") or f"{title}:{article_date}")
        if not title or identity in seen_articles:
            continue
        seen_articles.add(identity)

        words = re.findall(r"[a-z]+", f"{title} {summary}".casefold())
        positive = sum(word in POSITIVE_TERMS for word in words)
        negative = sum(word in NEGATIVE_TERMS for word in words)
        matched_terms = positive + negative
        if not matched_terms:
            continue

        recency_weight = math.exp(-age_days / 3)
        weighted_polarity += (positive - negative) * recency_weight
        weighted_terms += matched_terms * recency_weight
        used_articles += 1

    if weighted_terms == 0:
        return 0.0, used_articles

    confidence = min(used_articles / 3, 1.0)
    score = weighted_polarity / weighted_terms * confidence
    return max(-1.0, min(1.0, score)), used_articles


def _score_fundamentals(
    fundamentals: dict[str, Any],
    asset_type: str | None = None,
) -> tuple[float | None, int]:
    if not isinstance(fundamentals, dict):
        return None, 0
    quote_type = str(fundamentals.get("quote_type") or "").casefold()
    normalized_asset_type = (asset_type or "").casefold()
    if normalized_asset_type in {"etf", "mutual_fund", "index_fund"} or any(
        fund_type in quote_type for fund_type in ("etf", "fund", "index")
    ):
        return None, 0

    indicators: list[float] = []
    for key, scale in (
        ("revenue_growth", 0.25),
        ("earnings_growth", 0.25),
        ("profit_margin", 0.20),
        ("operating_margin", 0.20),
        ("return_on_equity", 0.25),
    ):
        value = _finite_number(fundamentals.get(key))
        if value is not None:
            indicators.append(_clamp(value / scale))

    debt_to_equity = _finite_number(fundamentals.get("debt_to_equity"))
    if debt_to_equity is not None:
        indicators.append(_clamp(1 - debt_to_equity / 150))

    if len(indicators) < 3:
        return None, len(indicators)
    return sum(indicators) / len(indicators), len(indicators)


def _events_within_horizon(
    events: list[dict[str, Any]],
    as_of: date,
    horizon_days: int,
) -> list[dict[str, str]]:
    relevant = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_date = _parse_date(str(event.get("date") or ""))
        if event_date is None:
            continue
        days_until = (event_date - as_of).days
        if 0 <= days_until <= min(horizon_days, 90):
            relevant.append(
                {
                    "type": str(event.get("type") or "event"),
                    "date": event_date.isoformat(),
                    "label": str(event.get("label") or "Scheduled event"),
                    "source": str(event.get("source") or "Unknown"),
                }
            )
    return sorted(relevant, key=lambda event: event["date"])


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            from dateutil.parser import parse

            return parse(value, fuzzy=False).date()
        except (ImportError, OverflowError, TypeError, ValueError):
            return None


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))
