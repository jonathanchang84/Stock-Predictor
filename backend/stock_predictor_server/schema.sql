-- Stock Predictor SQLite Schema
-- Designed for low-RAM usage: WAL mode, no heavy indexing, ON CONFLICT REPLACE for upserts

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- App settings: key-value store for API keys, last-run timestamps, app metadata
CREATE TABLE IF NOT EXISTS app_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Asset registry: portfolio holdings
CREATE TABLE IF NOT EXISTS assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT NOT NULL,
    asset_type    TEXT NOT NULL CHECK(asset_type IN ('stock', 'etf', 'mutual_fund', 'index_fund')),
    name          TEXT NOT NULL DEFAULT '',
    purchase_price REAL NOT NULL DEFAULT 0,
    quantity      REAL NOT NULL DEFAULT 0,
    date_added    TEXT NOT NULL,
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ticker)
);

-- Price history OHLCV: time-series data (indexed by ticker, date)
CREATE TABLE IF NOT EXISTS price_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker    TEXT NOT NULL,
    date      TEXT NOT NULL,
    open      REAL NOT NULL DEFAULT 0,
    high      REAL NOT NULL DEFAULT 0,
    low       REAL NOT NULL DEFAULT 0,
    close     REAL NOT NULL DEFAULT 0,
    volume    INTEGER NOT NULL DEFAULT 0,
    source    TEXT NOT NULL DEFAULT 'yfinance',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE,
    UNIQUE (ticker, date)
);

-- Catalyst events: detected movement spikes cross-referenced with news
CREATE TABLE IF NOT EXISTS catalyst_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    event_type  TEXT NOT NULL CHECK(event_type IN ('earnings', 'regulation', 'macro', 'sector', 'news', 'catalyst')),
    title       TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'unknown',
    confidence  REAL NOT NULL DEFAULT 0.5,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE
);

-- Prediction ledger: all generated forecasts
CREATE TABLE IF NOT EXISTS market_context_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT NOT NULL,
    captured_at  TEXT NOT NULL,
    context_json TEXT NOT NULL,
    FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE,
    UNIQUE (ticker, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_market_context_ticker_time
    ON market_context_snapshots(ticker, captured_at);

CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_date TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    horizon         TEXT NOT NULL CHECK(horizon IN ('1d', '7d', '1m', '6m', '1y', '3y', '5y', '10y', '20y')),
    predicted_price REAL NOT NULL DEFAULT 0,
    low             REAL NOT NULL DEFAULT 0,
    high            REAL NOT NULL DEFAULT 0,
    confidence_interval REAL NOT NULL DEFAULT 0.95,
    interval_coverage REAL NOT NULL DEFAULT 0.9,
    interval_method TEXT NOT NULL DEFAULT 'legacy',
    model_version   TEXT NOT NULL DEFAULT 'legacy',
    context_snapshot_id INTEGER REFERENCES market_context_snapshots(id) ON DELETE SET NULL,
    sentiment_score REAL NOT NULL DEFAULT 0,
    key_assumptions TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker) REFERENCES assets(ticker) ON DELETE CASCADE
);

-- Error audit log: audited predictions after target date has passed
CREATE TABLE IF NOT EXISTS error_audits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id   INTEGER NOT NULL,
    audit_date      TEXT NOT NULL,
    actual_close    REAL NOT NULL DEFAULT 0,
    absolute_error  REAL NOT NULL DEFAULT 0,
    percentage_error REAL NOT NULL DEFAULT 0,
    directional_correct INTEGER NOT NULL DEFAULT 0 CHECK(directional_correct IN (0, 1)),
    notes           TEXT NOT NULL DEFAULT '',
    audited_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id) ON DELETE CASCADE,
    UNIQUE (prediction_id)
);

-- Forecast accuracy aggregation: rolling performance per ticker/horizon
CREATE TABLE IF NOT EXISTS forecast_accuracy (
    ticker        TEXT NOT NULL,
    horizon       TEXT NOT NULL CHECK(horizon IN ('1d', '7d', '1m', '6m', '1y', '3y', '5y', '10y', '20y')),
    rolling_30d_mape REAL NOT NULL DEFAULT 0,
    directional_hit_rate REAL NOT NULL DEFAULT 0,
    mean_abs_error  REAL NOT NULL DEFAULT 0,
    sample_size     INTEGER NOT NULL DEFAULT 0,
    last_reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, horizon)
);

-- Indexes for query performance and low-RAM use
CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date ON price_history(ticker, date);
CREATE INDEX IF NOT EXISTS idx_catalyst_events_ticker_date ON catalyst_events(ticker, event_date);
CREATE INDEX IF NOT EXISTS idx_predictions_date_ticker ON predictions(prediction_date, ticker);
CREATE INDEX IF NOT EXISTS idx_error_audits_prediction_id ON error_audits(prediction_id);
CREATE INDEX IF NOT EXISTS idx_forecast_accuracy_ticker ON forecast_accuracy(ticker);
