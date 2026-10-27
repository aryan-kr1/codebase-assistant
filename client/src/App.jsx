import { useEffect, useState } from "react";
import "./App.css";

export default function App() {
  const [chats, setChats] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState("");

  // Load the chat list once
  useEffect(() => {
    fetch("/api/chats")
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then(setChats)
      .catch(() => setError("Could not load chats."));
  }, []);

  // Load messages whenever a different chat is selected
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    setMessages([]);
    fetch(`/api/chats/${activeId}/messages`)
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then((data) => {
        if (!cancelled) setMessages(data);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load messages.");
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const activeChat = chats.find((c) => c._id === activeId);

  return (
    <div className="app">
      <aside className="sidebar">
        <h2>Codebase Assistant</h2>

        {/* Placeholder: wired up in the next step */}
        <form className="repo-form" onSubmit={(e) => e.preventDefault()}>
          <input placeholder="https://github.com/owner/repo" disabled />
          <button disabled>Index repo</button>
        </form>

        {error && <div className="error">{error}</div>}

        <div className="chat-list">
          {chats.map((chat) => (
            <button
              key={chat._id}
              className={`chat-item ${chat._id === activeId ? "active" : ""}`}
              onClick={() => {
                setError("");
                setActiveId(chat._id);
              }}
            >
              <span>{chat.title}</span>
              <small>{chat.repo}</small>
            </button>
          ))}
        </div>
      </aside>

      <main className="main">
        <div className="main-header">
          {activeChat ? activeChat.repo : "Select a chat"}
        </div>

        <div className="messages">
          {!activeChat && (
            <div className="empty">Pick a chat from the sidebar.</div>
          )}
          {messages.map((m) => (
            <div key={m._id} className={`message ${m.role}`}>
              {m.content}
              {m.citations?.length > 0 && (
                <div className="sources">
                  Sources:{" "}
                  {m.citations
                    .map((c) => `${c.file}:${c.start_line}-${c.end_line}`)
                    .join(", ")}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Placeholder: wired up in the next step */}
        <form className="ask-form" onSubmit={(e) => e.preventDefault()}>
          <textarea rows={2} placeholder="Ask about this repo..." disabled />
          <button disabled>Send</button>
        </form>
      </main>
    </div>
  );
}
