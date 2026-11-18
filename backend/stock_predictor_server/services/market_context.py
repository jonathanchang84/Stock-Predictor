"""Fetch current fundamentals and scheduled company events from Yahoo Finance."""

import copy
import logging
import math
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60 * 60
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def fetch_market_context(ticker: str, now: datetime | None = None) -> dict[str, Any]:
    """Return a short-lived cached snapshot, with explicit provider warnings."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    normalized_ticker = ticker.strip().upper()
    current_time = time.monotonic()

    with _cache_lock:
        cached = _cache.get(normalized_ticker)
        if cached and current_time - cached[0] < _CACHE_TTL_SECONDS:
            return copy.deepcopy(cached[1])

    context = _load_market_context(normalized_ticker, now)
    with _cache_lock:
        _cache[normalized_ticker] = (current_time, copy.deepcopy(context))
    return context


def _load_market_context(ticker: str, now: datetime) -> dict[str, Any]:
    context: dict[str, Any] = {
        "ticker": ticker,
        "source": "Yahoo Finance",
        "captured_at": now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "fundamentals": {},
        "upcoming_events": [],
        "warnings": [],
    }

    try:
        import yfinance as yf
    except ImportError as error:
        logger.warning("Yahoo Finance context unavailable for %s: %s", ticker, error)
        context["warnings"].append("yfinance is not installed")
        return context

    try:
        asset = yf.Ticker(ticker)
    except Exception as error:
        logger.warning("Unable to initialize Yahoo Finance context for %s: %s", ticker, error)
        context["warnings"].append(f"Yahoo Finance initialization failed: {error}")
        return context

    info: dict[str, Any] = {}
    try:
        info = asset.get_info() or {}
        context["fundamentals"] = _normalize_fundamentals(info)
        if not any(
            isinstance(value, (int, float))
            for value in context["fundamentals"].values()
        ):
            context["warnings"].append("Yahoo Finance returned no usable fundamental metrics")
    except Exception as error:
        logger.warning("Yahoo Finance fundamentals unavailable for %s: %s", ticker, error)
        context["warnings"].append(f"Fundamentals unavailable: {error}")

    try:
        calendar = asset.calendar
        context["upcoming_events"] = _normalize_calendar(calendar, info, now.date())
    except Exception as error:
        logger.warning("Yahoo Finance calendar unavailable for %s: %s", ticker, error)
        context["warnings"].append(f"Upcoming events unavailable: {error}")

    return context


def _normalize_fundamentals(info: dict[str, Any]) -> dict[str, Any]:
    text_fields = {
        "short_name": "shortName",
        "quote_type": "quoteType",
        "sector": "sector",
        "industry": "industry",
        "currency": "currency",
        "fund_family": "fundFamily",
        "category": "category",
    }
    number_fields = {
        "market_cap": "marketCap",
        "trailing_pe": "trailingPE",
        "forward_pe": "forwardPE",
        "price_to_book": "priceToBook",
        "revenue_growth": "revenueGrowth",
        "earnings_growth": "earningsGrowth",
        "profit_margin": "profitMargins",
        "operating_margin": "operatingMargins",
        "return_on_equity": "returnOnEquity",
        "debt_to_equity": "debtToEquity",
        "free_cash_flow": "freeCashflow",
        "dividend_yield": "dividendYield",
        "target_mean_price": "targetMeanPrice",
        "recommendation_mean": "recommendationMean",
        "expense_ratio": "annualReportExpenseRatio",
        "nav_price": "navPrice",
        "total_assets": "totalAssets",
        "ytd_return": "ytdReturn",
        "three_year_average_return": "threeYearAverageReturn",
        "five_year_average_return": "fiveYearAverageReturn",
        "ten_year_average_return": "tenYearAverageReturn",
    }

    fundamentals: dict[str, Any] = {}
    for output_key, input_key in text_fields.items():
        value = info.get(input_key)
        if isinstance(value, str) and value.strip():
            fundamentals[output_key] = value.strip()
    for output_key, input_key in number_fields.items():
        value = _finite_number(info.get(input_key))
        if value is not None:
            fundamentals[output_key] = value
    return fundamentals


def _normalize_calendar(calendar: Any, info: dict[str, Any], as_of: date) -> list[dict[str, str]]:
    event_candidates: list[tuple[str, Any]] = []
    if hasattr(calendar, "iterrows"):
        for label, row in calendar.iterrows():
            event_candidates.extend((str(label), value) for value in row.tolist())
    elif isinstance(calendar, dict):
        for label, value in calendar.items():
            values = value if isinstance(value, (list, tuple)) else [value]
            event_candidates.extend((str(label), item) for item in values)

    for key, label in (
        ("earningsTimestampStart", "Earnings date"),
        ("earningsTimestampEnd", "Earnings date"),
        ("exDividendDate", "Ex-dividend date"),
    ):
        if info.get(key) is not None:
            event_candidates.append((label, info[key]))

    last_event_day = as_of + timedelta(days=366)
    events: dict[tuple[str, str], dict[str, str]] = {}
    for label, raw_date in event_candidates:
        event_type = _event_type(label)
        if event_type is None:
            continue
        event_date = _parse_date(raw_date)
        if event_date is None or event_date < as_of or event_date > last_event_day:
            continue
        event = {
            "type": event_type,
            "date": event_date.isoformat(),
            "label": {
                "earnings": "Earnings",
                "ex_dividend": "Ex-dividend",
                "dividend": "Dividend",
            }[event_type],
            "source": "Yahoo Finance",
        }
        events[(event_type, event["date"])] = event
    return sorted(events.values(), key=lambda event: event["date"])


def _event_type(label: str) -> str | None:
    normalized = label.casefold()
    if "earn" in normalized:
        return "earnings"
    if "ex-dividend" in normalized or "ex dividend" in normalized:
        return "ex_dividend"
    if "dividend date" in normalized:
        return "dividend"
    return None


def _parse_date(value: Any) -> date | None:
    if str(value) in {"NaT", "nan", "NaN", "<NA>"}:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)) or value <= 0:
            return None
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
    if hasattr(value, "to_pydatetime"):
        try:
            converted = value.to_pydatetime()
            return converted.date() if isinstance(converted, datetime) else None
        except (OverflowError, TypeError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except ValueError:
            try:
                from dateutil.parser import parse

                return parse(value, fuzzy=False).date()
            except (ImportError, OverflowError, TypeError, ValueError):
                return None
    return None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
