import { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, NavLink } from "react-router-dom";

import Upload from "./pages/upload";
import Chat from "./pages/chat";
import Sidebar from "./components/Sidebar";
import { DocumentsProvider } from "./context/DocumentsContext";

function Header({ onMenu }) {
  return (
    <header className="app-header">
      <div className="header-left">
        <button
          className="menu-btn"
          onClick={onMenu}
          aria-label="Toggle documents"
        >
          ☰
        </button>
        <NavLink to="/" className="brand">
          <span className="brand-mark">PDF</span>
          <span className="brand-name">DocChat</span>
        </NavLink>
      </div>
      <nav className="app-nav">
        <NavLink to="/" className="nav-link" end>
          Documents
        </NavLink>
      </nav>
    </header>
  );
}

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <BrowserRouter>
      <DocumentsProvider>
        <Header onMenu={() => setSidebarOpen((v) => !v)} />
        <div className="app-body">
          <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
          <main className="app-main">
            <Routes>
              <Route path="/" element={<Upload />} />
              <Route path="/chat/:key" element={<Chat />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </DocumentsProvider>
    </BrowserRouter>
  );
}

export default App;
