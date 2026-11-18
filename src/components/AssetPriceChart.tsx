import React from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ErrorAudit, HorizonForecast, PriceHistoryPoint } from "../tauri-backend/hooks/types";

const TIME_RANGES = [
  { label: "1 day", days: 1 },
  { label: "1 week", days: 7 },
  { label: "1 month", days: 30 },
  { label: "3 months", days: 90 },
  { label: "1 year", days: 365 },
  { label: "3 years", days: 365 * 3 },
  { label: "5 years", days: 365 * 5 },
  { label: "Max", days: null },
] as const;

const HORIZON_DAYS: Record<string, number> = {
  "1d": 1,
  "7d": 7,
  "1m": 30,
  "6m": 180,
  "1y": 365,
  "3y": 365 * 3,
  "5y": 365 * 5,
  "10y": 365 * 10,
  "20y": 365 * 20,
};

interface AssetPriceChartProps {
  ticker: string;
  history: PriceHistoryPoint[];
  forecast?: Record<string, HorizonForecast>;
  generatedAt?: string;
  audits?: ErrorAudit[];
}

const AssetPriceChart: React.FC<AssetPriceChartProps> = ({
  ticker,
  history,
  forecast,
  generatedAt,
  audits = [],
}) => {
  const [rangeDays, setRangeDays] = React.useState<number | null>(null);

  const chartData = React.useMemo(() => {
    if (history.length === 0) {
      return [];
    }

    const cutoff = rangeDays === null ? null : new Date();
    if (cutoff && rangeDays !== null) {
      cutoff.setUTCDate(cutoff.getUTCDate() - rangeDays);
    }
    let visibleHistory = cutoff
      ? history.filter((point) => point.date >= cutoff.toISOString().slice(0, 10))
      : history;
    if (visibleHistory.length === 0) {
      visibleHistory = [history[history.length - 1]];
    }

    const rows = new Map<string, {
      date: string;
      close?: number;
      forecast?: number;
      priorForecast?: number;
      deviationPercent?: number;
      priorHorizon?: string;
    }>();
    visibleHistory.forEach((point) => rows.set(point.date, { date: point.date, close: point.close }));

    audits.forEach((audit) => {
      const date = audit.audit_date.slice(0, 10);
      if (date < visibleHistory[0].date || date > visibleHistory[visibleHistory.length - 1].date) {
        return;
      }
      const row = rows.get(date) ?? { date };
      row.close = audit.actual_close;
      row.priorForecast = audit.predicted_price;
      row.deviationPercent = audit.predicted_price
        ? (audit.actual_close / audit.predicted_price - 1) * 100
        : 0;
      row.priorHorizon = audit.horizon;
      rows.set(date, row);
    });

    const latestPrice = history[history.length - 1].close;
    if (forecast && latestPrice > 0) {
      const base = new Date(generatedAt || new Date().toISOString());
      const baseDate = Number.isNaN(base.getTime())
        ? new Date().toISOString().slice(0, 10)
        : base.toISOString().slice(0, 10);
      rows.set(baseDate, { ...rows.get(baseDate), date: baseDate, forecast: latestPrice });

      Object.entries(forecast)
        .map(([horizon, prediction]) => ({
          days: HORIZON_DAYS[horizon],
          price: prediction.predicted_price,
        }))
        .filter((point) => point.days !== undefined)
        .sort((left, right) => left.days - right.days)
        .forEach((point) => {
          const date = new Date(`${baseDate}T12:00:00Z`);
          date.setUTCDate(date.getUTCDate() + point.days);
          const key = date.toISOString().slice(0, 10);
          rows.set(key, { ...rows.get(key), date: key, forecast: point.price });
        });
    }

    return [...rows.values()].sort((left, right) => left.date.localeCompare(right.date));
  }, [audits, forecast, generatedAt, history, rangeDays]);

  if (history.length === 0) {
    return null;
  }

  return (
    <section className="rounded-xl border border-surface-200 bg-surface-50 p-4">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-lg font-semibold text-surface-800">Price history and forecast - {ticker}</h2>
        <div className="flex flex-wrap gap-1" aria-label="Price history time range">
          {TIME_RANGES.map((timeRange) => (
            <button
              key={timeRange.label}
              type="button"
              onClick={() => setRangeDays(timeRange.days)}
              aria-pressed={rangeDays === timeRange.days}
              className={`rounded-md px-2 py-1 text-xs ${
                rangeDays === timeRange.days
                  ? "bg-brand-600 text-white"
                  : "border border-surface-300 text-surface-600 hover:bg-surface-100"
              }`}
            >
              {timeRange.label}
            </button>
          ))}
        </div>
      </div>
      {(forecast || audits.length > 0) && (
        <div className="mb-3 flex flex-wrap gap-4 text-xs text-surface-600">
          <span><span className="mr-1 inline-block h-0.5 w-4 bg-indigo-500 align-middle" />Actual close</span>
          {forecast && (
            <span><span className="mr-1 inline-block h-0.5 w-4 border-t-2 border-dashed border-orange-500 align-middle" />Forecast path; changes are relative to the latest close</span>
          )}
          {audits.length > 0 && (
            <span><span className="mr-1 inline-block h-0.5 w-4 border-t border-dashed border-red-600 align-middle" />Previous forecast (hover to see deviation)</span>
          )}
        </div>
      )}
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            interval="preserveStartEnd"
            tickFormatter={(date: string) => new Date(`${date}T12:00:00`).toLocaleDateString()}
          />
          <YAxis tickFormatter={(value: number) => `$${value.toFixed(2)}`} />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) {
                return null;
              }
              const row = payload[0].payload;
              return (
                <div className="rounded-md border border-surface-200 bg-white p-3 text-xs shadow">
                  <div className="mb-1 font-medium text-surface-800">
                    {new Date(`${label}T12:00:00`).toLocaleDateString()}
                  </div>
                  {row.close !== undefined && <div>Actual close: ${row.close.toFixed(2)}</div>}
                  {row.forecast !== undefined && <div>Forecast: ${row.forecast.toFixed(2)}</div>}
                  {row.priorForecast !== undefined && (
                    <>
                      <div>Previous {row.priorHorizon} forecast: ${row.priorForecast.toFixed(2)}</div>
                      <div className={row.deviationPercent >= 0 ? "text-emerald-700" : "text-red-700"}>
                        Deviation: {row.deviationPercent >= 0 ? "+" : ""}{row.deviationPercent.toFixed(1)}%
                      </div>
                    </>
                  )}
                </div>
              );
            }}
          />
          <Line type="monotone" dataKey="close" name="Actual close" stroke="#6366f1" strokeWidth={2} dot={false} />
          {forecast && (
            <Line
              type="monotone"
              dataKey="forecast"
              name="Forecast"
              stroke="#f97316"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 3 }}
            />
          )}
          {audits.length > 0 && (
            <Line
              type="monotone"
              dataKey="priorForecast"
              name="Previous forecast"
              stroke="#dc2626"
              strokeWidth={1}
              strokeDasharray="3 3"
              dot={{ r: 4, fill: "#dc2626" }}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
};

export default AssetPriceChart;
