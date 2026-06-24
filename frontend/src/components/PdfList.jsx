import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { formatSize, formatDate } from "../utils/format";
import TrashIcon from "./TrashIcon";

export default function PdfList({ pdfs, loading, error, onDelete }) {
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(null);

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
      await onDelete(pdf.key);
    } catch (err) {
      alert("Could not delete document: " + (err?.message || "unknown error"));
    } finally {
      setDeleting(null);
    }
  }

  if (loading) {
    return (
      <div className="pdf-grid">
        {[0, 1, 2].map((i) => (
          <div key={i} className="pdf-card pdf-card--skeleton" />
        ))}
      </div>
    );
  }

  if (error) {
    return <p className="empty-state">Could not load documents: {error}</p>;
  }

  if (!pdfs.length) {
    return (
      <p className="empty-state">
        No documents yet. Upload your first PDF above to start chatting.
      </p>
    );
  }

  return (
    <div className="pdf-grid">
      {pdfs.map((pdf) => (
        <div
          key={pdf.key}
          className="pdf-card"
          onClick={() => navigate(`/chat/${encodeURIComponent(pdf.key)}`)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              navigate(`/chat/${encodeURIComponent(pdf.key)}`);
            }
          }}
        >
          <div className="pdf-card-icon" aria-hidden>
            PDF
          </div>
          <div className="pdf-card-body">
            <p className="pdf-card-name" title={pdf.name}>
              {pdf.name}
            </p>
            <p className="pdf-card-meta">
              {formatSize(pdf.size)} · {formatDate(pdf.last_modified)}
            </p>
          </div>
          <span className="pdf-card-cta">Chat →</span>
          <button
            className="pdf-card-delete"
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
  );
}
