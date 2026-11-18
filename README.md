# Stock Predictor

## Build

The Tauri app bundles the backend Python source and starts a compatible local API
on an available port from 8001-8010. This keeps it separate from an older
manually started server on port 8000. A Python 3 interpreter and the backend
dependencies must be installed on the Mac that runs the app:

```sh
python3 -m pip install -r backend/stock_predictor_server/requirements.txt
```

The app initializes a new SQLite database automatically. It reuses the database
in the source checkout when one exists; otherwise it stores data in the
operating system's application-data directory. Set `STOCK_PREDICTOR_DB` when
starting the backend manually to use a specific path.

Add assets by ticker or fund name and select the matching exchange listing.
Price history is fetched from the earliest date the market-data provider makes
available for that symbol; coverage varies by fund and exchange. Searching
"S&P 500" includes established ETF listings. Tracked assets can be edited or
deleted from the market overview; deleting an asset also removes its saved
price history and forecasts.

Price charts can be filtered from one day through maximum history. Forecasts
are plotted separately from actual closes; completed forecast audits show the
percentage deviation from the realized close. Forecast explanations describe
the recent price trend and historical volatility used by the model.

## Forecast inputs and limitations

Forecasts combine adjusted-close history with a small, bounded set of current
context signals:

- Dated news from the app's news providers is scored with a keyword heuristic.
  Only articles no more than seven days old are eligible; the resulting
  short-horizon price adjustment is capped at 0.5% in either direction and
  decays with forecast length.
- Yahoo Finance fundamentals are used only for company securities, not ETFs,
  mutual funds, or index funds. A company score requires at least three
  available metrics and can change long-horizon growth by at most one percentage
  point per year. Valuation fields, analyst targets, and fund characteristics
  are displayed as context but are not forecast inputs.
- Upcoming earnings and ex-dividend dates can widen the forecast interval but
  never determine its direction. These are company-calendar events, not a
  comprehensive calendar of macroeconomic or geopolitical events.

Current provider data is fetched automatically and cached for up to one hour;
provider gaps or errors are surfaced in the forecast context. Exact context
snapshots used for forecasts are stored locally. Walk-forward backtests only
reuse snapshots captured before each historical forecast date, and only while
they are at most 90 days old. News is independently limited to its seven-day
window. Historical fundamentals and event calendars are not backfilled, so
older backtests will usually have fewer context-enabled samples.

These overlays are transparent heuristics, not a trained news model or evidence
that news or fundamentals cause the predicted movement. Event outcomes and
unannounced future events cannot be known in advance. Forecast ranges are
estimates; their nominal 90% target is not a guarantee and should be assessed
against the app's walk-forward backtest. This application is informational and
does not provide investment advice.

```sh
npm ci
npm run tauri:build
```

The macOS application bundle is created under `src-tauri/target/release/bundle/macos/`.

## Publish a macOS release

Push a version tag such as `v0.1.0`. GitHub Actions builds the application and
publishes a `Stock-Predictor-macos.zip` asset to a GitHub Release for that tag.

