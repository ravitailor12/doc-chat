import FileUploader from "../components/FileUploader";
import PdfList from "../components/PdfList";
import { useDocuments } from "../context/DocumentsContext";

export default function Upload() {
  const { pdfs, loading, error, refresh, remove } = useDocuments();

  return (
    <div className="page">
      <section className="hero">
        <h1>Chat with your PDFs</h1>
        <p className="hero-sub">
          Upload a document, then click it to ask questions answered straight
          from its contents.
        </p>
      </section>

      <FileUploader onUploaded={refresh} />

      {/* <section className="docs-section">
        <div className="section-head">
          <h2>Your documents</h2>
          <button className="ghost-btn" onClick={refresh} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <PdfList
          pdfs={pdfs}
          loading={loading}
          error={error}
          onDelete={remove}
        />
      </section> */}
    </div>
  );
}
