"""Significant Movement Event detector: price swings > 2.5 rolling std dev."""

import pandas as pd
from typing import Any

# Config: how many standard deviations trigger an event.
SIGMA_THRESHOLD = 2.5
# Rolling window in days for volatility estimation (per event type / market).
DEFAULT_ROLLING_WINDOW = 60


def detect_significant_movements(
    df: pd.DataFrame,
    ticker: str,
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    sigma: float = SIGMA_THRESHOLD,
) -> list[dict[str, Any]]:
    """Detect log-return spikes beyond ``sigma`` standard deviations.

    Input ``df`` must have a DatetimeIndex and columns: open, high, low, close, volume.
    Returns a list of event dicts ready for the catalyst logger.
    """
    if df is None or df.empty:
        return []

    # Ensure chronological order.
    df = df.sort_index()

    # Compute log returns and rolling statistics on close price.
    close = df["close"]
    log_returns = np_log_close(close)

    rolling_mean = log_returns.rolling(window=rolling_window, min_periods=20).mean()
    rolling_std = log_returns.rolling(window=rolling_window, min_periods=20).std()

    z_scores = (log_returns - rolling_mean) / rolling_std

    # Identify single-day and multi-day events.
    events = []
    for idx, z in z_scores.items():
        if pd.isna(z):
            continue
        threshold = abs(z) >= sigma
        if not threshold:
            continue

        # Determine event magnitude in percentage terms.
        daily_pct = (close.loc[idx] / close.shift(1).loc[idx] - 1.0) * 100.0
        direction = "up" if z > 0 else "down"

        events.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "event_type": classify_event_type(direction, daily_pct),
                "daily_log_return": float(z),
                "daily_pct": float(daily_pct),
                "direction": direction,
                "rolling_mean": float(rolling_mean.loc[idx]) if not pd.isna(rolling_mean.loc[idx]) else None,
                "rolling_std": float(rolling_std.loc[idx]) if not pd.isna(rolling_std.loc[idx]) else None,
            }
        )

    return events


def classify_event_type(direction: str, daily_pct: float) -> str:
    """Return a coarse event type label based on magnitude."""
    if direction == "up":
        if daily_pct >= 10.0:
            return "catalyst"
        if daily_pct >= 5.0:
            return "sector"
        return "news"
    else:  # down
        if daily_pct <= -10.0:
            return "catalyst"
        if daily_pct <= -5.0:
            return "sector"
        return "news"


def np_log_close(series: pd.Series) -> pd.Series:
    """Log-returns helper avoiding numpy import in pure context."""
    import numpy as np
    return np.log(series / series.shift(1))
