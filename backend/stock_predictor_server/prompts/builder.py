"""Prompt builder with dynamic error-calibration injection.

All LLM prompts request strict structured JSON output containing:
predicted_price, low, high, sentiment_score, key_assumptions.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# System prompt base (prepended to every request)
SYSTEM_PROMPT = """You are an expert quantitative analyst and financial forecaster.
You provide structured, calibrated price projections across 9 horizons:
1 day, 7 days, 1 month, 6 months, 1 year, 3 years, 5 years, 10 years, 20 years.

Your output MUST be strict JSON with the following schema:
{
  "horizon": "1d"|"7d"|"1m"|"6m"|"1y"|"3y"|"5y"|"10y"|"20y",
  "predicted_price": <number>,
  "confidence_interval": <number>,
  "sentiment_score": <number in [-1, 1]>,
  "key_assumptions": "<concise bullets citing specific world events>"
}

Rules:
- Confidence intervals must reflect genuine uncertainty, not over-precision.
- Cite specific real-world events (earnings, macro data, geopolitical events, policy changes).
- Never claim certainty; always provide a delta/percentile range.
- If news is unclear or conflicting, state that explicitly.
"""

CALIBRATION_INJECT_TEMPLATE = """
<!-- DYNAMIC CALIBRATION CONTEXT (to be injected into system prompt) -->
Based on your last 30 days of error audits for {ticker} ({sector} sector):
- Average percentage error per horizon: {avg_errors}
- Directional hit rate: {directional_hit_rate}
Bias flag: {bias_flag}
Adjust your confidence intervals and temper your bullish/bearish bias accordingly.
<!-- END CALIBRATION CONTEXT -->
"""


def build_system_prompt(ticker: str, sector: str, calibration: dict[str, Any] = None) -> str:
    """Build the full system prompt, optionally injecting calibration context."""
    prompt = SYSTEM_PROMPT

    if calibration and any(k in calibration for k in ("avg_errors", "directional_hit_rate", "bias_flag")):
        cal_block = CALIBRATION_INJECT_TEMPLATE.format(
            ticker=ticker,
            sector=sector,
            avg_errors=calibration.get("avg_errors", "n/a"),
            directional_hit_rate=calibration.get("directional_hit_rate", "n/a"),
            bias_flag=calibration.get("bias_flag", "none"),
        )
        prompt = prompt.replace("Rules:", cal_block + "\nRules:")

    return prompt


def parse_structured_json(response_text: str, horizon: str) -> dict[str, Any] | None:
    """Extract a single horizon's structured JSON from LLM response.

    Handles code fences, markdown, and trailing text.
    """
    # Try to find JSON object in the response
    import re

    # Look for JSON object with our expected fields
    patterns = [
        r"\{.*\"predicted_price\".*\}",
        r"```json\s*(\{.*?\})\s*```",
        r"(\{.*?\})",
    ]

    for pattern in patterns:
        m = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
        if m:
            candidate = m.group(1) if m.lastindex else m.group(0)
            candidate = candidate.strip()
            # Validate required fields
            required = ["predicted_price", "confidence_interval", "sentiment_score", "key_assumptions"]
            if all(field in candidate for field in required):
                try:
                    data = json.loads(candidate)
                    # Ensure horizon matches
                    if data.get("horizon") == horizon:
                        return data
                    # If horizon missing, inject it
                    data["horizon"] = horizon
                    return data
                except json.JSONDecodeError:
                    continue

    logger.warning("Failed to parse structured JSON for horizon %s", horizon)
    return None


def parse_forecast_batch(response_text: str) -> dict[str, dict[str, Any]]:
    """Parse a batch of 9 horizon predictions from LLM response."""
    result = {}
    # Split by horizon block if possible. Fallback: expect JSON array of 9 objects.
    import re

    # Try to find all JSON objects with predicted_price
    objects = re.findall(r"\{[^}]*\"predicted_price\"[^}]*\}", response_text, re.DOTALL)
    for obj in objects:
        try:
            data = json.loads(obj)
            h = data.get("horizon", "unknown")
            result[h] = data
        except json.JSONDecodeError:
            continue

    if len(result) == 9:
        return result

    # Fallback: try to find a JSON array
    m = re.search(r"\[.*\]", response_text, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict) and "horizon" in item:
                        result[item["horizon"]] = item
        except json.JSONDecodeError:
            pass

    if len(result) < 9:
        logger.warning("Only parsed %d horizons from batch response", len(result))

    return result
