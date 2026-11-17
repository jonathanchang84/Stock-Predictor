import React, { useState } from "react";
import { useTauri } from "../tauri-backend/hooks";

const Settings: React.FC = () => {
  const { settings, updateSettings } = useTauri();
  const [apiKeys, setApiKeys] = useState<{ [k: string]: string }>(settings);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    await updateSettings(apiKeys);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-surface-800">Settings</h1>
        <p className="text-surface-500">Configure API keys and application preferences.</p>
      </div>

      <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
        <h2 className="text-lg font-semibold text-surface-800 mb-4">AI Provider API Keys</h2>
        <p className="text-sm text-surface-500 mb-4">Add your API keys to enable advanced forecasting features. The app works without them using yfinance and RSS.</p>

        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-surface-700 mb-1">OpenAI API Key (gpt-4o-mini / gpt-4o)</label>
            <input
              type="password"
              value={apiKeys["openai_api_key"] || ""}
              onChange={(e) => setApiKeys({ ...apiKeys, "openai_api_key": e.target.value })}
              className="w-full rounded-md border border-surface-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              placeholder="sk-..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-surface-700 mb-1">Anthropic API Key (claude-3-5-sonnet)</label>
            <input
              type="password"
              value={apiKeys["anthropic_api_key"] || ""}
              onChange={(e) => setApiKeys({ ...apiKeys, "anthropic_api_key": e.target.value })}
              className="w-full rounded-md border border-surface-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              placeholder="sk-ant-..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-surface-700 mb-1">Finnhub API Key (optional)</label>
            <input
              type="password"
              value={apiKeys["finnhub_api_key"] || ""}
              onChange={(e) => setApiKeys({ ...apiKeys, "finnhub_api_key": e.target.value })}
              className="w-full rounded-md border border-surface-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              placeholder="..."
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-surface-700 mb-1">Alpha Vantage API Key (optional)</label>
            <input
              type="password"
              value={apiKeys["alpha_vantage_api_key"] || ""}
              onChange={(e) => setApiKeys({ ...apiKeys, "alpha_vantage_api_key": e.target.value })}
              className="w-full rounded-md border border-surface-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              placeholder="..."
            />
          </div>
        </div>
      </div>

      <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
        <h2 className="text-lg font-semibold text-surface-800 mb-4">Data Preferences</h2>
        <div className="space-y-2">
          <label className="flex items-center gap-3">
            <input type="checkbox" defaultChecked className="rounded border-surface-300" />
            <span className="text-sm text-surface-700">Auto-run daily forecast on app launch</span>
          </label>
          <label className="flex items-center gap-3">
            <input type="checkbox" defaultChecked className="rounded border-surface-300" />
            <span className="text-sm text-surface-700">Store forecast history in local SQLite</span>
          </label>
        </div>
      </div>

      <div className="flex gap-3">
        <button onClick={handleSave}
          className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-2">
          {saved ? <span className="text-emerald-600">✓ Saved</span> : "Save Settings"}
        </button>
      </div>
    </div>
  );
};

export default Settings;
