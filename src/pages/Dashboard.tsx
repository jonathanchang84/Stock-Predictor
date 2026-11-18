import React from "react";
import { useTauri } from "../tauri-backend/hooks";
import type { Asset, AssetSearchResult } from "../tauri-backend/hooks/types";
import AssetPriceChart from "../components/AssetPriceChart";
import ForecastSummary from "../components/ForecastSummary";

const TICKER_PATTERN = /^[A-Z0-9.^=_-]+$/i;

const Dashboard: React.FC = () => {
  const {
    assets,
    priceHistory,
    errorAudits,
    catalysts,
    predictions,
    forecastNews,
    loading,
    error,
    addAsset,
    updateAsset,
    deleteAsset,
    searchAssets,
    fetchForecast,
    fetchPriceHistory,
    fetchErrorAudits,
  } = useTauri();
  const [selectedTicker, setSelectedTicker] = React.useState<string | null>(null);
  const [isAddAssetOpen, setIsAddAssetOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [assetQuery, setAssetQuery] = React.useState("");
  const [assetType, setAssetType] = React.useState("stock");
  const [assetSearchResults, setAssetSearchResults] = React.useState<AssetSearchResult[]>([]);
  const [selectedAsset, setSelectedAsset] = React.useState<AssetSearchResult | null>(null);
  const [editingAsset, setEditingAsset] = React.useState<Asset | null>(null);
  const [editName, setEditName] = React.useState("");
  const [editType, setEditType] = React.useState("stock");
  const [editNotes, setEditNotes] = React.useState("");
  const [editError, setEditError] = React.useState<string | null>(null);
  const [assetActionError, setAssetActionError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (assets.length === 0) {
      setSelectedTicker(null);
      return;
    }
    setSelectedTicker((current) =>
      current && assets.some((asset) => asset.ticker === current) ? current : assets[0].ticker,
    );
  }, [assets]);

  React.useEffect(() => {
    if (selectedTicker) {
      void fetchPriceHistory(selectedTicker);
      void fetchErrorAudits(selectedTicker);
    }
  }, [selectedTicker, fetchErrorAudits, fetchPriceHistory]);

  const selectedHistory = selectedTicker ? priceHistory[selectedTicker] ?? [] : [];
  const latestPrice = selectedHistory.length ? selectedHistory[selectedHistory.length - 1].close : undefined;
  const historyStart = selectedHistory[0]?.date;
  const historyEnd = selectedHistory.length ? selectedHistory[selectedHistory.length - 1].date : undefined;
  const forecastCount = selectedTicker ? Object.keys(predictions[selectedTicker] ?? {}).length : 0;

  const handleAssetSearch = async () => {
    const query = assetQuery.trim();
    if (!query) {
      setFormError("Enter a ticker symbol or fund name to search.");
      return;
    }
    setSelectedAsset(null);
    const results = await searchAssets(query);
    setAssetSearchResults(results);
    setFormError(results.length ? null : "No matching assets found. Check the ticker or try another name.");
  };

  const handleAddAsset = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedAsset) {
      const results = await searchAssets(assetQuery.trim());
      setAssetSearchResults(results);
      setFormError(
        results.length
          ? "Select a matching ticker from the results before adding it."
          : "No matching assets found. Check the symbol or try another name.",
      );
      return;
    }

    const ticker = selectedAsset.ticker.toUpperCase();
    if (assets.some((asset) => asset.ticker === ticker)) {
      setFormError(`${ticker} is already being tracked.`);
      return;
    }
    if (!TICKER_PATTERN.test(ticker)) {
      setFormError("Select a valid matching ticker from the search results.");
      return;
    }

    setFormError(null);
    const added = await addAsset({
      ticker,
      asset_type: assetType,
      name: selectedAsset?.name ?? "",
      purchase_price: 0,
      quantity: 0,
      date_added: new Date().toISOString().slice(0, 10),
      notes: "",
    });
    if (added) {
      setAssetQuery("");
      setAssetType("stock");
      setAssetSearchResults([]);
      setSelectedAsset(null);
      setIsAddAssetOpen(false);
      setSelectedTicker(ticker);
    }
  };

  const startEditingAsset = (asset: Asset) => {
    setEditingAsset(asset);
    setEditName(asset.name);
    setEditType(asset.asset_type);
    setEditNotes(asset.notes);
    setEditError(null);
  };

  const handleUpdateAsset = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editingAsset) {
      return;
    }
    const updated = await updateAsset(editingAsset.ticker, {
      name: editName.trim(),
      asset_type: editType,
      notes: editNotes.trim(),
    });
    if (updated) {
      setEditingAsset(null);
    } else {
      setEditError("Could not update this asset. See the page error for details.");
    }
  };

  const handleDeleteAsset = async (asset: Asset) => {
    if (!window.confirm(`Stop tracking ${asset.name || asset.ticker}? Its saved history and forecasts will be deleted.`)) {
      return;
    }
    setAssetActionError(null);
    if (!await deleteAsset(asset.ticker)) {
      setAssetActionError("Could not delete the asset. Review the API error shown on this page and try again.");
    }
  };

  const selectSearchResult = (result: AssetSearchResult) => {
    setSelectedAsset(result);
    setAssetQuery(result.ticker);
    setAssetType(result.asset_type);
    setFormError(
      assets.some((asset) => asset.ticker === result.ticker)
        ? `${result.ticker} is already being tracked.`
        : null,
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-800">Market Overview</h1>
          <p className="text-surface-500">Track price history and view multi-horizon forecasts for stocks and funds.</p>
        </div>
        <button
          onClick={() => { setFormError(null); setIsAddAssetOpen(true); }}
          className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg flex items-center gap-2"
        >
          <span>+</span> Add Asset
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="text-sm text-surface-500">Tracked Assets</div>
          <div className="text-2xl font-bold text-surface-800">{assets.length}</div>
        </div>
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="text-sm text-surface-500">Latest Close{selectedTicker ? ` - ${selectedTicker}` : ""}</div>
          <div className="text-2xl font-bold text-surface-800">
            {latestPrice === undefined ? "—" : `$${latestPrice.toFixed(2)}`}
          </div>
        </div>
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="text-sm text-surface-500">Available History</div>
          <div className="text-sm font-semibold text-surface-800">
            {historyStart && historyEnd ? `${historyStart} to ${historyEnd}` : "Select an asset"}
          </div>
          <div className="text-xs text-surface-500">{selectedHistory.length.toLocaleString()} daily prices</div>
        </div>
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <div className="text-sm text-surface-500">Forecast Horizons</div>
          <div className="text-2xl font-bold text-brand-600">{forecastCount || 9}</div>
        </div>
      </div>

      {assets.length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-end gap-3">
          <label className="block flex-1 text-sm font-medium text-surface-700">
            Asset
            <select
              value={selectedTicker || ""}
              onChange={(event) => setSelectedTicker(event.target.value)}
              className="mt-2 block w-full rounded-md border border-surface-300 px-3 py-2 bg-white text-surface-800 focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
            >
              <option value="">Select asset...</option>
              {assets.map((asset) => (
                <option key={asset.ticker} value={asset.ticker}>
                  {asset.ticker} - {asset.name || asset.asset_type}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => selectedTicker && void fetchForecast(selectedTicker)}
            disabled={!selectedTicker || loading}
            className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg disabled:opacity-50"
          >
            Generate Forecast
          </button>
        </div>
      )}

      {assets.length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-3">Manage tracked assets</h2>
          {assetActionError && <p role="alert" className="mb-2 text-sm text-red-600">{assetActionError}</p>}
          <div className="divide-y divide-surface-200">
            {assets.map((asset) => (
              <div key={asset.ticker} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="font-medium text-surface-800">{asset.name || asset.ticker}</div>
                  <div className="text-sm text-surface-500">{asset.ticker} · {asset.asset_type}</div>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => startEditingAsset(asset)}
                    className="rounded-lg border border-surface-300 px-3 py-2 text-sm text-surface-700"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDeleteAsset(asset)}
                    disabled={loading}
                    className="rounded-lg border border-red-300 px-3 py-2 text-sm text-red-700 disabled:opacity-50"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {selectedTicker && (
        <AssetPriceChart
          ticker={selectedTicker}
          history={selectedHistory}
          forecast={predictions[selectedTicker]}
          audits={errorAudits[selectedTicker]}
        />
      )}

      {selectedTicker && predictions[selectedTicker] && (
        <ForecastSummary
          ticker={selectedTicker}
          forecasts={predictions[selectedTicker]}
          latestPrice={latestPrice}
          historyCount={selectedHistory.length}
          news={forecastNews[selectedTicker] ?? []}
        />
      )}

      {selectedTicker && catalysts[selectedTicker]?.length > 0 && (
        <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
          <h2 className="text-lg font-semibold text-surface-800 mb-4">Detected Catalyst Events</h2>
          <div className="space-y-2">
            {catalysts[selectedTicker].map((catalyst) => (
              <div key={catalyst.id} className="p-3 bg-surface-100 rounded-lg">
                <div className="font-medium text-surface-800">{catalyst.title}</div>
                <div className="text-sm text-surface-500">{catalyst.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <div role="alert" className="text-red-600 text-sm">Error: {error}</div>}
      {loading && <div className="text-surface-500">Loading...</div>}

      {isAddAssetOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <form onSubmit={handleAddAsset} className="w-full max-w-lg space-y-4 rounded-xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-surface-800">Add stock or fund</h2>
              <button type="button" onClick={() => setIsAddAssetOpen(false)} aria-label="Close" className="text-surface-500">✕</button>
            </div>
            <label className="block text-sm font-medium text-surface-700">
              Search by ticker or fund name
              <div className="mt-1 flex gap-2">
                <input
                  required
                  value={assetQuery}
                  onChange={(event) => {
                    setAssetQuery(event.target.value);
                    setSelectedAsset(null);
                    setAssetSearchResults([]);
                    setFormError(null);
                  }}
                  className="block min-w-0 flex-1 rounded-md border border-surface-300 px-3 py-2"
                  placeholder="AAPL or UBS S&P 500"
                />
                <button
                  type="button"
                  onClick={() => void handleAssetSearch()}
                  disabled={loading || !assetQuery.trim()}
                  className="rounded-lg border border-surface-300 px-3 py-2 disabled:opacity-50"
                >
                  Search
                </button>
              </div>
            </label>
            {assetSearchResults.length > 0 && (
              <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-surface-200 p-2">
                {assetSearchResults.map((result) => (
                  <button
                    key={`${result.ticker}-${result.exchange}`}
                    type="button"
                    onClick={() => selectSearchResult(result)}
                    className="block w-full rounded-md px-3 py-2 text-left hover:bg-surface-100"
                  >
                    <span className="block font-medium text-surface-800">{result.name}</span>
                    <span className="block text-xs text-surface-500">
                      {result.ticker}{result.exchange ? ` - ${result.exchange}` : ""}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {selectedAsset && (
              <p className="text-sm text-emerald-700">
                Selected: {selectedAsset.name} ({selectedAsset.ticker})
              </p>
            )}
            <label className="block text-sm font-medium text-surface-700">
              Asset type
              <select
                value={assetType}
                onChange={(event) => setAssetType(event.target.value)}
                className="mt-1 block w-full rounded-md border border-surface-300 px-3 py-2 bg-white"
              >
                <option value="stock">Stock</option>
                <option value="etf">ETF</option>
                <option value="mutual_fund">Mutual fund</option>
                <option value="index_fund">Index fund</option>
              </select>
            </label>
            {formError && <p role="alert" className="text-sm text-red-600">{formError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setIsAddAssetOpen(false)} className="rounded-lg border border-surface-300 px-4 py-2 text-surface-700">
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || !assetQuery.trim()}
                className="rounded-lg bg-brand-600 px-4 py-2 text-white disabled:opacity-50"
              >
                {selectedAsset ? "Add Asset" : "Check Match"}
              </button>
            </div>
          </form>
        </div>
      )}

      {editingAsset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <form onSubmit={handleUpdateAsset} className="w-full max-w-lg space-y-4 rounded-xl bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold text-surface-800">Edit tracked asset</h2>
                <p className="text-sm text-surface-500">{editingAsset.ticker}</p>
              </div>
              <button type="button" onClick={() => setEditingAsset(null)} aria-label="Close" className="text-surface-500">✕</button>
            </div>
            <label className="block text-sm font-medium text-surface-700">
              Display name
              <input
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
                className="mt-1 block w-full rounded-md border border-surface-300 px-3 py-2"
              />
            </label>
            <label className="block text-sm font-medium text-surface-700">
              Asset type
              <select
                value={editType}
                onChange={(event) => setEditType(event.target.value)}
                className="mt-1 block w-full rounded-md border border-surface-300 px-3 py-2 bg-white"
              >
                <option value="stock">Stock</option>
                <option value="etf">ETF</option>
                <option value="mutual_fund">Mutual fund</option>
                <option value="index_fund">Index fund</option>
              </select>
            </label>
            <label className="block text-sm font-medium text-surface-700">
              Notes
              <textarea
                value={editNotes}
                onChange={(event) => setEditNotes(event.target.value)}
                rows={3}
                className="mt-1 block w-full rounded-md border border-surface-300 px-3 py-2"
              />
            </label>
            {editError && <p role="alert" className="text-sm text-red-600">{editError}</p>}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditingAsset(null)} className="rounded-lg border border-surface-300 px-4 py-2 text-surface-700">
                Cancel
              </button>
              <button type="submit" disabled={loading} className="rounded-lg bg-brand-600 px-4 py-2 text-white disabled:opacity-50">
                Save Changes
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
