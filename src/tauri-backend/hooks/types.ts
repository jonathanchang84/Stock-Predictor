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
  sentiment_score: number;
  key_assumptions: string;
}

export interface ForecastResult {
  ticker: string;
  generated_at: string;
  predictions: Record<string, HorizonForecast>;
  confidence_band: Record<string, number>;
  calibration_context_applied: boolean;
}

export interface NewsArticle {
  source: string;
  title: string;
  summary: string;
  url: string;
  published: string;
}
