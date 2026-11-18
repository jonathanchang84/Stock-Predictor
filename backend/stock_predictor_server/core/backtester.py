"""Leakage-safe walk-forward evaluation for the current forecast model."""

from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from .prediction_engine import DAYS, HORIZONS, MODEL_VERSION, generate_forecast


def walk_forward_backtest(
    ticker: str,
    price_history: pd.DataFrame,
    minimum_train_rows: int = 252,
    step_rows: int = 63,
) -> dict[str, Any]:
    """Evaluate forecasts using only data available at each historical forecast date."""
    data = price_history.copy()
    if not isinstance(data.index, pd.DatetimeIndex):
        data["date"] = pd.to_datetime(data["date"])
        data = data.set_index("date")
    data = data.sort_index()
    data = data.loc[~data.index.duplicated(keep="last")]
    close = pd.to_numeric(data["close"], errors="coerce").dropna()

    observations: dict[str, list[dict[str, float]]] = {horizon: [] for horizon in HORIZONS}
    if minimum_train_rows < 20 or step_rows < 1:
        raise ValueError("minimum_train_rows must be at least 20 and step_rows must be positive")

    dates = close.index
    for origin_index in range(minimum_train_rows - 1, len(close), step_rows):
        origin_date = dates[origin_index]
        origin_price = float(close.iloc[origin_index])
        history = data.loc[dates[: origin_index + 1]].copy()
        history["close"] = close.iloc[: origin_index + 1]
        forecast = generate_forecast(
            ticker,
            history,
            [],
            {},
            origin_date.strftime("%Y-%m-%dT00:00:00Z"),
        )

        for horizon in HORIZONS:
            target_date = origin_date + timedelta(days=DAYS[horizon])
            actual_index = int(dates.searchsorted(target_date, side="left"))
            if actual_index >= len(close):
                continue
            actual_date = dates[actual_index]
            if actual_date > target_date + timedelta(days=7):
                continue

            prediction = forecast["predictions"][horizon]
            predicted_price = float(prediction["predicted_price"])
            actual_price = float(close.iloc[actual_index])
            if actual_price <= 0 or origin_price <= 0:
                continue
            observations[horizon].append(
                {
                    "actual": actual_price,
                    "predicted": predicted_price,
                    "baseline": origin_price,
                    "low": float(prediction["low"]),
                    "high": float(prediction["high"]),
                }
            )

    horizon_results = {}
    for horizon, rows in observations.items():
        count = len(rows)
        if not count:
            horizon_results[horizon] = {
                "sample_size": 0,
                "model": None,
                "baseline": None,
            }
            continue

        actual = np.asarray([row["actual"] for row in rows])
        predicted = np.asarray([row["predicted"] for row in rows])
        baseline = np.asarray([row["baseline"] for row in rows])
        direction_target = actual >= baseline
        model_direction = predicted >= baseline

        horizon_results[horizon] = {
            "sample_size": count,
            "model": {
                "mae": float(np.mean(np.abs(predicted - actual))),
                "mape": float(np.mean(np.abs(predicted - actual) / actual) * 100),
                "directional_hit_rate": float(np.mean(model_direction == direction_target)),
                "interval_coverage": float(
                    np.mean(
                        [
                            row["low"] <= row["actual"] <= row["high"]
                            for row in rows
                        ]
                    )
                ),
            },
            "baseline": {
                "mae": float(np.mean(np.abs(baseline - actual))),
                "mape": float(np.mean(np.abs(baseline - actual) / actual) * 100),
            },
        }

    return {
        "ticker": ticker,
        "model_version": MODEL_VERSION,
        "as_of": dates[-1].strftime("%Y-%m-%d") if len(dates) else None,
        "methodology": (
            f"Walk-forward, {minimum_train_rows}-row initial history, "
            f"{step_rows}-row step, next available close within 7 calendar days. "
            "Compared with a flat last-close baseline; no transaction costs."
        ),
        "horizons": horizon_results,
    }
