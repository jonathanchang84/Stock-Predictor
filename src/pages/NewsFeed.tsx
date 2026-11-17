import React from "react";

const NewsFeed: React.FC = () => {
  const [news, setNews] = React.useState<any[]>([]);
  const [query, setQuery] = React.useState("markets");
  const [loading, setLoading] = React.useState(false);

  const fetchNews = async () => {
    setLoading(true);
    try {
      // In the full implementation, this would call the backend news aggregation API
      // For now, simulate with sample data
      const sampleNews = [
        { source: "Reuters", title: "Markets rally as rate cut hopes surge", date: "2026-11-17", summary: "Global equities rise on expectations of central bank easing." },
        { source: "Bloomberg", title: "Tech earnings beat after strong holiday demand", date: "2026-11-17", summary: "Semiconductor and software companies report robust quarterly results." },
        { source: "MarketWatch", title: "Oil prices decline on supply concerns", date: "2026-11-17", summary: "Crude futures drop as geopolitical tensions ease and inventories rise." },
      ];
      setNews(sampleNews);
    } catch (e: any) {
      alert("Failed to fetch news: " + e.message);
    }
    setLoading(false);
  };

  React.useEffect(() => {
    fetchNews();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-surface-800">Global News Feed</h1>
          <p className="text-surface-500">Recent events affecting your holdings and market sentiment.</p>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Search news..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="px-3 py-2 border border-surface-300 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
          />
          <button
            onClick={fetchNews}
            disabled={loading}
            className="bg-brand-600 hover:bg-brand-700 text-white px-4 py-2 rounded-lg text-sm flex items-center gap-2 disabled:opacity-50"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            Search
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {news.map((item: any, i: number) => (
          <div key={i} className="bg-surface-50 border border-surface-200 rounded-xl p-4 hover:shadow-md transition-shadow">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-medium text-brand-600">{item.source}</span>
              <span className="text-xs text-surface-400">{item.date}</span>
            </div>
            <h3 className="font-semibold text-surface-800 mb-1">{item.title}</h3>
            <p className="text-sm text-surface-600">{item.summary}</p>
          </div>
        ))}
      </div>

      <div className="bg-surface-50 border border-surface-200 rounded-xl p-4">
        <h2 className="text-lg font-semibold text-surface-800 mb-2">News Sources</h2>
        <ul className="text-sm text-surface-600 space-y-1">
          <li>- Finnhub (free tier): Company news API</li>
          <li>- Marketaux (free tier): Global financial headlines</li>
          <li>- RSS aggregator: Yahoo Finance, Reuters, MarketWatch</li>
        </ul>
      </div>
    </div>
  );
};

export default NewsFeed;
