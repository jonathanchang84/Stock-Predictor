import React from "react";
import { useTauri } from "../tauri-backend/hooks";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const Dashboard: React.FC = () => {
  const { assets, priceHistory, catalysts, loading, error, fetchPriceHistory } = useTauri();
  const [selectedTicker, setSelectedTicker] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (assets.length > 0) {
      setSelectedTicker(assets[0].ticker);
      fetchPriceHistory(assets[0].ticker);
    }
  }, [assets, fetchPriceHistory]);

  const totalValue = assets.reduce((sum: number, a: any) => sum + a.purchase_price * a.quantity, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-800">Portfolio Overview</h1>
          <p className="text-surface-500">Track stocks and funds, generate forecasts, and learn from prediction errors.</p>
        </div>
        <button className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg flex items-center gap-2">
          <span>+</span> Add Asset
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="text-sm text-surface-500">Total Value</div>
          <div className="text-2xl font-bold text-surface-800">${totalValue.toFixed(2)}</div>
        </div>
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="text-sm text-surface-500">Assets</div>
          <div className="text-2xl font-bold text-surface-800">{assets.length}</div>
        </div>
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="text-sm text-surface-500">Daily Change</div>
          <div className="text-2xl font-bold text-emerald-600">+$1,245.30</div>
        </div>
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="text-sm text-surface-500">Forecasts</div>
          <div className="text-2xl font-bold text-brand-600">9 horizons</div>
        </div>
      </div>

      {assets.length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <select
            value={selectedTicker || ""}
            onChange={(e) => { setSelectedTicker(e.target.value); fetchPriceHistory(e.target.value); }}
            className="mt-2 block w-full rounded-md border border-surface-300 px-3 py-2 bg-white text-surface-800 focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
          >
            <option value="">Select asset...</option>
            {assets.map((a: any) => <option key={a.ticker} value={a.ticker}>{a.ticker} - {a.name || a.asset_type}</option>)}
          </select>
        </div>
      )}

      {selectedTicker && priceHistory[selectedTicker]?.length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Price History - {selectedTicker}</h2>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={priceHistory[selectedTicker].slice(-60)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tickFormatter={(d: string) => new Date(d).toLocaleDateString()} />
              <YAxis tickFormatter={(v: number) => "$" + v.toFixed(2)} />
              <Tooltip formatter={(v: any) => [v, "Price"]} />
              <Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {selectedTicker && catalysts[selectedTicker] && catalysts[selectedTicker].length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Detected Catalyst Events</h2>
          <div className="space-y-2">
            {catalysts[selectedTicker].map((ce: any) => (
              <div key={ce.id} className="p-3 bg-surface-100 rounded-lg">
                <div className="font-medium text-surface-800">{ce.title}</div>
                <div className="text-sm text-surface-500">{ce.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <div className="text-red-600 text-sm">Error: {error}</div>}
      {loading && <div className="text-surface-500">Loading...</div>}
    </div>
  );
};

export default Dashboard;
