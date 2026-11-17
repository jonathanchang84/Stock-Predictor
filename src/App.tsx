import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { TauriProvider } from "./tauri-backend/hooks";
import Dashboard from "./pages/Dashboard";
import AssetDetail from "./pages/AssetDetail";
import NewsFeed from "./pages/NewsFeed";
import Settings from "./pages/Settings";
import Layout from "./components/Layout";

const App: React.FC = () => {
  return (
    <TauriProvider>
      <Router>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/asset/:ticker" element={<AssetDetail />} />
            <Route path="/news" element={<NewsFeed />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Layout>
      </Router>
    </TauriProvider>
  );
};

export default App;
