"""Google Gemini AI service for financial forecasting.

Uses the official Google Genai SDK to call Gemini models (Gemini 2.0 / 1.5).
Requires a GEMINI_API_KEY environment variable or settings entry.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Model names for different horizons
GEMINI_MODEL_MAP = {
    "1d": "gemini-2.0-flash",
    "7d": "gemini-2.0-flash",
    "1m": "gemini-2.0-flash",
    "6m": "gemini-2.0-flash",
    "1y": "gemini-1.5-pro",
    "3y": "gemini-1.5-pro",
    "5y": "gemini-1.5-pro",
    "10y": "gemini-1.5-pro",
    "20y": "gemini-1.5-pro",
}


def get_api_key() -> str | None:
    """Retrieve Gemini API key from environment or settings DB."""
    # Check environment variable first
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key

    # Try reading from SQLite settings
    try:
        from ..db.connection import fetch_one
        row = fetch_one("SELECT value FROM app_settings WHERE key = ?", ("gemini_api_key",))
        if row:
            return row["value"]
    except Exception:
        pass

    return None


def _build_llm_prompt(ticker: str, price_data: str, news_context: list[dict], calibration_context: str, horizon: str) -> str:
    """Build a prompt for a specific horizon."""
    prompt = f"""You are a financial forecasting expert.

Ticker: {ticker}
Horizon: {horizon}

Recent price data (last 10 days):
{price_data}

News context:
\"\"\"
{json.dumps(news_context, indent=2)[:2000]}
\"\"\"

{calibration_context}
"""

    return prompt


def call_gemini_forecast(ticker: str, price_data: str, news_context: list[dict],
                         calibration_context: str, horizon: str) -> dict[str, Any] | None:
    """Call Gemini API and get structured forecast for a single horizon."""
    api_key = get_api_key()
    if not api_key:
        logger.warning("No Gemini API key configured")
        return None

    try:
        # Try installing genai if not available
        try:
            import google.genai as genai
        except ImportError:
            import subprocess
            subprocess.run(["pip", "install", "google-genai"], check=True, capture_output=True)
            import google.genai as genai

        genai.configure(api_key=api_key)
        model_name = GEMINI_MODEL_MAP.get(horizon, "gemini-2.0-flash")
        model = genai.GenerativeModel(model_name)

        prompt = _build_llm_prompt(ticker, price_data, news_context, calibration_context, horizon)

        # Request structured JSON output
        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.3,
            },
        )

        response_text = response.text
        logger.info("Gemini response received for %s (%s)", ticker, horizon)

        # Parse structured JSON
        return json.loads(response_text) if response_text else None

    except Exception as e:
        logger.error("Gemini call failed for %s (%s): %s", ticker, horizon, e)
        return None


def call_gemini_forecast_batch(ticker: str, price_data: str, news_context: list[dict],
                               calibration_context: str) -> dict[str, dict[str, Any]]:
    """Call Gemini to get all 9 horizons in a single batch."""
    api_key = get_api_key()
    if not api_key:
        logger.warning("No Gemini API key configured")
        return {}

    try:
        try:
            import google.genai as genai
        except ImportError:
            import subprocess
            subprocess.run(["pip", "install", "google-genai"], check=True, capture_output=True)
            import google.genai as genai

        genai.configure(api_key=api_key)
        model_name = "gemini-2.0-flash"
        model = genai.GenerativeModel(model_name)

        # Build prompt requesting all 9 horizons
        prompt = f"""You are a financial forecasting expert.

Ticker: {ticker}

Recent price data (last 30 days):
{price_data}

News context:
\"\"\"
{json.dumps(news_context, indent=2)[:2000]}
\"\"\"

{calibration_context}

Generate predictions for ALL 9 horizons:
1 day (1d), 7 days (7d), 1 month (1m), 6 months (6m), 1 year (1y), 3 years (3y), 5 years (5y), 10 years (10y), 20 years (20y).

Output MUST be a valid JSON array with 9 objects. Each object:
{{
  "horizon": "<1d|7d|1m|6m|1y|3y|5y|10y|20y>",
  "predicted_price": <number>,
  "low": <number>,
  "high": <number>,
  "confidence_interval": <number e.g. 0.95>,
  "sentiment_score": <number between -1 and 1>,
  "key_assumptions": "<concise bullet points citing specific world events>"
}}

Strictly output ONLY the JSON array, no markdown or explanation.
"""

        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.3,
            },
        )

        response_text = response.text
        logger.info("Gemini batch response received for %s", ticker)

        # Parse JSON array
        data = json.loads(response_text) if response_text else []

        # Convert to dict by horizon
        result = {}
        for item in data:
            h = item.get("horizon", "unknown")
            result[h] = item

        return result

    except Exception as e:
        logger.error("Gemini batch call failed for %s: %s", ticker, e)
        return {}
