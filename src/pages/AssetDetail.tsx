import React from "react";
import { Link, useParams } from "react-router-dom";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { useTauri } from "../tauri-backend/hooks";

const AssetDetail: React.FC = () => {
  const { ticker } = useParams<{ ticker: string }>();
  const {
    assets,
    priceHistory,
    catalysts,
    predictions,
    error,
    loading,
    fetchPriceHistory,
    fetchCatalysts,
    fetchForecast,
  } = useTauri();

  React.useEffect(() => {
    if (ticker) {
      void fetchPriceHistory(ticker);
      void fetchCatalysts(ticker);
      void fetchForecast(ticker);
    }
  }, [ticker, fetchPriceHistory, fetchCatalysts, fetchForecast]);

  const asset = ticker ? assets.find((item) => item.ticker === ticker) : undefined;
  const history = ticker ? priceHistory[ticker] ?? [] : [];
  const forecast = ticker ? predictions[ticker] : undefined;
  const latestPrice = history.length ? history[history.length - 1].close : undefined;
  const formatDate = (date: string) => new Date(date).toLocaleDateString();

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

      {history.length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Full Price History</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" interval="preserveStartEnd" tickFormatter={formatDate} />
              <YAxis tickFormatter={(value: number) => "$" + value.toFixed(2)} />
              <Tooltip formatter={(value: number) => [value, "Price"]} />
              <Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {forecast && Object.keys(forecast).length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Multi-Horizon Forecast</h2>
          {history.length < 20 && (
            <p className="mb-3 text-sm text-amber-700">
              Limited history: these values use a flat baseline at the latest available close.
            </p>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {Object.entries(forecast).map(([horizon, data]) => (
              <div key={horizon} className="bg-surface-100 rounded-lg p-3">
                <div className="text-xs text-surface-500">{horizon}</div>
                <div className="text-lg font-bold text-surface-800">${data.predicted_price.toFixed(2)}</div>
                {latestPrice !== undefined && (
                  <div className="text-xs text-surface-500">
                    Change: {((data.predicted_price / latestPrice - 1) * 100).toFixed(1)}%
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
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
