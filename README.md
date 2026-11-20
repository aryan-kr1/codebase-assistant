# Codebase Q&A Assistant

Paste a public GitHub repo URL, let the app index the code, then ask questions in plain English. Answers stream in live and cite the exact files and line ranges they used. Click a citation to open the real code.

> **Live demo:** https://askrepo.me
> Runs on a free instance that sleeps after about 15 minutes idle. The first request after a sleep took about 30 seconds in my test (Render warns it can be 50 seconds or more). Four demo repos (express, cors, morgan, express-rate-limit) are ready to ask about as soon as it wakes.
>
> **Demo video:** _coming soon_

## What it does

- Index a small public GitHub repo (one chat per repo, re-indexing reuses it) or ask about one of the 4 built-in demo repos.
- Ask questions and get streamed answers with clickable `[file:start-end]` citations.
- Follow-up questions use the last few messages as context.
- Email and password accounts; every chat belongs to its user.
- Rename and delete chats.
- Re-indexing is incremental: if the repo's latest commit has not changed, indexing is skipped.

## Architecture

Three parts in one repo:

| Folder         | What it is                                                              | Port |
| -------------- | ----------------------------------------------------------------------- | ---- |
| `client/`      | React (Vite) chat UI, plain CSS                                         | 5173 |
| `server/`      | Express 5 API: auth, chats, rate limits, MongoDB, proxy to rag-service  | 4000 |
| `rag-service/` | Python + FastAPI: indexing, retrieval, answer generation, code snippets | 8000 |

Stack: LangChain, Groq (`llama-3.3-70b-versatile`) for answers, Google Gemini (`gemini-embedding-2`) for embeddings, Jina (`jina-reranker-v3`) for reranking, Chroma (on disk) for vectors, MongoDB Atlas (users, chats, messages).

Flow: the browser talks to Express, which checks the login cookie and rate limits, then forwards to rag-service. Answers stream back as server-sent events and the finished answer is saved to MongoDB. In production everything runs in one container: Express serves the built React app and is the only public port, and rag-service listens only on localhost.

## How retrieval works

1. **Path filter:** skip tests, examples, changelogs and similar files before indexing.
2. **Hybrid search:** vector search (Gemini embeddings) and BM25 each return their top 20 chunks.
3. **Reciprocal Rank Fusion** merges the two lists.
4. **Rerank** the top 20 with the hosted Jina reranker and keep the top 5.

The 5 chunks go to the LLM, which must cite them as `[path/to/file.js:10-42]`.

Fallbacks: if the Gemini query embedding fails, retrieval continues with BM25 + rerank only. If Jina fails or times out (10 s, one retry), the hybrid order is used.

## Results

Evaluated on the Express repo with 20 hand-written questions (8 lookup, 8 behavior, 4 multi-file), k=5, chunk size 1000 / overlap 150. A hit means a retrieved chunk from an expected file that also contains the expected marker. I wrote a second set of 20 questions after tuning and never tuned on it (held-out).

Final setups, same pipeline, different models (hit@5 / file-only@5 / MRR):

| Setup                                              | Tuned set            | Held-out set        |
| -------------------------------------------------- | -------------------- | ------------------- |
| **Jina rerank + Gemini embeddings (the demo)**     | 90% / 100% / 0.900   | 100% / 100% / 0.950 |
| Same, BM25 only (fallback when Gemini is down)     | 100% / 100% / 0.8375 | 100% / 100% / 0.975 |
| Jina rerank + local MiniLM embeddings              | 95% / 100% / 0.827   | 100% / 100% / 0.950 |
| Local cross-encoder + local MiniLM (first version) | 85% / 95% / 0.693    | 95% / 100% / 0.817  |

How to read it:

- Each set has only 20 questions, so one question is 5 points. The differences between the hosted setups are within noise; the honest claim is "equal within noise", not "better".
- On the tuned set the Gemini run misses two questions (a `package.json` question and an ETags question: right files, wrong chunk range). Its MRR is higher because all its hits are at rank 1.
- BM25-only does as well as hybrid here because most questions name an exact identifier (`res.json`, `trust proxy`). That does not show vector search is useless; conceptual questions without an identifier, and a second repo, are untested.
- The held-out set is easier (many "where is X defined?" lookups) and is saturated at 100%.

### How retrieval improved (first version, local models)

These runs were measured on the first version, with local MiniLM embeddings and a local cross-encoder, one change at a time, with settings fixed before each run:

| Run             | Change                                       | hit@5 | file-only@5 | MRR   |
| --------------- | -------------------------------------------- | ----- | ----------- | ----- |
| baseline        | naive chunks, vector only                    | 30%   | 55%         | 0.145 |
| path_filter     | skip test/examples/history/readme/changelogs | 60%   | 90%         | 0.414 |
| syntax_chunking | language-aware splitters on top              | 55%   | 90%         | 0.377 |
| hybrid          | BM25 + vectors + RRF                         | 70%   | 95%         | 0.529 |
| rerank          | + cross-encoder rerank                       | 85%   | 95%         | 0.693 |
| rewrite         | + query rewriting                            | 85%   | 95%         | 0.693 |

