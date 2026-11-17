import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Asset, PriceHistoryPoint, CatalystEvent, ErrorAudit, ForecastAccuracy, AppSettings, ForecastResult } from "./types";

export interface TauriContextValue {
  assets: Asset[];
  priceHistory: Record<string, PriceHistoryPoint[]>;
  catalysts: Record<string, CatalystEvent[]>;
  predictions: Record<string, ForecastResult["predictions"]>;
  errorAudits: Record<string, ErrorAudit[]>;
  forecastAccuracy: Record<string, ForecastAccuracy[]>;
  settings: AppSettings;
  loading: boolean;
  error: string | null;
  fetchAssets: () => Promise<void>;
  fetchPriceHistory: (ticker: string) => Promise<void>;
  fetchCatalysts: (ticker: string) => Promise<void>;
  fetchForecast: (ticker: string) => Promise<ForecastResult | null>;
  fetchErrorAudits: (ticker: string) => Promise<void>;
  fetchErrorSummary: (ticker: string) => Promise<void>;
  fetchForecastAccuracy: () => Promise<void>;
  fetchSettings: () => Promise<void>;
  addAsset: (asset: Omit<Asset, "id" | "created_at" | "updated_at">) => Promise<void>;
  updateAsset: (ticker: string, updates: Partial<Pick<Asset, "name" | "purchase_price" | "quantity" | "date_added" | "notes">>) => Promise<void>;
  deleteAsset: (ticker: string) => Promise<void>;
  runDailyForecast: () => Promise<void>;
  updateSettings: (settings: AppSettings) => Promise<void>;
}

const TauriContext = createContext<TauriContextValue | null>(null);

