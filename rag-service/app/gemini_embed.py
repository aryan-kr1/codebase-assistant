import math
import os
import time

import httpx
from langchain_core.embeddings import Embeddings

MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-2")
BASE = "https://generativelanguage.googleapis.com/v1beta/models"
BATCH = 50  # texts per request (Google allows up to 100)
MAX_TPM = 27000  # stay under the 30K tokens/min limit
MAX_RPM = 90  # stay under the 100 requests/min limit
ATTEMPTS = 5


class GeminiQuotaError(RuntimeError):
    pass


def _tokens(text):
    # rough estimate; measured about 300 tokens per 1000-char chunk
    return len(text) // 3 + 1


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class GeminiEmbeddings(Embeddings):
    def __init__(self):
        self.key = os.getenv("GEMINI_API_KEY")
        self.client = httpx.Client(timeout=30)
        self.window = []  # (time, tokens, requests) in the last 60 s

    def _wait_for_room(self, tokens, reqs):
        while True:
            now = time.time()
            self.window = [w for w in self.window if now - w[0] < 60]
            t = sum(w[1] for w in self.window)
            r = sum(w[2] for w in self.window)
            if not self.window or (t + tokens <= MAX_TPM and r + reqs <= MAX_RPM):
                return
            time.sleep(max(0.5, 60 - (now - self.window[0][0]) + 0.5))

    def _post(self, method, body, tokens, reqs, attempts=ATTEMPTS):
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY missing")
        last = None
        for attempt in range(attempts):
            self._wait_for_room(tokens, reqs)
            self.window.append((time.time(), tokens, reqs))
            try:
                resp = self.client.post(
                    f"{BASE}/{method}",
                    json=body,
                    headers={"x-goog-api-key": self.key},
                )
            except httpx.TransportError as e:
                last = f"network error: {type(e).__name__}"
                time.sleep(2**attempt * 2)
                continue
            if resp.status_code == 200:
                return resp.json()
            last = resp.status_code
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = resp.headers.get("Retry-After")
                delay = float(wait) if wait and wait.isdigit() else 2**attempt * 2
                print(
                    f"Gemini embed retry ({resp.status_code}), sleeping {delay}s",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f"Gemini embedding error {resp.status_code}")
        if last == 429:
            raise GeminiQuotaError("Gemini embedding quota reached")
        raise RuntimeError(f"Gemini embedding failed ({last})")

    def embed_documents(self, texts):
        out = []
        for i in range(0, len(texts), BATCH):
            chunk = texts[i : i + BATCH]
            body = {
                "requests": [
                    {"model": f"models/{MODEL}", "content": {"parts": [{"text": t}]}}
                    for t in chunk
                ]
            }
            d = self._post(
                f"{MODEL}:batchEmbedContents",
                body,
                sum(_tokens(t) for t in chunk),
                len(chunk),
            )
            out += [_norm(e["values"]) for e in d["embeddings"]]
        return out

    def embed_query(self, text):
        body = {"model": f"models/{MODEL}", "content": {"parts": [{"text": text}]}}
        d = self._post(f"{MODEL}:embedContent", body, _tokens(text), 1, attempts=2)
        return _norm(d["embedding"]["values"])