Every run, including the failed ones, is recorded in `rag-service/eval/RESULTS.md`.

### What did not work

- **Syntax-aware chunking** scored lower than the simple splitter (55% vs 60%), so I reverted it.
- **Query rewriting** gave no gain on either question set, so it is off by default (`REWRITE=1` turns it on).
- **Caching:** measured on the first version, not needed. A full answer took about 2-3 seconds there, mostly Groq generation. On the free host the first token arrives in 2-5 seconds.
- **Local reranking on the free host:** the cross-encoder took about 90 seconds per question at 0.1 CPU, so reranking and embeddings moved to hosted APIs. Quality stayed equal within noise (table above).

## Why hosted APIs

I built the first version with local models and measured each retrieval step. To run it live for free (512 MB RAM, 0.1 CPU, no card) I moved embeddings and reranking to hosted free-tier APIs, re-ran the same evaluation, and added a BM25-only fallback for when an API is unavailable.

## Deployment

One Docker container on a Render free web service (Singapore region, 0.1 CPU, 512 MB RAM), built from the repo's root `Dockerfile`.

- `start.sh` runs rag-service on `127.0.0.1:8000` and Express on the public port; if either process exits, the container exits so Render restarts it.
- Four demo repos (express, cors, morgan, express-rate-limit) have their Gemini index baked into the image, so they use no API quota and survive every restart.
- MongoDB Atlas (free tier) stores users, chats and messages. Secrets are Render environment variables, never in the image.
- Measured: with the same limits locally the container peaked at 230 MB. On Render, a small new repo indexed in 8 s and a warm question streamed its first token in 2-5 s. After an idle sleep, the container restarted in about 20 s (Express up at 8 s, rag-service ready at 20 s), and a cold page load to first answer took about 30 s.

## Known limitations

- **Repos indexed by visitors are kept only until the service sleeps.** The free instance has no persistent disk, so after about 15 minutes idle they disappear and the chat asks you to index again (the chat history stays in MongoDB). The 4 demo repos always stay.
- **Shared free quotas.** Gemini's free tier allows about 1,000 embeddings a day for all visitors combined (each indexed chunk and each question uses one), so repos above 200 chunks are refused and indexing may be unavailable late in the day. Jina's free key has a limited one-time token balance and a non-commercial licence, fine for a portfolio demo. Groq free-plan limits apply.
- **Privacy:** indexing sends a repo's code chunks to Google Gemini for embeddings (on its free tier, Google may use inputs to improve its products). Each question goes to Gemini, and the question plus the retrieved chunks go to Jina (reranking) and Groq (the answer). Only public repos are supported, so no private code is involved.
- A few retrieval misses remain (right file, wrong chunk; one function split across chunks).
- Follow-up questions use a Groq rewrite call before retrieval, which can lower retrieval quality compared with a first question.
- Indexing job state and rate-limit counters are kept in memory and reset on restart. Only one repo is indexed at a time.
- The model sometimes writes full-width brackets in answers; those citations are not clickable (the Sources line still works).
- Only public GitHub repos are supported.

## Run it locally

You need Node 18+, Python 3.12, a MongoDB Atlas cluster, and free API keys for Groq, Gemini and Jina.

Create two `.env` files (never commit them):

- `server/.env`: `PORT`, `RAG_URL`, `MONGODB_URI`, `JWT_SECRET`
- `rag-service/.env`: `GROQ_API_KEY`, `GROQ_MODEL`, `GEMINI_API_KEY`, `JINA_API_KEY`, `REWRITE=0`

Install dependencies once:

```bash
cd rag-service
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd ../server && npm install
cd ../client && npm install
```

Then run each part in its own terminal:

```bash
cd rag-service
source .venv/bin/activate
EMBEDDER=gemini RERANKER=jina python -m uvicorn app.main:app --port 8000
```

```bash
cd server
npm run dev
```

```bash
cd client
npm run dev
```

Open `http://localhost:5173`, create an account, paste a GitHub repo URL and index it.

### Run the evaluation

Index the Express repo through the app first, then:

```bash
cd rag-service
source .venv/bin/activate
EMBEDDER=gemini RERANKER=jina python -m eval.run_eval express --label my_run
EMBEDDER=gemini RERANKER=jina python -m eval.run_eval express --label my_run --questions questions2.json
```

Add `NO_VECTOR=1` for the BM25-only run. A run only counts if the output has no "Jina rerank failed" lines.

### Run it as one container (like production)

From the repo root, with Docker running:

```bash
docker build -t codebase-assistant .
docker run -d --name ca1 -m 512m --memory-swap 512m --cpus 0.1 -p 8010:10000 \
  --env-file server/.env --env-file rag-service/.env \
  -e PORT=10000 -e RAG_URL=http://127.0.0.1:8000 codebase-assistant
```

Open `http://localhost:8010`. Values in the `.env` files must not be quoted for `--env-file`.
