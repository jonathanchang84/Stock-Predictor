import React from "react";
import { Link, useLocation } from "react-router-dom";

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = React.useState(false);

  const navItems = [
    { path: "/", label: "Portfolio", icon: "📊" },
    { path: "/news", label: "News Feed", icon: "📰" },
    { path: "/settings", label: "Settings", icon: "⚙️" },
  ];

  return (
    <div className="flex h-screen bg-surface-0 text-surface-800 overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`${menuOpen ? "w-64" : "w-20"} bg-surface-100 border-r border-surface-200 flex flex-col transition-all duration-200`}
      >
        <div className="flex items-center gap-3 px-4 h-16 border-b border-surface-200">
          <span className="text-xl font-bold text-brand-600">Stock P</span>
          {menuOpen && (
            <span className="text-sm font-medium text-surface-700">Predictor</span>
          )}
        </div>

        <nav className="flex-1 px-2 py-4 space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                location.pathname === item.path
                  ? "bg-brand-50 text-brand-700"
                  : "text-surface-600 hover:bg-surface-200 hover:text-surface-800"
              }`}
              title={!menuOpen ? item.label : undefined}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {menuOpen && <span>{item.label}</span>}
            </Link>
          ))}
        </nav>

        <div className="px-4 py-3 border-t border-surface-200">
          <div className="text-xs text-surface-500">
            <div className="font-medium text-surface-700">macOS</div>
            <div className="text-xs">Native Tauri App</div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-4 md:p-6 lg:p-8">{children}</div>
      </main>

      {/* Mobile menu toggle */}
      <button
        className="lg:hidden absolute top-4 left-4 z-50 p-2 bg-surface-100 rounded-lg"
        onClick={() => setMenuOpen(!menuOpen)}
        aria-label="Toggle menu"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
    </div>
  );
};

export default Layout;
