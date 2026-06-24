import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import { listPdfs, deletePdf } from "../services/api";

const DocumentsContext = createContext(null);

// Shared document state so both the sidebar and the home page stay in sync
// after an upload or a delete.
export function DocumentsProvider({ children }) {
  const [pdfs, setPdfs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPdfs(await listPdfs());
    } catch (e) {
      setError(e?.message || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  const remove = useCallback(async (key) => {
    await deletePdf(key);
    // Optimistically drop it from the list so the UI updates instantly.
    setPdfs((prev) => prev.filter((p) => p.key !== key));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <DocumentsContext.Provider value={{ pdfs, loading, error, refresh, remove }}>
      {children}
    </DocumentsContext.Provider>
  );
}

export function useDocuments() {
  const ctx = useContext(DocumentsContext);
  if (!ctx) {
    throw new Error("useDocuments must be used within a DocumentsProvider");
  }
  return ctx;
}
