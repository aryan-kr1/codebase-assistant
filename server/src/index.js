require("dotenv").config();
const express = require("express");
const cors = require("cors");
const { Readable } = require("node:stream");

const app = express();
const PORT = process.env.PORT || 4000;
const RAG_URL = process.env.RAG_URL || "http://localhost:8000";

app.use(cors());
app.use(express.json());

app.get("/health", (req, res) => {
  res.json({ status: "ok" });
});

// Forward a JSON request to rag-service and relay its status and body
async function forwardJson(res, path, options) {
  try {
    const upstream = await fetch(`${RAG_URL}${path}`, options);
    const body = await upstream.json();
    res.status(upstream.status).json(body);
  } catch (err) {
    console.error("rag-service request failed:", err.message);
    res.status(502).json({ error: "The indexing service is unavailable." });
  }
}

app.post("/api/index", (req, res) => {
  forwardJson(res, "/index", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: req.body?.url }),
  });
});

app.get("/api/index/:jobId", (req, res) => {
  forwardJson(res, `/index/${encodeURIComponent(req.params.jobId)}`);
});

// Pipe the SSE stream from rag-service straight to the client
app.post("/api/ask", async (req, res) => {
  const { repo, question } = req.body || {};
  if (!repo || !question) {
    return res.status(400).json({ error: "repo and question are required" });
  }

  // Stop the upstream request if the client disconnects
  const controller = new AbortController();
  res.on("close", () => controller.abort());

  try {
    const upstream = await fetch(`${RAG_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo, question }),
      signal: controller.signal,
    });

    if (!upstream.ok) {
      return res
        .status(502)
        .json({ error: "The answering service returned an error." });
    }

    res.status(200).set({
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    res.flushHeaders();

    const stream = Readable.fromWeb(upstream.body);
    stream.on("error", () => res.end());
    stream.pipe(res);
  } catch (err) {
    if (controller.signal.aborted) return;
    console.error("rag-service /ask failed:", err.message);
    if (!res.headersSent) {
      res.status(502).json({ error: "The answering service is unavailable." });
    } else {
      res.end();
    }
  }
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
