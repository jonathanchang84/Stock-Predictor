// Types for backend communication

export interface Asset {
  id: number;
  ticker: string;
  asset_type: string;
  name: string;
  purchase_price: number;
  quantity: number;
  date_added: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface AssetSearchResult {
  ticker: string;
  name: string;
  asset_type: string;
  exchange: string;
}

export interface PriceHistoryPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CatalystEvent {
  id: number;
  ticker: string;
  event_date: string;
  event_type: string;
  title: string;
  summary: string;
  source: string;
  confidence: number | null;
  created_at: string;
}

export interface Prediction {
  id: number;
  ticker: string;
  horizon: string;
  predicted_price: number;
  confidence_interval: number;
  confidence_range: number;
  low: number;
  high: number;
  sentiment_score: number;
  key_assumptions: string;
  prediction_date: string;
  created_at: string;
}

export interface ErrorAudit {
  id: number;
  prediction_id: number;
  audit_date: string;
  actual_close: number;
  absolute_error: number;
  percentage_error: number;
  directional_correct: number;
  notes: string;
  audited_at: string;
  prediction_date: string;
  horizon: string;
  predicted_price: number;
}

export interface ForecastAccuracy {
  ticker: string;
  horizon: string;
  rolling_30d_mape: number;
  directional_hit_rate: number;
  mean_abs_error: number;
  sample_size: number;
  last_reported_at: string;
}

export interface AppSettings {
  [key: string]: any;
}

export interface HorizonForecast {
  horizon: string;
  predicted_price: number;
  confidence_interval: number;
  interval_coverage: number;
  low: number;
  high: number;
  interval_method: string;
  interval_sample_size: number;
  sentiment_score: number;
  key_assumptions: string;
}

export interface ForecastResult {
  ticker: string;
  model_version: string;
  generated_at: string;
  predictions: Record<string, HorizonForecast>;
  news_context: NewsArticle[];
  market_context: MarketContext;
  context_signals: Record<string, ForecastContextSignal>;
  context_snapshot_id: number | null;
  confidence_band: Record<string, number>;
  calibration_context_applied: boolean;
}

export interface MarketFundamentals {
  short_name?: string;
  quote_type?: string;
  sector?: string;
  industry?: string;
  currency?: string;
  fund_family?: string;
  category?: string;
  market_cap?: number;
  trailing_pe?: number;
  forward_pe?: number;
  price_to_book?: number;
  revenue_growth?: number;
  earnings_growth?: number;
  profit_margin?: number;
  operating_margin?: number;
  return_on_equity?: number;
  debt_to_equity?: number;
  free_cash_flow?: number;
  dividend_yield?: number;
  target_mean_price?: number;
  recommendation_mean?: number;
  expense_ratio?: number;
  nav_price?: number;
  total_assets?: number;
  ytd_return?: number;
  three_year_average_return?: number;
  five_year_average_return?: number;
  ten_year_average_return?: number;
}

export interface MarketContextEvent {
  type: string;
  date: string;
  label: string;
  source: string;
}

export interface MarketContext {
  ticker: string;
  source: string;
  captured_at: string;
  fundamentals: MarketFundamentals;
  upcoming_events: MarketContextEvent[];
  warnings: string[];
}

export interface ForecastContextSignal {
  news_sentiment_score: number;
  news_articles_used: number;
  news_adjustment_pct: number;
  fundamental_score: number | null;
  fundamental_metrics_used: number;
  fundamental_annualized_adjustment_pct: number;
  event_risk_multiplier: number;
  relevant_events: MarketContextEvent[];
}

export interface BacktestMetrics {
  mae: number;
  mape: number;
  directional_hit_rate?: number;
  interval_coverage?: number;
}

export interface ForecastBacktestResult {
  ticker: string;
  model_version: string;
  as_of: string | null;
  methodology: string;
  horizons: Record<string, {
    sample_size: number;
    context_sample_size: number;
    model: BacktestMetrics | null;
    baseline: BacktestMetrics | null;
  }>;
}

export interface NewsArticle {
  source: string;
  title: string;
  summary: string;
  url: string;
  published: string;
}
