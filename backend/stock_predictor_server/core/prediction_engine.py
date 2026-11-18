"""Multi-horizon forecast generation with hybrid statistical + LLM approach.

Generates projections for 9 exact horizons: 1d, 7d, 1m, 6m, 1y, 3y, 5y, 10y, 20y.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Exact forecast horizons (must match horizon enum)
HORIZONS = ["1d", "7d", "1m", "6m", "1y", "3y", "5y", "10y", "20y"]

# Days-per-period conversions
DAYS = {"1d": 1, "7d": 7, "1m": 30, "6m": 180, "1y": 365, "3y": 1095, "5y": 1825, "10y": 3650, "20y": 7300}


def generate_forecast(
    ticker: str,
    price_history: pd.DataFrame,
    news_context: dict[str, Any],
    calibration_context: dict[str, Any],
    today: str,
) -> dict[str, Any]:
    """Produce forecasts for all 9 horizons, mixing statistical baselines with LLM."""
    if price_history is None or len(price_history) < 20:
        logger.warning("Insufficient price history for %s (%d rows); using naive baseline",
                       ticker, len(price_history) if price_history is not None else 0)
        return _naive_forecast(ticker, today, price_history)

    df = price_history.copy()
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()
    else:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    recent = close.dropna()
    if recent.empty:
        return _naive_forecast(ticker, today, df)

    short_term = _statistical_short_term_forecast(close, recent)
    long_term = _statistical_long_term_forecast(close, recent)

    predictions = {}
    for h in HORIZONS:
        days = DAYS[h]
        stat_proj = _statistical_project(close, days)

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

        if calibration_context:
            bias = calibration_context.get("bias_correction", 0.0)
            temper_bullish = calibration_context.get("temper_bullish", False)
            if temper_bullish:
                blend = blend * 0.85
            blend += bias

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

        predictions[h] = {
            "predicted_price": round(max(blend, 0.01), 2),
            "confidence_interval": round(blend * (1 - calibration_context.get("ci_width", 0.1)), 2)
                                   if calibration_context else round(blend * 0.9, 2),
            "sentiment_score": short_term.get("sentiment_score", 0.0),
            "horizon": h,
            "prediction_date": today,
            "key_assumptions": _build_key_assumptions(
                recent,
                blend,
                days,
                bool(calibration_context),
                model_explanation,
            ),
        }

    return {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "predictions": predictions,
        "confidence_band": {
            "1d": predictions["1d"]["confidence_interval"],
            "7d": predictions["7d"]["confidence_interval"],
            "1m": predictions["1m"]["confidence_interval"],
            "6m": predictions["6m"]["confidence_interval"],
            "1y": predictions["1y"]["confidence_interval"],
        },
        "calibration_context_applied": bool(calibration_context),
    }


def _naive_forecast(
    ticker: str,
    today: str,
    price_history: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    latest_price = 100.0
    if price_history is not None and "close" in price_history:
        close = pd.to_numeric(price_history["close"], errors="coerce").dropna()
        if not close.empty and np.isfinite(close.iloc[-1]) and close.iloc[-1] > 0:
            latest_price = float(close.iloc[-1])

    return {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "predictions": {h: {"predicted_price": latest_price, "confidence_interval": latest_price,
                            "sentiment_score": 0.0, "horizon": h, "prediction_date": today,
                            "key_assumptions": "Insufficient historical data; using flat baseline."}
                        for h in HORIZONS},
        "confidence_band": {},
        "calibration_context_applied": False,
    }


def _build_key_assumptions(
    recent: pd.Series,
    projected_price: float,
    days: int,
    calibration_applied: bool,
    model_explanation: str,
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
        f"{model_explanation} This estimate uses price history only; it does not model news, "
        "fundamentals, or future market events."
    )
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
