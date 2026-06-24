import { useEffect, useRef, useState } from "react";

import { askQuestion, getPdfStatus } from "../services/api";

export default function ChatBox({ sourceKey, docName }) {
  const [messages, setMessages] = useState([]); // { role: 'user'|'assistant', text, sources? }
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false); // document finished embedding?
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  // Poll the backend until this document has been embedded into the vector DB.
  // (Upload finishes when the file hits S3, but a Lambda still needs to chunk
  //  and embed it — only then can we answer questions about it.)
  useEffect(() => {
    let active = true;
    let timer;

    async function check() {
      try {
        const status = await getPdfStatus(sourceKey);
        if (!active) return;
        if (status.ready) {
          setReady(true);
          return; // ready — stop polling
        }
      } catch {
        // transient error — keep retrying
      }
      if (active) timer = setTimeout(check, 3000);
    }

    setReady(false);
    check();

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [sourceKey]);

  async function send(e) {
    e?.preventDefault();
    const question = input.trim();
    if (!question || loading || !ready) return;

    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setLoading(true);

    try {
      const data = await askQuestion(question, sourceKey);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: data.answer, sources: data.sources || [] },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text:
            "Sorry, something went wrong reaching the server: " +
            (e?.message || "unknown error"),
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat">
      {!ready && (
        <div className="chat-processing">
          <span className="doc-delete-spinner" />
          <span>
            Processing <strong>{docName}</strong>… this can take a moment. You
            can start chatting as soon as it’s ready.
          </span>
        </div>
      )}

      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && !loading && ready && (
          <div className="chat-welcome">
            <div className="chat-welcome-icon" aria-hidden>
              💬
            </div>
            <h2>Ask anything about this document</h2>
            <p>
              Questions are answered using only the contents of{" "}
              <strong>{docName}</strong>.
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`bubble-row ${m.role}`}>
            <div className={`bubble ${m.role} ${m.isError ? "error" : ""}`}>
              <p className="bubble-text">{m.text}</p>
              {m.sources?.length > 0 && (
                <p className="bubble-sources">
                  Source: {m.sources.map((s) => s.split("/").pop()).join(", ")}
                </p>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="bubble-row assistant">
            <div className="bubble assistant">
              <span className="typing">
                <i />
                <i />
                <i />
              </span>
            </div>
          </div>
        )}
      </div>

      <form className="chat-input" onSubmit={send}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            ready
              ? `Ask a question about ${docName}…`
              : "Document is still processing…"
          }
          disabled={loading || !ready}
        />
        <button type="submit" disabled={loading || !ready || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
