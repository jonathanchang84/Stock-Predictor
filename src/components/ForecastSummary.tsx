import React from "react";
import type { HorizonForecast, NewsArticle } from "../tauri-backend/hooks/types";
import ExternalLink from "./ExternalLink";

interface ForecastSummaryProps {
  ticker: string;
  forecasts: Record<string, HorizonForecast>;
  latestPrice?: number;
  historyCount: number;
  news: NewsArticle[];
}

const ForecastSummary: React.FC<ForecastSummaryProps> = ({
  ticker,
  forecasts,
  latestPrice,
  historyCount,
  news,
}) => (
  <section className="rounded-xl border border-surface-200 bg-surface-50 p-4">
    <h2 className="mb-4 text-lg font-semibold text-surface-800">Forecast - {ticker}</h2>
    {historyCount < 20 && (
      <p className="mb-3 text-sm text-amber-700">
        Limited history: the forecast uses a flat baseline at the latest available close.
      </p>
    )}
    <p className="mb-3 text-xs text-surface-500">
      Forecast ranges are estimates; 90% is a nominal target, not a guarantee. Run a walk-forward backtest to review historical coverage for this asset.
    </p>
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
            {prediction.low > 0 &&
            prediction.high > 0 &&
            !prediction.interval_method.startsWith("unavailable") ? (
              <div className="text-xs text-surface-500">
                Indicative {Math.round(prediction.interval_coverage * 100)}% range: $
                {prediction.low.toFixed(2)}-${prediction.high.toFixed(2)}
                <span className="block">
                  {prediction.interval_method}
                  {prediction.interval_sample_size > 0
                    ? ` (${prediction.interval_sample_size} prior forecasts)`
                    : ""}
                </span>
              </div>
            ) : (
              <div className="text-xs text-surface-500">Forecast range unavailable.</div>
            )}
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
    <div className="mt-5 border-t border-surface-200 pt-4">
      <h3 className="font-semibold text-surface-800">Recent news (context only)</h3>
      <p className="mb-2 text-xs text-surface-500">
        Headlines are provided for context and do not change the price forecast.
      </p>
      {news.length > 0 ? (
        <ul className="space-y-2">
          {news.map((article) => (
            <li key={`${article.url}-${article.title}`} className="text-sm">
              <ExternalLink href={article.url} className="text-brand-700 hover:underline">
                {article.title}
              </ExternalLink>
              <span className="ml-2 text-xs text-surface-500">
                {article.source}{article.published ? ` · ${article.published}` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-surface-500">No recent headlines were available.</p>
      )}
    </div>
  </section>
);

export default ForecastSummary;
