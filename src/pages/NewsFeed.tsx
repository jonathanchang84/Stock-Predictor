import React from "react";
import { useTauri } from "../tauri-backend/hooks";

const NewsFeed: React.FC = () => {
  const { news, loading, error, searchNews } = useTauri();
  const [query, setQuery] = React.useState("markets");

  React.useEffect(() => {
    void searchNews("markets");
  }, [searchNews]);

  const handleSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const searchTerm = query.trim();
    if (searchTerm) {
      void searchNews(searchTerm);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-800">Global News Feed</h1>
          <p className="text-surface-500">Recent events affecting your holdings and market sentiment.</p>
        </div>
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="search"
            placeholder="Search news..."
            aria-label="Search news"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="px-3 py-2 border border-surface-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50"
          >
            Search
          </button>
        </form>
      </div>

      {error && <div role="alert" className="text-sm text-red-600">News search failed: {error}</div>}
      {loading && <div className="text-surface-500">Searching news...</div>}

      {news.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {news.map((item, index) => (
            <article
              key={`${item.url}-${item.title}-${index}`}
              className="bg-surface-50 border border-surface-200 rounded-xl p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-medium text-brand-600">{item.source}</span>
                {item.published && (
                  <time className="text-xs text-surface-400">{item.published}</time>
                )}
              </div>
              <h2 className="font-semibold text-surface-800 mb-1">
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-brand-600">
                    {item.title}
                  </a>
                ) : item.title}
              </h2>
              <p className="text-sm text-surface-600">{item.summary}</p>
            </article>
          ))}
        </div>
      ) : !loading && !error ? (
        <div className="rounded-xl border border-surface-200 bg-surface-50 p-6 text-surface-500">
          No articles found for "{query}". Try another search.
        </div>
      ) : null}

      <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
        <h2 className="text-lg font-semibold text-surface-800 mb-2">News Sources</h2>
        <p className="text-sm text-surface-600">
          Searches use configured Finnhub or Marketaux API keys when available, with Yahoo Finance, Reuters, and MarketWatch RSS feeds as a fallback.
        </p>
      </div>
    </div>
  );
};

export default NewsFeed;
