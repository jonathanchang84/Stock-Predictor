#!/usr/bin/env python3
"""Data ingestion script - fetches yfinance data and populates SQLite."""
import sqlite3
import yfinance as yf
from datetime import datetime, timedelta

DB = "backend/stock_predictor_server/data/stock_predictor.db"

# Add test assets
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("INSERT INTO assets (ticker, asset_type, name, purchase_price, quantity, date_added, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
    ("AAPL", "stock", "Apple Inc", 150.00, 10, "2026-01-01", "Test holding"))
cur.execute("INSERT INTO assets (ticker, asset_type, name, purchase_price, quantity, date_added, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
    ("TSLA", "stock", "Tesla Inc", 250.00, 5, "2026-01-01", "Test holding"))
conn.commit()
print("Added test assets AAPL and TSLA")

# Fetch price history for each asset
cur.execute("SELECT ticker, asset_type FROM assets")
assets = cur.fetchall()

for ticker, asset_type in assets:
    try:
        print(f"Fetching data for {ticker}...")
        # Fetch 2 years of data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)
        ticker_obj = yf.Ticker(ticker)
        hist = ticker_obj.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
        
        if hist.empty:
            print(f"  No data from yfinance for {ticker}")
            continue
        
        for _, row in hist.iterrows():
            date_str = row.name.strftime("%Y-%m-%d")
            cur.execute(
                "INSERT OR IGNORE INTO price_history (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ticker, date_str, float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), int(row["Volume"]))
            )
        conn.commit()
        print(f"  Fetched {len(hist)} days of data for {ticker}")
    except Exception as e:
        print(f"  Error fetching data for {ticker}: {e}")

conn.close()
print("Data ingestion complete!")