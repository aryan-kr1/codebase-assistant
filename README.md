# Codebase Q&A Assistant

Paste a public GitHub repo URL, let the app index the code, then ask questions in plain English. Answers stream in live and cite the exact files and line ranges they used. Click a citation to open the real code.

> Live demo: _coming soon_  
> Demo video: _coming soon_

## What it does

- Index any public GitHub repo (one chat per repo, re-indexing reuses it).
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

Stack: LangChain, Groq (`llama-3.3-70b-versatile`), local MiniLM embeddings (`all-MiniLM-L6-v2`), Chroma (on local disk), MongoDB Atlas (users, chats, messages).

Flow: the browser talks to Express, which checks the login cookie and rate limits, then forwards to rag-service. Answers stream back as server-sent events and the finished answer is saved to MongoDB.

## How retrieval works

1. **Path filter:** skip tests, examples, changelogs and similar files before indexing.
2. **Hybrid search:** vector search and BM25 each return their top 20 chunks.
3. **Reciprocal Rank Fusion** merges the two lists.
4. **Cross-encoder rerank** (`ms-marco-MiniLM-L-6-v2`) re-scores the top 20 against the original question and keeps the top 5.

The 5 chunks go to the LLM, which must cite them as `[path/to/file.js:10-42]`.

## Results

Evaluated on the Express repo with 20 hand-written questions (8 lookup, 8 behavior, 4 multi-file), k=5, chunk size 1000 / overlap 150. A hit means a retrieved chunk from an expected file that also contains the expected marker.

| Run             | Change                                       | hit@5 | file-only@5 | MRR   |
| --------------- | -------------------------------------------- | ----- | ----------- | ----- |
| baseline        | naive chunks, vector only                    | 30%   | 55%         | 0.145 |
| path_filter     | skip test/examples/history/readme/changelogs | 60%   | 90%         | 0.414 |
| syntax_chunking | language-aware splitters on top              | 55%   | 90%         | 0.377 |
| hybrid          | BM25 + vectors + RRF                         | 70%   | 95%         | 0.529 |
| rerank          | + cross-encoder rerank                       | 85%   | 95%         | 0.693 |
| rewrite         | + query rewriting                            | 85%   | 95%         | 0.693 |

Each change was measured on its own, with settings fixed before the run. Every run, including the failed ones, is recorded in `rag-service/eval/RESULTS.md`.

**Held-out check.** I wrote 20 new questions after tuning and never tuned on them. With the final setup (path filter + hybrid + rerank, no rewriting): hit@5 95% (19/20), file-only 100%, MRR 0.817. So the setup did not overfit to the first 20 questions.

**Caveat:** the held-out set is easier (many "where is X defined?" lookups), so 95% does not mean it beats 85%. The honest claim is 85% on the tuned set and 95% on a held-out set with the same setup.

### What did not work

- **Syntax-aware chunking** scored lower than the simple splitter (55% vs 60%), so I reverted it.
- **Query rewriting** gave no gain on either question set, so it is off by default (`REWRITE=1` turns it on). My rule was to keep it only if it won by 2+ questions.
- **Caching:** measured, not needed. A full answer takes about 2-3 seconds, mostly Groq generation, so the retrieval side is not a bottleneck.

## Known limitations

- A few retrieval misses remain: one question where `package.json` is crowded out by `.github/workflows` chunks, two where the right file is found but the wrong chunk, and one function split across chunks.
- Indexing job state and rate-limit counters are kept in memory, so they reset when a server restarts.
- The model sometimes writes full-width brackets in answers; those citations are not clickable (the Sources line still works).
- Groq free-plan limits apply (tokens per minute is the real limit), so heavy use will be throttled.
- Only public GitHub repos are supported.

## Run it locally

You need Node 18+, Python 3.10+, a MongoDB Atlas cluster and a Groq API key.

Create two `.env` files (never commit them):

- `server/.env`: `PORT`, `RAG_URL`, `MONGODB_URI`, `JWT_SECRET`
- `rag-service/.env`: `GROQ_API_KEY`, `GROQ_MODEL`, `REWRITE=0`

Install dependencies once:

```bash
cd rag-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ../server && npm install
cd ../client && npm install
```

Then run each part in its own terminal:

```bash
cd rag-service
source .venv/bin/activate
uvicorn app.main:app --port 8000
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

```bash
cd rag-service
python -m eval.run_eval express --label my_run
python -m eval.run_eval express --label my_run --questions questions2.json
```

## Deployment

_To be added._
