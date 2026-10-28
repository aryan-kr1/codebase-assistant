import { useEffect, useRef, useState } from "react";
import "./App.css";

// Matches [path/to/file.js:10-42]; accepts -, non-breaking hyphen, en dash, em dash
const CITATION_RE = /\[([^\[\]:\s]+):(\d+)\s*[-\u2011\u2013\u2014]\s*(\d+)\]/g;

export default function App() {
  const [chats, setChats] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(""); // "" | "starting" | "running"
  const indexing = jobStatus !== "";
  const bottomRef = useRef(null);
  const [snippet, setSnippet] = useState(null); // {file, start, end, code, loading, error}
  const codeReq = useRef(0); // ignores late responses from older clicks

  function loadChats() {
    return fetch("/api/chats")
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then(setChats)
      .catch(() => setError("Could not load chats."));
  }

  async function startIndex(e) {
    e.preventDefault();
    const url = repoUrl.trim();
    if (!url || indexing) return;

    setError("");
    setJobStatus("starting");
    try {
      const res = await fetch("/api/index", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || "Could not start indexing.");
      }
      const data = await res.json();
      setJobId(data.job_id);
      setJobStatus("running");
    } catch (err) {
      setJobStatus("");
      setError(err.message || "Could not start indexing.");
    }
  }

  // Load the chat list once
  useEffect(() => {
    loadChats();
  }, []);

  // Load messages whenever a different chat is selected
  useEffect(() => {
    if (!activeId) return;

    setSnippet(null);
    codeReq.current++;

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

  // Poll the indexing job every 2 seconds
  useEffect(() => {
    if (!jobId) return;
    let stopped = false;

    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/index/${jobId}`);
        if (!res.ok) throw new Error();
        const job = await res.json();
        if (stopped) return;

        if (job.status === "failed") {
          stopped = true;
          clearInterval(timer);
          setError(job.error || "Indexing failed.");
          setJobId(null);
          setJobStatus("");
        } else if (job.status === "done") {
          stopped = true;
          clearInterval(timer);
          const chatRes = await fetch("/api/chats", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ repo: job.repo }),
          });
          if (!chatRes.ok) throw new Error();
          const chat = await chatRes.json();
          await loadChats();
          setActiveId(chat._id);
          setRepoUrl("");
          setJobId(null);
          setJobStatus("");
        }
      } catch {
        stopped = true;
        clearInterval(timer);
        setError("Something went wrong while indexing.");
        setJobId(null);
        setJobStatus("");
      }
    }, 2000);

    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [jobId]);

  // Keep the newest text in view while the answer streams
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const activeChat = chats.find((c) => c._id === activeId);

  async function openCode(file, start, end) {
    if (!activeId) return;
    const req = ++codeReq.current;
    setSnippet({ file, start, end, code: "", loading: true, error: "" });
    try {
      const params = new URLSearchParams({
        file,
        start: String(start),
        end: String(end),
      });
      const res = await fetch(`/api/chats/${activeId}/code?${params}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      if (req !== codeReq.current) return;
      setSnippet({
        file,
        start: data.start_line,
        end: data.end_line,
        code: data.code,
        loading: false,
        error: "",
      });
    } catch {
      if (req !== codeReq.current) return;
      setSnippet({
        file,
        start,
        end,
        code: "",
        loading: false,
        error: "Could not load that code.",
      });
    }
  }

  function closeCode() {
    codeReq.current++;
    setSnippet(null);
  }

  // Split answer text into plain text and clickable citations
  function renderContent(text) {
    const parts = [];
    let last = 0;
    for (const m of text.matchAll(CITATION_RE)) {
      const [full, file, start, end] = m;
      if (m.index > last) parts.push(text.slice(last, m.index));
      parts.push(
        <button
          key={m.index}
          className="cite"
          onClick={() => openCode(file, Number(start), Number(end))}
        >
          {file}:{start}-{end}
        </button>,
      );
      last = m.index + full.length;
    }
    if (last < text.length) parts.push(text.slice(last));
    return parts;
  }

  // Update one message by id
  function patchMessage(id, patch) {
    setMessages((prev) =>
      prev.map((m) => (m._id === id ? { ...m, ...patch } : m)),
    );
  }

  // Handle one SSE event from the stream
  function handleEvent(raw, assistantId, state) {
    let event = "message";
    let data = "";
    for (const line of raw.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    let value;
    try {
      value = JSON.parse(data);
    } catch {
      return;
    }

    if (event === "token") {
      state.text += value;
      patchMessage(assistantId, { content: state.text });
    } else if (event === "citations") {
      patchMessage(assistantId, { citations: value });
    } else if (event === "error") {
      setError(typeof value === "string" ? value : "Something went wrong.");
    }
  }

  async function sendQuestion(e) {
    e.preventDefault();
    const question = input.trim();
    if (!question || !activeId || streaming) return;

    setError("");
    setInput("");
    setStreaming(true);

    const stamp = Date.now();
    const userId = `tmp-user-${stamp}`;
    const assistantId = `tmp-assistant-${stamp}`;
    setMessages((prev) => [
      ...prev,
      { _id: userId, role: "user", content: question, citations: [] },
      { _id: assistantId, role: "assistant", content: "", citations: [] },
    ]);

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chatId: activeId, question }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || "Request failed.");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      const state = { text: "" };
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let i;
        while ((i = buffer.indexOf("\n\n")) !== -1) {
          handleEvent(buffer.slice(0, i), assistantId, state);
          buffer = buffer.slice(i + 2);
        }
      }
    } catch (err) {
      setError(err.message || "Request failed.");
    } finally {
      setStreaming(false);
      loadChats(); // refresh titles and order
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h2>Codebase Assistant</h2>

        <form className="repo-form" onSubmit={startIndex}>
          <input
            placeholder="https://github.com/owner/repo"
            value={repoUrl}
            disabled={indexing}
            onChange={(e) => setRepoUrl(e.target.value)}
          />
          <button disabled={indexing || !repoUrl.trim()}>
            {indexing ? "Indexing…" : "Index repo"}
          </button>
        </form>
        {indexing && <div>Indexing… this can take a minute.</div>}

        {error && <div className="error">{error}</div>}

        <div className="chat-list">
          {chats.map((chat) => (
            <button
              key={chat._id}
              className={`chat-item ${chat._id === activeId ? "active" : ""}`}
              disabled={streaming}
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
              {m.content
                ? renderContent(m.content)
                : streaming && m.role === "assistant"
                  ? "…"
                  : ""}
              {m.citations?.length > 0 && (
                <div className="sources">
                  Sources:
                  {m.citations.map((c, i) => (
                    <button
                      key={i}
                      className="cite"
                      onClick={() => openCode(c.file, c.start_line, c.end_line)}
                    >
                      {c.file}:{c.start_line}-{c.end_line}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {snippet && (
          <div className="code-panel">
            <div className="code-header">
              <span>
                {snippet.file}:{snippet.start}-{snippet.end}
              </span>
              <button onClick={closeCode}>Close</button>
            </div>
            {snippet.loading ? (
              <div className="code-note">Loading…</div>
            ) : snippet.error ? (
              <div className="code-note error">{snippet.error}</div>
            ) : (
              <pre className="code-body">{snippet.code}</pre>
            )}
          </div>
        )}

        <form className="ask-form" onSubmit={sendQuestion}>
          <textarea
            rows={2}
            placeholder="Ask about this repo..."
            value={input}
            disabled={!activeChat || streaming}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendQuestion(e);
              }
            }}
          />
          <button disabled={!activeChat || streaming || !input.trim()}>
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
