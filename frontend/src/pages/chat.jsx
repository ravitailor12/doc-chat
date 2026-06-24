import { Link, useParams } from "react-router-dom";

import ChatBox from "../components/ChatBox";

export default function Chat() {
  const { key } = useParams();
  const sourceKey = decodeURIComponent(key || "");
  const docName = sourceKey.split("/").pop() || sourceKey;

  return (
    <div className="page chat-page">
      <div className="chat-topbar">
        <Link to="/" className="back-link">
          ← Documents
        </Link>
        <div className="chat-doc">
          <span className="chat-doc-icon" aria-hidden>
            PDF
          </span>
          <span className="chat-doc-name" title={docName}>
            {docName}
          </span>
        </div>
      </div>

      {/* key={sourceKey} forces a fresh ChatBox (and clears messages)
          whenever the user switches to a different document. */}
      <ChatBox key={sourceKey} sourceKey={sourceKey} docName={docName} />
    </div>
  );
}
