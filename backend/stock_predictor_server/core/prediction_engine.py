"""Multi-horizon price-only forecasts with horizon-specific statistical baselines.

Generates projections for 9 exact horizons: 1d, 7d, 1m, 6m, 1y, 3y, 5y, 10y, 20y.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from .context_signals import build_context_signals

logger = logging.getLogger(__name__)

# Exact forecast horizons (must match horizon enum)
HORIZONS = ["1d", "7d", "1m", "6m", "1y", "3y", "5y", "10y", "20y"]
MODEL_VERSION = "price-context-v1"
INTERVAL_COVERAGE = 0.9
MIN_CALIBRATION_SAMPLES = 20

# Days-per-period conversions
DAYS = {"1d": 1, "7d": 7, "1m": 30, "6m": 180, "1y": 365, "3y": 1095, "5y": 1825, "10y": 3650, "20y": 7300}


def generate_forecast(
    ticker: str,
    price_history: pd.DataFrame,
    news_context: list[dict[str, Any]],
    calibration_context: dict[str, Any],
    today: str,
    market_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Produce forecasts with bounded, sourced context overlays."""
    if price_history is None or len(price_history) < 20:
        logger.warning("Insufficient price history for %s (%d rows); using naive baseline",
                       ticker, len(price_history) if price_history is not None else 0)
        return _naive_forecast(
            ticker, today, price_history, news_context, market_context
        )

    df = price_history.copy()
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()
    else:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    recent = close.dropna()
    if recent.empty:
        return _naive_forecast(ticker, today, df, news_context, market_context)

    short_term = _statistical_short_term_forecast(close, recent)
    long_term = _statistical_long_term_forecast(close, recent)

    predictions = {}
    context_signals: dict[str, dict[str, Any]] = {}
    for h in HORIZONS:
        days = DAYS[h]
        stat_proj = _statistical_project(close, days)
        signals = build_context_signals(
            news_context,
            market_context,
            days,
            today,
        )
        context_signals[h] = signals

        if days <= 180:
            momentum_proj = _momentum_project(recent, days)
            blend = 0.5 * stat_proj + 0.5 * momentum_proj
            model_explanation = (
                "Short horizons blend the full-history daily return with a capped "
                "recent 20-session momentum estimate."
            )
        else:
            long_term_proj = _long_term_project(recent.iloc[-1], days, long_term)
            long_term_weight = float(np.interp(days, [181, DAYS["20y"]], [0.5, 0.85]))
            blend = (1 - long_term_weight) * stat_proj + long_term_weight * long_term_proj
            model_explanation = (
                f"Long horizons blend historical daily returns with a long-run annual "
                f"growth estimate of {long_term['cagr_20yr'] * 100:.1f}%, shrunk toward "
                f"a {long_term['baseline_cagr'] * 100:.1f}% nominal baseline, with the "
                "projection capped at -8% to +12% annualized."
            )

        if signals["news_adjustment_pct"]:
            blend *= 1 + signals["news_adjustment_pct"] / 100
        if signals["fundamental_annualized_adjustment_pct"]:
            years = days / 365.25
            latest_price = float(recent.iloc[-1])
            base_growth = (blend / latest_price) ** (1 / years) - 1
            adjusted_growth = float(
                np.clip(
                    base_growth
                    + signals["fundamental_annualized_adjustment_pct"] / 100,
                    -0.08,
                    0.12,
                )
            )
            blend = latest_price * (1 + adjusted_growth) ** years

        horizon_calibration = calibration_context.get("horizons", {}).get(h, {})
        residuals = horizon_calibration.get("residuals", [])
        if len(residuals) >= MIN_CALIBRATION_SAMPLES:
            median_residual = float(np.median(residuals))
            shrinkage = len(residuals) / (len(residuals) + MIN_CALIBRATION_SAMPLES)
            correction = float(np.clip(median_residual * shrinkage, -0.1, 0.1))
            blend *= 1 + correction

        if days > 180:
            years = days / 365.25
            latest_price = float(recent.iloc[-1])
            blend = float(
                np.clip(
                    blend,
                    latest_price * (1 - 0.08) ** years,
                    latest_price * (1 + 0.12) ** years,
                )
            )

        low, high, interval_method, interval_sample_size = _prediction_interval(
            recent,
            blend,
            days,
            residuals,
        )
        event_multiplier = signals["event_risk_multiplier"]
        if event_multiplier > 1:
            lower_distance = max(0.0, np.log(blend / max(low, 0.01)))
            upper_distance = max(0.0, np.log(max(high, blend) / blend))
            low = max(0.01, blend * np.exp(-lower_distance * event_multiplier))
            high = blend * np.exp(upper_distance * event_multiplier)
            interval_method += "; widened for scheduled-event risk"
        predictions[h] = {
            "predicted_price": round(max(blend, 0.01), 2),
            "confidence_interval": INTERVAL_COVERAGE,
            "interval_coverage": INTERVAL_COVERAGE,
            "low": round(low, 2),
            "high": round(high, 2),
            "interval_method": interval_method,
            "interval_sample_size": interval_sample_size,
            "sentiment_score": short_term.get("sentiment_score", 0.0),
            "horizon": h,
            "prediction_date": today,
            "key_assumptions": _build_key_assumptions(
                recent,
                blend,
                days,
                len(residuals) >= MIN_CALIBRATION_SAMPLES,
                model_explanation,
                signals,
            ),
        }

    return {
        "ticker": ticker,
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "predictions": predictions,
        "news_context": _normalize_news_context(news_context),
        "market_context": market_context or _empty_market_context(ticker, today),
        "context_signals": context_signals,
        "confidence_band": {
            "1d": predictions["1d"]["low"],
            "7d": predictions["7d"]["low"],
            "1m": predictions["1m"]["low"],
            "6m": predictions["6m"]["low"],
            "1y": predictions["1y"]["low"],
        },
        "calibration_context_applied": any(
            len(context.get("residuals", [])) >= MIN_CALIBRATION_SAMPLES
            for context in calibration_context.get("horizons", {}).values()
        ),
    }


