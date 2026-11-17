import React from "react";
import { useParams, Link } from "react-router-dom";
import { useTauri } from "../tauri-backend/hooks";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const AssetDetail: React.FC = () => {
  const { ticker } = useParams<{ ticker: string }>();
  const { assets, priceHistory, catalysts, predictions, fetchPriceHistory, fetchCatalysts, fetchForecast } = useTauri();

  React.useEffect(() => {
    if (ticker) {
      fetchPriceHistory(ticker);
      fetchCatalysts(ticker);
      fetchForecast(ticker);
    }
  }, [ticker, fetchPriceHistory, fetchCatalysts, fetchForecast]);

  const asset = ticker ? assets.find((a: any) => a.ticker === ticker) : undefined;
  const history = ticker ? priceHistory[ticker] || [] : [];
  const forecast = ticker ? predictions[ticker] || {} : {};
  const latestPrice = history.length > 0 ? history[history.length - 1].close : 0;

  const formatDate = (d: string) => new Date(d).toLocaleDateString();

  if (!ticker) return <div className="text-surface-500">No asset selected</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/" className="text-sm text-brand-600 hover:underline">&larr; Back</Link>
        <h1 className="text-2xl font-bold text-surface-800">{ticker}</h1>
      </div>

      {asset && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-surface-500">Type</div>
              <div className="font-medium text-surface-800">{asset.asset_type}</div>
            </div>
            <div>
              <div className="text-sm text-surface-500">Purchase Price</div>
              <div className="font-medium text-surface-800">${asset.purchase_price.toFixed(2)}</div>
            </div>
            <div>
              <div className="text-sm text-surface-500">Quantity</div>
              <div className="font-medium text-surface-800">{asset.quantity}</div>
            </div>
            <div>
              <div className="text-sm text-surface-500">Current Price</div>
              <div className={`font-medium ${latestPrice >= asset.purchase_price ? "text-emerald-600" : "text-red-600"}`}>
                ${latestPrice.toFixed(2)}
              </div>
            </div>
          </div>
          {asset.notes && <p className="mt-3 text-sm text-surface-600">{asset.notes}</p>}
        </div>
      )}

      {history.length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Price Trend</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={history.slice(-60)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tickFormatter={(d: string) => formatDate(d)} />
              <YAxis tickFormatter={(v: number) => "$" + v.toFixed(2)} />
              <Tooltip formatter={(v: any) => [v, "Price"]} />
              <Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {Object.keys(forecast).length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Multi-Horizon Forecast</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-9 gap-3">
            {Object.entries(forecast).map(([horizon, data]: [string, any]) => (
              <div key={horizon} className="bg-surface-100 rounded-lg p-3">
                <div className="text-xs text-surface-500">{horizon}</div>
                <div className="text-lg font-bold text-surface-800">${data.predicted_price.toFixed(2)}</div>
                <div className="text-xs text-surface-500">delta: {((data.predicted_price / latestPrice - 1) * 100).toFixed(1)}%</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {catalysts[ticker] && catalysts[ticker].length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Catalyst Events</h2>
          <div className="space-y-2">
            {catalysts[ticker].map((ce: any) => (
              <div key={ce.id} className="p-3 bg-surface-100 rounded-lg">
                <div className="font-medium text-surface-800">{ce.title}</div>
                <div className="text-sm text-surface-500">{ce.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default AssetDetail;
