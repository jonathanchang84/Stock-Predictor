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

```sh
npm ci
npm run tauri:build
```

The macOS application bundle is created under `src-tauri/target/release/bundle/macos/`.

## Publish a macOS release

Push a version tag such as `v0.1.0`. GitHub Actions builds the application and
publishes a `Stock-Predictor-macos.zip` asset to a GitHub Release for that tag.

