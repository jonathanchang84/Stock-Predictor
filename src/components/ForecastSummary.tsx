import React from "react";
import type {
  ForecastContextSignal,
  HorizonForecast,
  MarketContext,
  NewsArticle,
} from "../tauri-backend/hooks/types";
import ExternalLink from "./ExternalLink";

interface ForecastSummaryProps {
  ticker: string;
  forecasts: Record<string, HorizonForecast>;
  latestPrice?: number;
  historyCount: number;
  news: NewsArticle[];
  marketContext: MarketContext | null;
  contextSignals: Record<string, ForecastContextSignal>;
}

const formatPercent = (value: number): string => `${(value * 100).toFixed(1)}%`;

const formatCurrency = (value: number, currency = "USD"): string => {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${currency} ${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
};

const ForecastSummary: React.FC<ForecastSummaryProps> = ({
  ticker,
  forecasts,
  latestPrice,
  historyCount,
  news,
  marketContext,
  contextSignals,
}) => (
  <section className="rounded-xl border border-surface-200 bg-surface-50 p-4">
    <h2 className="mb-4 text-lg font-semibold text-surface-800">Forecast - {ticker}</h2>
    {historyCount < 20 && (
      <p className="mb-3 text-sm text-amber-700">
        Limited history: the forecast uses a flat baseline at the latest available close.
      </p>
    )}
    <p className="mb-3 text-xs text-surface-500">
      Headlines can modestly adjust short-term estimates and company fundamentals can adjust long-term growth. Known event dates widen ranges but do not predict outcomes. These are bounded heuristics, not proven causal effects; ranges are estimates with a nominal 90% target, not guarantees.
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
            {contextSignals[horizon] && (
              <p className="mt-1 text-xs text-surface-500">
                Context: headlines {contextSignals[horizon].news_adjustment_pct >= 0 ? "+" : ""}
                {contextSignals[horizon].news_adjustment_pct.toFixed(2)}%
                {contextSignals[horizon].fundamental_annualized_adjustment_pct !== 0
                  ? ` fundamentals ${contextSignals[horizon].fundamental_annualized_adjustment_pct >= 0 ? "+" : ""}${contextSignals[horizon].fundamental_annualized_adjustment_pct.toFixed(2)}%/yr`
                  : ""}
                {contextSignals[horizon].event_risk_multiplier > 1
                  ? ` · event range ×${contextSignals[horizon].event_risk_multiplier.toFixed(2)}`
                  : ""}
              </p>
            )}
            <p className="mt-2 text-xs leading-relaxed text-surface-600">
              {prediction.key_assumptions}
            </p>
          </article>
        );
      })}
    </div>
    {marketContext && (
      <div className="mt-5 border-t border-surface-200 pt-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-semibold text-surface-800">Fundamentals and scheduled events</h3>
          <span className="text-xs text-surface-500">
            {marketContext.source} snapshot · {marketContext.captured_at.slice(0, 10)}
          </span>
        </div>
        {Object.keys(marketContext.fundamentals).length > 0 ? (
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-4">
            {marketContext.fundamentals.sector && (
              <div><dt className="text-xs text-surface-500">Sector</dt><dd>{marketContext.fundamentals.sector}</dd></div>
            )}
            {marketContext.fundamentals.quote_type && (
              <div><dt className="text-xs text-surface-500">Asset type</dt><dd>{marketContext.fundamentals.quote_type}</dd></div>
            )}
            {marketContext.fundamentals.industry && (
              <div><dt className="text-xs text-surface-500">Industry</dt><dd>{marketContext.fundamentals.industry}</dd></div>
            )}
            {marketContext.fundamentals.fund_family && (
              <div><dt className="text-xs text-surface-500">Fund family</dt><dd>{marketContext.fundamentals.fund_family}</dd></div>
            )}
            {marketContext.fundamentals.category && (
              <div><dt className="text-xs text-surface-500">Fund category</dt><dd>{marketContext.fundamentals.category}</dd></div>
            )}
            {marketContext.fundamentals.market_cap !== undefined && (
              <div><dt className="text-xs text-surface-500">Market cap</dt><dd>{formatCurrency(marketContext.fundamentals.market_cap, marketContext.fundamentals.currency)}</dd></div>
            )}
            {marketContext.fundamentals.trailing_pe !== undefined && (
              <div><dt className="text-xs text-surface-500">Trailing P/E</dt><dd>{marketContext.fundamentals.trailing_pe.toFixed(2)}</dd></div>
            )}
            {marketContext.fundamentals.forward_pe !== undefined && (
              <div><dt className="text-xs text-surface-500">Forward P/E</dt><dd>{marketContext.fundamentals.forward_pe.toFixed(2)}</dd></div>
            )}
            {marketContext.fundamentals.price_to_book !== undefined && (
              <div><dt className="text-xs text-surface-500">Price / book</dt><dd>{marketContext.fundamentals.price_to_book.toFixed(2)}</dd></div>
            )}
            {marketContext.fundamentals.revenue_growth !== undefined && (
              <div><dt className="text-xs text-surface-500">Revenue growth</dt><dd>{formatPercent(marketContext.fundamentals.revenue_growth)}</dd></div>
            )}
            {marketContext.fundamentals.earnings_growth !== undefined && (
              <div><dt className="text-xs text-surface-500">Earnings growth</dt><dd>{formatPercent(marketContext.fundamentals.earnings_growth)}</dd></div>
            )}
            {marketContext.fundamentals.profit_margin !== undefined && (
              <div><dt className="text-xs text-surface-500">Profit margin</dt><dd>{formatPercent(marketContext.fundamentals.profit_margin)}</dd></div>
            )}
            {marketContext.fundamentals.return_on_equity !== undefined && (
              <div><dt className="text-xs text-surface-500">Return on equity</dt><dd>{formatPercent(marketContext.fundamentals.return_on_equity)}</dd></div>
            )}
            {marketContext.fundamentals.operating_margin !== undefined && (
              <div><dt className="text-xs text-surface-500">Operating margin</dt><dd>{formatPercent(marketContext.fundamentals.operating_margin)}</dd></div>
            )}
            {marketContext.fundamentals.debt_to_equity !== undefined && (
              <div><dt className="text-xs text-surface-500">Debt / equity</dt><dd>{marketContext.fundamentals.debt_to_equity.toFixed(1)}%</dd></div>
            )}
            {marketContext.fundamentals.dividend_yield !== undefined && (
              <div><dt className="text-xs text-surface-500">Dividend yield</dt><dd>{formatPercent(marketContext.fundamentals.dividend_yield)}</dd></div>
            )}
            {marketContext.fundamentals.expense_ratio !== undefined && (
              <div><dt className="text-xs text-surface-500">Expense ratio</dt><dd>{formatPercent(marketContext.fundamentals.expense_ratio)}</dd></div>
            )}
            {marketContext.fundamentals.nav_price !== undefined && (
              <div><dt className="text-xs text-surface-500">NAV</dt><dd>{formatCurrency(marketContext.fundamentals.nav_price, marketContext.fundamentals.currency)}</dd></div>
            )}
            {marketContext.fundamentals.total_assets !== undefined && (
              <div><dt className="text-xs text-surface-500">Fund assets</dt><dd>{formatCurrency(marketContext.fundamentals.total_assets, marketContext.fundamentals.currency)}</dd></div>
            )}
            {marketContext.fundamentals.ytd_return !== undefined && (
              <div><dt className="text-xs text-surface-500">YTD return</dt><dd>{formatPercent(marketContext.fundamentals.ytd_return)}</dd></div>
            )}
            {marketContext.fundamentals.three_year_average_return !== undefined && (
              <div><dt className="text-xs text-surface-500">3-year average return</dt><dd>{formatPercent(marketContext.fundamentals.three_year_average_return)}</dd></div>
            )}
            {marketContext.fundamentals.five_year_average_return !== undefined && (
              <div><dt className="text-xs text-surface-500">5-year average return</dt><dd>{formatPercent(marketContext.fundamentals.five_year_average_return)}</dd></div>
            )}
            {marketContext.fundamentals.ten_year_average_return !== undefined && (
              <div><dt className="text-xs text-surface-500">10-year average return</dt><dd>{formatPercent(marketContext.fundamentals.ten_year_average_return)}</dd></div>
            )}
            {marketContext.fundamentals.target_mean_price !== undefined && (
              <div><dt className="text-xs text-surface-500">Analyst target mean</dt><dd>{formatCurrency(marketContext.fundamentals.target_mean_price, marketContext.fundamentals.currency)}</dd></div>
            )}
          </dl>
        ) : (
          <p className="mt-2 text-sm text-surface-500">No current fundamentals were available from the data provider.</p>
        )}
        {marketContext.upcoming_events.length > 0 ? (
          <ul className="mt-3 space-y-1 text-sm">
            {marketContext.upcoming_events.map((event) => (
              <li key={`${event.type}-${event.date}`} className="text-surface-700">
                {event.label}: {event.date} <span className="text-xs text-surface-500">({event.source})</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-surface-500">No upcoming company events were available.</p>
        )}
        {marketContext.warnings.length > 0 && (
          <ul className="mt-2 text-xs text-amber-700">
            {marketContext.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        )}
      </div>
    )}
    <div className="mt-5 border-t border-surface-200 pt-4">
      <h3 className="font-semibold text-surface-800">Recent news (analyzed context)</h3>
      <p className="mb-2 text-xs text-surface-500">
        Dated headlines are scored with a small keyword-based sentiment signal; article links are provided for verification.
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
