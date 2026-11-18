import React from "react";
import type { HorizonForecast } from "../tauri-backend/hooks/types";

interface ForecastSummaryProps {
  ticker: string;
  forecasts: Record<string, HorizonForecast>;
  latestPrice?: number;
  historyCount: number;
}

const ForecastSummary: React.FC<ForecastSummaryProps> = ({
  ticker,
  forecasts,
  latestPrice,
  historyCount,
}) => (
  <section className="rounded-xl border border-surface-200 bg-surface-50 p-4">
    <h2 className="mb-4 text-lg font-semibold text-surface-800">Forecast - {ticker}</h2>
    {historyCount < 20 && (
      <p className="mb-3 text-sm text-amber-700">
        Limited history: the forecast uses a flat baseline at the latest available close.
      </p>
    )}
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Object.entries(forecasts).map(([horizon, prediction]) => {
        const change = latestPrice && latestPrice > 0
          ? (prediction.predicted_price / latestPrice - 1) * 100
          : null;
        const changeLabel = change === null
          ? null
          : change > 0
            ? "rise from latest close"
            : change < 0
              ? "fall from latest close"
              : "change from latest close";

        return (
          <article key={horizon} className="rounded-lg bg-surface-100 p-3">
            <div className="text-sm text-surface-500">{horizon}</div>
            <div className="font-semibold text-surface-800">${prediction.predicted_price.toFixed(2)}</div>
            {change !== null && changeLabel && (
              <div className={`text-sm font-medium ${change > 0 ? "text-emerald-700" : change < 0 ? "text-red-700" : "text-surface-600"}`}>
                {change > 0 ? "+" : ""}{change.toFixed(1)}% {changeLabel}
              </div>
            )}
            <p className="mt-2 text-xs leading-relaxed text-surface-600">
              {prediction.key_assumptions}
            </p>
          </article>
        );
      })}
    </div>
  </section>
);

export default ForecastSummary;
