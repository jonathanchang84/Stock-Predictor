"""FastAPI app factory with lifespan management."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..db.connection import initialize_database
from .routes import router as core_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Stock Predictor API",
    description="AI-powered stock and fund tracking, multi-horizon forecasting, event correlation, and self-learning error calibration.",
    version="0.1.6",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
    allow_headers=["*"],)

app.include_router(core_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "stock-predictor", "version": "0.1.6"}


from .settings_routes import router as settings_router
app.include_router(settings_router)
