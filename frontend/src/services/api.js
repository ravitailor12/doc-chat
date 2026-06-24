import axios from "axios";
import { baseURL } from "../constant";

const api = axios.create({
  baseURL: baseURL, 
});

// Upload a PDF file. `onProgress` (optional) receives 0-100.
export async function uploadPdf(file, onProgress) {
  const form = new FormData();
  form.append("file", file);

  const res = await api.post("/upload/", form, {
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded * 100) / e.total));
      }
    },
  });
  return res.data;
}

// List every PDF stored in S3.
export async function listPdfs() {
  const res = await api.get("/pdfs/");
  return res.data.pdfs;
}

// Check whether a PDF has finished embedding into the vector DB.
// Returns { ready: boolean, chunks: number }.
export async function getPdfStatus(key) {
  const path = key.split("/").map(encodeURIComponent).join("/");
  const res = await api.get(`/pdfs/status/${path}`);
  return res.data;
}

// Delete a PDF (removes it from S3 and its vectors from the database).
export async function deletePdf(key) {
  // Preserve "/" separators but escape any special characters in each segment.
  const path = key.split("/").map(encodeURIComponent).join("/");
  const res = await api.delete(`/pdfs/${path}`);
  return res.data;
}

// Ask a question. When `sourceKey` is given, the answer is scoped to that PDF.
export async function askQuestion(question, sourceKey) {
  const res = await api.post("/chat/", {
    question,
    source_key: sourceKey,
  });
  return res.data; // { answer, sources }
}

export default api;