interface TauriState {
  assets: Asset[];
  priceHistory: Record<string, PriceHistoryPoint[]>;
  catalysts: Record<string, CatalystEvent[]>;
  predictions: Record<string, ForecastResult["predictions"]>;
  errorAudits: Record<string, ErrorAudit[]>;
  forecastAccuracy: Record<string, ForecastAccuracy[]>;
  settings: AppSettings;
  loading: boolean;
  error: string | null;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`API request failed (${response.status}): ${detail || response.statusText}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export const TauriProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<TauriState>({
    assets: [],
    priceHistory: {},
    catalysts: {},
    predictions: {},
    errorAudits: {},
    forecastAccuracy: {},
    settings: {},
    loading: false,
    error: null,
  });
  const pendingRequests = useRef(0);

  const runRequest = useCallback(async <T,>(request: () => Promise<T>): Promise<T | null> => {
    pendingRequests.current += 1;
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      return await request();
    } catch (error) {
      setState((current) => ({ ...current, error: getErrorMessage(error) }));
      return null;
    } finally {
      pendingRequests.current -= 1;
      setState((current) => ({ ...current, loading: pendingRequests.current > 0 }));
    }
  }, []);

  const fetchAssets = useCallback(async () => {
    await runRequest(async () => {
      const assets = await apiRequest<Asset[]>("/api/assets");
      setState((current) => ({ ...current, assets }));
    });
  }, [runRequest]);

  const fetchPriceHistory = useCallback(async (ticker: string) => {
    await runRequest(async () => {
      const history = await apiRequest<PriceHistoryPoint[]>(
        `/api/assets/${encodeURIComponent(ticker)}/price-history`,
      );
      setState((current) => ({
        ...current,
        priceHistory: {
          ...current.priceHistory,
          [ticker]: history.slice().reverse(),
        },
      }));
    });
  }, [runRequest]);

  const fetchCatalysts = useCallback(async (ticker: string) => {
    await runRequest(async () => {
      const catalysts = await apiRequest<CatalystEvent[]>(
        `/api/assets/${encodeURIComponent(ticker)}/catalysts`,
      );
      setState((current) => ({
        ...current,
        catalysts: { ...current.catalysts, [ticker]: catalysts },
      }));
    });
  }, [runRequest]);

  const fetchForecast = useCallback(async (ticker: string) => {
    const result = await runRequest(() =>
      apiRequest<ForecastResult>("/api/forecast", {
        method: "POST",
        body: JSON.stringify({ ticker }),
      }),
    );
    if (result) {
      setState((current) => ({
        ...current,
        predictions: { ...current.predictions, [ticker]: result.predictions },
      }));
    }
    return result;
  }, [runRequest]);

  const fetchErrorAudits = useCallback(async (ticker: string) => {
    await runRequest(async () => {
      const audits = await apiRequest<ErrorAudit[]>(
        `/api/errors/audits/${encodeURIComponent(ticker)}`,
      );
      setState((current) => ({
        ...current,
        errorAudits: { ...current.errorAudits, [ticker]: audits },
      }));
    });
  }, [runRequest]);

  const fetchErrorSummary = useCallback(async (ticker: string) => {
    await runRequest(() =>
      apiRequest<unknown>(`/api/errors/audit-summary/${encodeURIComponent(ticker)}`),
    );
  }, [runRequest]);

  const fetchForecastAccuracy = useCallback(async () => {
    await runRequest(async () => {
      const summaries = await Promise.all(
        state.assets.map(async (asset) => {
          const rows = await apiRequest<Array<{
            horizon: string;
            avg_pct: number;
            avg_abs: number;
            hit_rate: number;
            total: number;
          }>>(`/api/errors/audit-summary/${encodeURIComponent(asset.ticker)}`);
          return rows.map((row): ForecastAccuracy => ({
            ticker: asset.ticker,
            horizon: row.horizon,
            rolling_30d_mape: row.avg_pct,
            directional_hit_rate: row.hit_rate / 100,
            mean_abs_error: row.avg_abs,
            sample_size: row.total,
            last_reported_at: new Date().toISOString(),
          }));
        }),
      );
      setState((current) => ({
        ...current,
        forecastAccuracy: Object.fromEntries(
          summaries.map((rows, index) => [state.assets[index].ticker, rows]),
        ),
      }));
    });
  }, [runRequest, state.assets]);

  const fetchSettings = useCallback(async () => {
    await runRequest(async () => {
      const settings = await apiRequest<AppSettings>("/api/settings");
      setState((current) => ({ ...current, settings }));
    });
  }, [runRequest]);

  const addAsset = useCallback(async (asset: Omit<Asset, "id" | "created_at" | "updated_at">) => {
    await runRequest(async () => {
      await apiRequest("/api/assets", { method: "POST", body: JSON.stringify(asset) });
      const assets = await apiRequest<Asset[]>("/api/assets");
      setState((current) => ({ ...current, assets }));
    });
  }, [runRequest]);

  const updateAsset = useCallback(async (
    ticker: string,
    updates: Partial<Pick<Asset, "name" | "purchase_price" | "quantity" | "date_added" | "notes">>,
  ) => {
    await runRequest(async () => {
      await apiRequest(`/api/assets/${encodeURIComponent(ticker)}`, {
        method: "PUT",
        body: JSON.stringify(updates),
      });
      const assets = await apiRequest<Asset[]>("/api/assets");
      setState((current) => ({ ...current, assets }));
    });
  }, [runRequest]);

  const deleteAsset = useCallback(async (ticker: string) => {
    await runRequest(async () => {
      await apiRequest(`/api/assets/${encodeURIComponent(ticker)}`, { method: "DELETE" });
      const assets = await apiRequest<Asset[]>("/api/assets");
      setState((current) => ({ ...current, assets }));
    });
  }, [runRequest]);

  const runDailyForecast = useCallback(async () => {
    await runRequest(() => apiRequest("/api/run-daily-forecast", { method: "POST" }));
  }, [runRequest]);

  const updateSettings = useCallback(async (settings: AppSettings) => {
    await runRequest(async () => {
      await apiRequest("/api/settings", {
        method: "PUT",
        body: JSON.stringify(settings),
      });
      setState((current) => ({ ...current, settings }));
    });
  }, [runRequest]);

  useEffect(() => {
    void fetchAssets();
    void fetchSettings();
  }, [fetchAssets, fetchSettings]);

  return (
    <TauriContext.Provider
      value={{
        ...state,
        fetchAssets,
        fetchPriceHistory,
        fetchCatalysts,
        fetchForecast,
        fetchErrorAudits,
        fetchErrorSummary,
        fetchForecastAccuracy,
        fetchSettings,
        addAsset,
        updateAsset,
        deleteAsset,
        runDailyForecast,
        updateSettings,
      }}
    >
      {children}
    </TauriContext.Provider>
  );
};

export function useTauriContext(): TauriContextValue {
  const context = useContext(TauriContext);
  if (!context) {
    throw new Error("useTauriContext must be used within a TauriProvider");
  }
  return context;
}

export default TauriContext;