"""Settings management routes."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..db.connection import execute, fetch_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings():
    rows = fetch_all("SELECT key, value, updated_at FROM app_settings ORDER BY key")
    return {r["key"]: r["value"] for r in rows}


@router.put("")
def update_settings(payload: dict):
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for key, value in payload.items():
        execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now), fetch=False,
        )
    return {"message": "Settings saved", "count": len(payload)}
