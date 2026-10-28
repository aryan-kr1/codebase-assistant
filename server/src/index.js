require("dotenv").config();
const express = require("express");
const cors = require("cors");
const mongoose = require("mongoose");
const { Readable } = require("node:stream");

const connectDB = require("./db");
const Chat = require("./models/Chat");
const Message = require("./models/Message");

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

// ---- Chats ----

app.post("/api/chats", async (req, res) => {
  const repo = req.body?.repo;
  if (!repo || typeof repo !== "string") {
    return res.status(400).json({ error: "repo is required" });
  }
  const chat = await Chat.create({ repo });
  res.status(201).json(chat);
});

app.get("/api/chats", async (req, res) => {
  const chats = await Chat.find().sort({ updatedAt: -1 });
  res.json(chats);
});

app.get("/api/chats/:id/messages", async (req, res) => {
  if (!mongoose.isValidObjectId(req.params.id)) {
    return res.status(400).json({ error: "Invalid chat id" });
  }
  const messages = await Message.find({ chat: req.params.id }).sort({
    createdAt: 1,
  });
  res.json(messages);
});

app.get("/api/chats/:id/code", async (req, res) => {
  if (!mongoose.isValidObjectId(req.params.id)) {
    return res.status(400).json({ error: "Invalid chat id" });
  }
  const { file, start, end } = req.query;
  if (!file || !start || !end) {
    return res.status(400).json({ error: "file, start and end are required" });
  }
  const chat = await Chat.findById(req.params.id);
  if (!chat) {
    return res.status(404).json({ error: "Chat not found" });
  }
  const params = new URLSearchParams({
    repo: chat.repo,
    file: String(file),
    start: String(start),
    end: String(end),
  });
  forwardJson(res, `/code?${params}`);
});

// ---- Ask: stream the answer to the client and save it when it finishes ----

app.post("/api/ask", async (req, res) => {
  const { chatId, question } = req.body || {};
  if (!chatId || !question) {
    return res.status(400).json({ error: "chatId and question are required" });
  }
  if (!mongoose.isValidObjectId(chatId)) {
    return res.status(400).json({ error: "Invalid chatId" });
  }

  const chat = await Chat.findById(chatId);
  if (!chat) {
    return res.status(404).json({ error: "Chat not found" });
  }

  const recent = await Message.find({ chat: chat._id })
    .sort({ createdAt: -1 })
    .limit(4);
  const history = recent
    .reverse()
    .map((m) => ({ role: m.role, content: m.content }));

  await Message.create({ chat: chat._id, role: "user", content: question });
  const update = { updatedAt: new Date() };
  if (chat.title === "New chat") update.title = question.slice(0, 60);
  await Chat.updateOne({ _id: chat._id }, { $set: update });

  // Stop the upstream request if the client disconnects
  const controller = new AbortController();
  res.on("close", () => controller.abort());

  try {
    const upstream = await fetch(`${RAG_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo: chat.repo, question, history }),
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
    stream.setEncoding("utf8");

    let buffer = "";
    let answer = "";
    let citations = [];
    let finished = false;

    // Read one SSE event so we can collect the full answer for saving
    function handleEvent(raw) {
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
      if (event === "token") answer += value;
      else if (event === "citations") citations = value;
      else if (event === "done") finished = true;
    }

    stream.on("data", (chunk) => {
      res.write(chunk); // pass through to the client unchanged
      buffer += chunk;
      let i;
      while ((i = buffer.indexOf("\n\n")) !== -1) {
        handleEvent(buffer.slice(0, i));
        buffer = buffer.slice(i + 2);
      }
    });

    stream.on("end", async () => {
      if (finished && answer.trim()) {
        try {
          await Message.create({
            chat: chat._id,
            role: "assistant",
            content: answer,
            citations,
          });
        } catch (err) {
          console.error("Saving answer failed:", err.message);
        }
      }
      res.end();
    });

    stream.on("error", () => res.end());
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

connectDB().then(() => {
  app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
  });
});
