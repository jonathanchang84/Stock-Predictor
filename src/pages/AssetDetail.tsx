import React from "react";
import { Link, useParams } from "react-router-dom";
import { useTauri } from "../tauri-backend/hooks";
import AssetPriceChart from "../components/AssetPriceChart";
import ForecastSummary from "../components/ForecastSummary";

const AssetDetail: React.FC = () => {
  const { ticker } = useParams<{ ticker: string }>();
  const {
    assets,
    priceHistory,
    catalysts,
    predictions,
    forecastNews,
    errorAudits,
    error,
    loading,
    fetchPriceHistory,
    fetchCatalysts,
    fetchForecast,
    fetchErrorAudits,
  } = useTauri();

  React.useEffect(() => {
    if (ticker) {
      void fetchPriceHistory(ticker);
      void fetchCatalysts(ticker);
      void fetchForecast(ticker);
      void fetchErrorAudits(ticker);
    }
  }, [ticker, fetchPriceHistory, fetchCatalysts, fetchForecast, fetchErrorAudits]);

  const asset = ticker ? assets.find((item) => item.ticker === ticker) : undefined;
  const history = ticker ? priceHistory[ticker] ?? [] : [];
  const forecast = ticker ? predictions[ticker] : undefined;
  const latestPrice = history.length ? history[history.length - 1].close : undefined;

  if (!ticker) return <div className="text-surface-500">No asset selected</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/" className="text-sm text-brand-600 hover:underline">&larr; Back</Link>
        <div>
          <h1 className="text-2xl font-bold text-surface-800">{asset?.name || ticker}</h1>
          {asset?.name && <p className="text-sm text-surface-500">{ticker}</p>}
        </div>
      </div>

      <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <div className="text-sm text-surface-500">Type</div>
            <div className="font-medium text-surface-800">{asset?.asset_type ?? "Asset"}</div>
          </div>
          <div>
            <div className="text-sm text-surface-500">Latest Close</div>
            <div className="font-medium text-surface-800">
              {latestPrice === undefined ? "No price data" : `$${latestPrice.toFixed(2)}`}
            </div>
          </div>
          <div>
            <div className="text-sm text-surface-500">Available History</div>
            <div className="font-medium text-surface-800">
              {history.length ? `${history[0].date} to ${history[history.length - 1].date}` : "Loading"}
            </div>
            <div className="text-xs text-surface-500">{history.length.toLocaleString()} daily prices</div>
          </div>
        </div>
        {asset?.notes && <p className="mt-3 text-sm text-surface-600">{asset.notes}</p>}
      </div>

      <AssetPriceChart
        ticker={ticker}
        history={history}
        forecast={forecast}
        audits={errorAudits[ticker] ?? []}
      />

      {forecast && Object.keys(forecast).length > 0 && (
        <ForecastSummary
          ticker={ticker}
          forecasts={forecast}
          latestPrice={latestPrice}
          historyCount={history.length}
          news={forecastNews[ticker] ?? []}
        />
      )}

      {ticker && catalysts[ticker] && catalysts[ticker].length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Catalyst Events</h2>
          <div className="space-y-2">
            {catalysts[ticker].map((catalyst) => (
              <div key={catalyst.id} className="p-3 bg-surface-100 rounded-lg">
                <div className="font-medium text-surface-800">{catalyst.title}</div>
                <div className="text-sm text-surface-500">{catalyst.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <div role="alert" className="text-sm text-red-600">Error: {error}</div>}
      {loading && <div className="text-surface-500">Loading...</div>}
    </div>
  );
};

export default AssetDetail;