def _naive_forecast(
    ticker: str,
    today: str,
    price_history: Optional[pd.DataFrame] = None,
    news_context: Optional[list[dict[str, Any]]] = None,
    market_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    latest_price = 100.0
    if price_history is not None and "close" in price_history:
        close = pd.to_numeric(price_history["close"], errors="coerce").dropna()
        if not close.empty and np.isfinite(close.iloc[-1]) and close.iloc[-1] > 0:
            latest_price = float(close.iloc[-1])

    return {
        "ticker": ticker,
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "predictions": {h: {"predicted_price": latest_price, "confidence_interval": INTERVAL_COVERAGE,
                            "interval_coverage": INTERVAL_COVERAGE,
                            "low": latest_price, "high": latest_price,
                            "interval_method": "unavailable: insufficient price history",
                            "interval_sample_size": 0,
                            "sentiment_score": 0.0, "horizon": h, "prediction_date": today,
                            "key_assumptions": "Insufficient historical data; using flat baseline."}
                        for h in HORIZONS},
        "news_context": _normalize_news_context(news_context or []),
        "market_context": market_context or _empty_market_context(ticker, today),
        "context_signals": {
            horizon: {
                "news_sentiment_score": 0.0,
                "news_articles_used": 0,
                "news_adjustment_pct": 0.0,
                "fundamental_score": None,
                "fundamental_metrics_used": 0,
                "fundamental_annualized_adjustment_pct": 0.0,
                "event_risk_multiplier": 1.0,
                "relevant_events": [],
            }
            for horizon in HORIZONS
        },
        "confidence_band": {},
        "calibration_context_applied": False,
    }


def _empty_market_context(ticker: str, today: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "source": "unavailable",
        "captured_at": today,
        "fundamentals": {},
        "upcoming_events": [],
        "warnings": ["Market context was not provided"],
    }


def _normalize_news_context(news_context: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized = []
    for article in news_context:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        if not title or not url.startswith(("https://", "http://")):
            continue
        normalized.append(
            {
                "title": title,
                "summary": str(article.get("summary") or "").strip()[:2000],
                "url": url,
                "source": str(article.get("source") or "News"),
                "published": str(article.get("published") or ""),
            }
        )
    return normalized[:5]


def _prediction_interval(
    recent: pd.Series,
    projected_price: float,
    days: int,
    residuals: list[float],
) -> tuple[float, float, str, int]:
    if len(residuals) >= MIN_CALIBRATION_SAMPLES:
        residual_array = np.asarray(residuals, dtype=float)
        median_residual = float(np.median(residual_array))
        low_residual, high_residual = np.quantile(residual_array, [0.05, 0.95])
        low = projected_price * (1 + float(low_residual) - median_residual)
        high = projected_price * (1 + float(high_residual) - median_residual)
        return (
            max(float(low), 0.01),
            max(float(high), float(low), 0.01),
            "historical 90% residual interval",
            len(residuals),
        )

    returns = np.log(recent / recent.shift(1)).dropna().tail(252)
    daily_volatility = float(returns.std()) if len(returns) > 1 else 0.0
    trading_days = max(days * 252 / 365.25, 1)
    log_spread = min(50.0, 1.6448536269514722 * daily_volatility * np.sqrt(trading_days))
    low = projected_price * np.exp(-log_spread)
    high = projected_price * np.exp(log_spread)
    return (
        max(float(low), 0.01),
        float(high),
        "historical-volatility estimate; not backtest-calibrated",
        len(returns),
    )


def _build_key_assumptions(
    recent: pd.Series,
    projected_price: float,
    days: int,
    calibration_applied: bool,
    model_explanation: str,
    context_signals: dict[str, Any],
) -> str:
    latest_price = float(recent.iloc[-1])
    projected_change = (projected_price / latest_price - 1) * 100
    lookback = min(20, len(recent) - 1)
    if lookback > 0:
        recent_trend = (float(recent.iloc[-1]) / float(recent.iloc[-1 - lookback]) - 1) * 100
        trend_text = f"The latest {lookback}-session price trend was {recent_trend:+.1f}%."
    else:
        trend_text = "There is not enough history to calculate a recent price trend."

    returns = np.log(recent / recent.shift(1)).dropna()
    annualized_volatility = float(returns.std() * np.sqrt(252) * 100) if len(returns) > 1 else 0.0
    direction = "rise" if projected_change > 0 else "fall" if projected_change < 0 else "remain flat"
    assumptions = (
        f"Latest close was ${latest_price:.2f}. Projects a {abs(projected_change):.1f}% "
        f"{direction} over about {days} calendar days. "
        f"{trend_text} Historical annualized volatility was {annualized_volatility:.1f}%. "
        f"{model_explanation} "
        "Recent headlines can nudge short-horizon estimates by at most 0.5%; "
        "reported company fundamentals can adjust long-run growth by at most 1 percentage point annually. "
        "Known scheduled events widen the range without predicting their outcome. "
        "These context overlays are bounded heuristics, not validated causal effects."
    )
    if context_signals["news_articles_used"]:
        assumptions += (
            f" Recent headline sentiment was {context_signals['news_sentiment_score']:+.2f} "
            f"across {context_signals['news_articles_used']} dated article(s)."
        )
    if context_signals["fundamental_score"] is not None:
        assumptions += (
            f" The fundamentals score was {context_signals['fundamental_score']:+.2f} "
            f"from {context_signals['fundamental_metrics_used']} reported metric(s)."
        )
    elif context_signals["fundamental_metrics_used"]:
        assumptions += (
            " Some company metrics were available, but not enough to compute a "
            "fundamentals signal."
        )
    if context_signals["relevant_events"]:
        event_labels = ", ".join(
            f"{event['label']} on {event['date']}"
            for event in context_signals["relevant_events"]
        )
        assumptions += f" Upcoming scheduled events: {event_labels}."
    if (
        not context_signals["news_articles_used"]
        and context_signals["fundamental_score"] is None
    ):
        assumptions += " No usable news or company fundamentals were available; this is the price-history baseline."
    if calibration_applied:
        assumptions += " Recent forecast-error calibration was applied."
    return assumptions


def _statistical_short_term_forecast(close: pd.Series, recent: pd.Series) -> dict[str, Any]:
    if recent.empty or len(recent) < 10:
        return {"sentiment_score": 0.0, "momentum": 0.0, "volatility": 0.0}

    rets = np.log(recent / recent.shift(1)).dropna()
    lookback_5d = min(5, len(recent) - 1)
    lookback_20d = min(20, len(recent) - 1)
    mom_5d = recent.iloc[-1] / recent.iloc[-1 - lookback_5d] - 1
    mom_20d = recent.iloc[-1] / recent.iloc[-1 - lookback_20d] - 1

    sentiment = 0.0
    if mom_5d > 0.02:
        sentiment = 0.6
    elif mom_5d < -0.02:
        sentiment = -0.6

    return {
        "sentiment_score": round(sentiment, 4),
        "momentum_5d": round(mom_5d, 6),
        "momentum_20d": round(mom_20d, 6),
        "volatility": round(float(rets.std()), 6),
        "price_now": float(recent.iloc[-1]),
    }


def _statistical_long_term_forecast(close: pd.Series, recent: pd.Series) -> dict[str, Any]:
    if len(close) < 20:
        return {"cagr_20yr": 0.065, "baseline_cagr": 0.065, "observed_cagr": 0.0}

    years = (close.index[-1] - close.index[0]).days / 365.25
    if years <= 0 or close.iloc[0] <= 0 or close.iloc[-1] <= 0:
        return {"cagr_20yr": 0.065, "baseline_cagr": 0.065, "observed_cagr": 0.0}
    cagr = (close.iloc[-1] / close.iloc[0]) ** (1 / years) - 1
    history_weight = min(0.5, years / (years + 10))
    baseline_cagr = 0.065
    cagr_20yr = float(np.clip(cagr * history_weight + baseline_cagr * (1 - history_weight), -0.08, 0.12))

    return {
        "cagr_approx": round(cagr, 4),
        "cagr_20yr": round(cagr_20yr, 4),
        "baseline_cagr": baseline_cagr,
        "observed_cagr": round(cagr, 4),
        "years": years,
    }


def _momentum_project(recent: pd.Series, days: int) -> float:
    returns = np.log(recent / recent.shift(1)).dropna()
    if returns.empty:
        return float(recent.iloc[-1])

    recent_drift = returns.tail(20).mean()
    historical_drift = returns.mean()
    daily_drift = float(np.clip(0.7 * recent_drift + 0.3 * historical_drift, -0.015, 0.015))
    trading_days = max(days * 252 / 365.25, 1)
    return float(recent.iloc[-1] * np.exp(daily_drift * trading_days))


def _long_term_project(latest_price: float, days: int, long_term: dict[str, Any]) -> float:
    years = days / 365.25
    return float(latest_price * (1 + long_term["cagr_20yr"]) ** years)


def _statistical_project(close: pd.Series, days: int) -> float:
    if len(close) < 5:
        return float(close.iloc[-1])
    rets = np.log(close / close.shift(1)).dropna()
    drift = rets.mean()
    last = close.iloc[-1]
    trading_days = max(days * 252 / 365.25, 1)
    proj = last * np.exp(drift * trading_days)
    return float(proj)
