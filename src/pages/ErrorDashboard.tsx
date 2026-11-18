import React from "react";
import { useTauri } from "../tauri-backend/hooks";
import type { ForecastBacktestResult } from "../tauri-backend/hooks/types";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const ErrorDashboard: React.FC = () => {
  const { assets, errorAudits, loading, fetchErrorAudits, fetchErrorSummary, runForecastBacktest } = useTauri();
  const [activeTicker, setActiveTicker] = React.useState<string | null>(null);
  const [backtest, setBacktest] = React.useState<ForecastBacktestResult | null>(null);
  const [backtestError, setBacktestError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (activeTicker) { fetchErrorAudits(activeTicker); fetchErrorSummary(activeTicker); }
  }, [activeTicker, fetchErrorAudits, fetchErrorSummary]);

  React.useEffect(() => {
    setBacktest(null);
    setBacktestError(null);
  }, [activeTicker]);

  const handleBacktest = async () => {
    if (!activeTicker) {
      return;
    }
    setBacktestError(null);
    const result = await runForecastBacktest(activeTicker);
    if (result) {
      setBacktest(result);
    } else {
      setBacktestError("Could not run the backtest. Review the API error and try again.");
    }
  };

  if (assets.length === 0) {
    return (<div className="text-center py-12"><h1 className="text-2xl font-bold text-surface-800 mb-4">Error Audit Dashboard</h1><p className="text-surface-500">Add assets to see prediction error calibration.</p></div>);
  }

  return (
    <div className="space-y-6">
      <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
        <h2 className="text-lg font-semibold text-surface-800 mb-4">Select Asset for Error Analysis</h2>
        <select value={activeTicker || ""} onChange={(e) => setActiveTicker(e.target.value)}
          className="block w-full rounded-md border border-surface-300 px-3 py-2 bg-white text-surface-800 focus:ring-2 focus:ring-brand-500 focus:border-brand-500">
          <option value="">All assets</option>
          {assets.map((a: any) => <option key={a.ticker} value={a.ticker}>{a.ticker} - {a.name || a.asset_type}</option>)}
        </select>
      </div>

      {activeTicker && (
        <div className="space-y-4">
          <div className="rounded-xl border border-surface-200 bg-surface-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-surface-800">Historical walk-forward backtest</h3>
                <p className="text-xs text-surface-500">
                  Evaluates forecasts made from earlier data against a flat last-close baseline.
                </p>
              </div>
              <button
                type="button"
                onClick={() => void handleBacktest()}
                disabled={loading}
                className="rounded-lg border border-surface-300 px-3 py-2 text-sm text-surface-700 disabled:opacity-50"
              >
                {loading ? "Running..." : "Run backtest"}
              </button>
            </div>
            {backtestError && <p role="alert" className="mt-2 text-sm text-red-600">{backtestError}</p>}
            {backtest && (
              <>
                <p className="mt-2 text-xs text-surface-500">{backtest.methodology}</p>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-200 text-left text-surface-500">
                        <th className="py-2">Horizon</th>
                        <th className="py-2">Samples</th>
                        <th className="py-2">Model MAPE</th>
                        <th className="py-2">Baseline MAPE</th>
                        <th className="py-2">Direction hit rate</th>
                        <th className="py-2">Range coverage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(backtest.horizons).map(([horizon, result]) => (
                        <tr key={horizon} className="border-b border-surface-100">
                          <td className="py-2">{horizon}</td>
                          <td className="py-2">{result.sample_size}</td>
                          <td className="py-2">{result.model ? `${result.model.mape.toFixed(2)}%` : "—"}</td>
                          <td className="py-2">{result.baseline ? `${result.baseline.mape.toFixed(2)}%` : "—"}</td>
                          <td className="py-2">
                            {result.model?.directional_hit_rate === undefined
                              ? "—"
                              : `${(result.model.directional_hit_rate * 100).toFixed(1)}%`}
                          </td>
                          <td className="py-2">
                            {result.model?.interval_coverage === undefined
                              ? "—"
                              : `${(result.model.interval_coverage * 100).toFixed(1)}%`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
            <div className="bg-surface-50 border border-surface-200 rounded-xl p-4"><div className="text-sm text-surface-500">Total Audits</div><div className="text-2xl font-bold text-surface-800">{errorAudits[activeTicker]?.length || 0}</div></div>
            <div className="bg-surface-50 border border-surface-200 rounded-xl p-4"><div className="text-sm text-surface-500">Avg MAPE</div><div className="text-2xl font-bold text-amber-600">{((errorAudits[activeTicker]?.reduce((s: number, a: any) => s + a.percentage_error, 0) || 0) / (errorAudits[activeTicker]?.length || 1)).toFixed(2)}%</div></div>
            <div className="bg-surface-50 border border-surface-200 rounded-xl p-4"><div className="text-sm text-surface-500">Directional Hit Rate</div><div className="text-2xl font-bold text-emerald-600">{errorAudits[activeTicker]?.filter((a: any) => a.directional_correct).length / (errorAudits[activeTicker]?.length || 1) * 100 || 0}.0%</div></div>
            <div className="bg-surface-50 border border-surface-200 rounded-xl p-4"><div className="text-sm text-surface-500">Mean Abs Error</div><div className="text-2xl font-bold text-surface-800">${((errorAudits[activeTicker]?.reduce((s: number, a: any) => s + a.absolute_error, 0) || 0) / (errorAudits[activeTicker]?.length || 1)).toFixed(4)}</div></div>
          </div>

          <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
            <h3 className="text-md font-semibold text-surface-800 mb-3">MAPE Trend by Horizon</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={errorAudits[activeTicker]}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="horizon" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v: number) => v.toFixed(2) + "%"} />
                <Line type="monotone" dataKey="percentage_error" name="MAPE" stroke="#f59e0b" strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
            <h3 className="text-md font-semibold text-surface-800 mb-3">Recent Audit Records</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-surface-200">
                  <th className="text-left py-2 text-surface-500">Horizon</th>
                  <th className="text-left py-2 text-surface-500">Predicted</th>
                  <th className="text-left py-2 text-surface-500">Actual</th>
                  <th className="text-left py-2 text-surface-500">Abs Error</th>
                  <th className="text-left py-2 text-surface-500">MAPE</th>
                  <th className="text-left py-2 text-surface-500">Directional</th>
                </tr></thead>
                <tbody>
                  {errorAudits[activeTicker]?.slice(0, 10).reverse().map((audit: any) => (
                    <tr key={audit.id} className="border-b border-surface-100">
                      <td className="py-2 text-surface-600">{audit.horizon}</td>
                      <td className="py-2 text-surface-800">${audit.predicted_price.toFixed(2)}</td>
                      <td className="py-2 text-surface-800">${audit.actual_close.toFixed(2)}</td>
                      <td className="py-2 text-surface-600">${audit.absolute_error.toFixed(4)}</td>
                      <td className="py-2 text-surface-600">{audit.percentage_error.toFixed(2)}%</td>
                      <td className={"py-2 font-medium " + (audit.directional_correct ? "text-emerald-600" : "text-red-600")}>{audit.directional_correct ? "Correct" : "Incorrect"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ErrorDashboard;
