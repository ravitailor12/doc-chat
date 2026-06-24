import { useState } from "react";
import { NavLink, useMatch, useNavigate } from "react-router-dom";

import { useDocuments } from "../context/DocumentsContext";
import { formatSize, formatDate } from "../utils/format";
import TrashIcon from "./TrashIcon";

export default function Sidebar({ open, onClose }) {
  const { pdfs, loading, error, remove } = useDocuments();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(null);

  // Highlight whichever document is currently open in the chat view.
  const match = useMatch("/chat/:key");
  const activeKey = match ? decodeURIComponent(match.params.key) : null;

  async function handleDelete(e, pdf) {
    e.preventDefault();
    e.stopPropagation();
    if (
      !window.confirm(
        `Delete "${pdf.name}"?\nThis permanently removes the file and its chat data.`
      )
    ) {
      return;
    }

    setDeleting(pdf.key);
    try {
      await remove(pdf.key);
      // If we just deleted the doc we're chatting with, leave the chat view.
      if (activeKey === pdf.key) navigate("/");
    } catch (err) {
      alert("Could not delete document: " + (err?.message || "unknown error"));
    } finally {
      setDeleting(null);
    }
  }

  return (
    <>
      {open && <div className="sidebar-overlay" onClick={onClose} />}

      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="sidebar-head">
          <span className="sidebar-title">Documents</span>
          {!loading && !error && (
            <span className="sidebar-count">{pdfs.length}</span>
          )}
        </div>

        <div className="doc-list">
          {loading && (
            <>
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="doc-skeleton" />
              ))}
            </>
          )}

          {!loading && error && (
            <p className="sidebar-empty">Couldn’t load documents.</p>
          )}

          {!loading && !error && pdfs.length === 0 && (
            <p className="sidebar-empty">No documents yet. Upload one to begin.</p>
          )}

          {!loading &&
            !error &&
            pdfs.map((pdf) => (
              <div className="doc-item" key={pdf.key}>
                <NavLink
                  to={`/chat/${encodeURIComponent(pdf.key)}`}
                  className={`doc-link ${activeKey === pdf.key ? "active" : ""}`}
                  onClick={onClose}
                >
                  <span className="doc-icon" aria-hidden>
                    PDF
                  </span>
                  <span className="doc-info">
                    <span className="doc-name" title={pdf.name}>
                      {pdf.name}
                    </span>
                    <span className="doc-meta">
                      {formatSize(pdf.size)} · {formatDate(pdf.last_modified)}
                    </span>
                  </span>
                </NavLink>

                <button
                  className="doc-delete"
                  onClick={(e) => handleDelete(e, pdf)}
                  disabled={deleting === pdf.key}
                  title="Delete document"
                  aria-label={`Delete ${pdf.name}`}
                >
                  {deleting === pdf.key ? (
                    <span className="doc-delete-spinner" />
                  ) : (
                    <TrashIcon />
                  )}
                </button>
              </div>
            ))}
        </div>
      </aside>
    </>
  );
}
