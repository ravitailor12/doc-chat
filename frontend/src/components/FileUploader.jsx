import { useRef, useState } from "react";

import { uploadPdf } from "../services/api";

export default function FileUploader({ onUploaded }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | uploading | done | error
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState("");

  async function handleFile(file) {
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setStatus("error");
      setError("Only PDF files are allowed.");
      return;
    }

    setFileName(file.name);
    setStatus("uploading");
    setProgress(0);
    setError("");

    try {
      await uploadPdf(file, setProgress);
      setStatus("done");
      onUploaded?.();
      // Reset back to idle after a short success moment.
      setTimeout(() => setStatus("idle"), 1500);
    } catch (e) {
      setStatus("error");
      setError(e?.response?.data?.detail || e.message || "Upload failed.");
    }
  }

  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files?.[0]);
  }

  const busy = status === "uploading";

  return (
    <div
      className={`dropzone ${dragging ? "is-dragging" : ""} ${busy ? "is-busy" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => !busy && inputRef.current?.click()}
      role="button"
      tabIndex={0}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        hidden
        onChange={(e) => handleFile(e.target.files?.[0])}
      />

      <div className="dropzone-icon" aria-hidden>
        {status === "done" ? "✓" : "↑"}
      </div>

      {status === "uploading" ? (
        <>
          <p className="dropzone-title">Uploading {fileName}…</p>
          <div className="progress">
            <div className="progress-bar" style={{ width: `${progress}%` }} />
          </div>
          <p className="dropzone-hint">{progress}%</p>
        </>
      ) : status === "done" ? (
        <p className="dropzone-title">Uploaded {fileName}</p>
      ) : (
        <>
          <p className="dropzone-title">
            Drag &amp; drop a PDF here, or <span className="link">browse</span>
          </p>
          <p className="dropzone-hint">PDF files only</p>
        </>
      )}

      {status === "error" && <p className="dropzone-error">{error}</p>}
    </div>
  );
}
