# Evaluation results

Last updated: Nov 20 2026.

## How the evaluation works

- Repo: expressjs/express, k=5, chunk size 1000 / overlap 150.
- `questions.json`: 20 hand-written questions used for tuning. `questions2.json`: 20 held-out questions written after tuning and never tuned on. Each set has only 20 questions, so one question is 5 points.
- **hit@5:** a retrieved chunk from an expected file that also contains the expected marker. **file-only@5:** an expected file appears in the top 5 (marker not required). **MRR:** mean reciprocal rank of the first hit.
- Rules: settings are fixed before each run, each run changes one thing, every run is recorded (including failures), and a run counts only if its log has 0 "Jina rerank failed" lines (and 0 Gemini retries unless stated). Raw results are in `rag-service/eval/results/`.

## 1. Final results (the setup the live demo runs)

Same pipeline (path filter + hybrid + rerank), different models. Format: hit@5 / file-only@5 / MRR.

| Setup                                              | Tuned set            | Held-out set        |
| -------------------------------------------------- | -------------------- | ------------------- |
| **Jina rerank + Gemini embeddings (the demo)**     | 90% / 100% / 0.900   | 100% / 100% / 0.950 |
| Same, BM25 only (fallback when Gemini is down)     | 100% / 100% / 0.8375 | 100% / 100% / 0.975 |
| Jina rerank + local MiniLM embeddings              | 95% / 100% / 0.827   | 100% / 100% / 0.950 |
| Local cross-encoder + local MiniLM (first version) | 85% / 95% / 0.693    | 95% / 100% / 0.817  |

How to read it:

- The differences between the hosted setups are within noise ("equal within noise", not "better").
- The held-out set is saturated at 100% for the hosted setups, so it can no longer separate them. The next honest test needs a fresh third question set, ideally conceptual questions on a second repo.
- BM25-only is as good as hybrid here because most questions name an exact identifier (`res.json`, `trust proxy`), which favours BM25. It does not show vector search is useless; conceptual questions are untested.

## 2. Baked demo repos

Four repos have their Gemini index baked into the image (`rag-service/demo-data/`, 17 MB, 426 files), so they cost 0 embedding quota and survive every restart.

| Repo               | Chunks |
| ------------------ | ------ |
| express            | 107    |
| cors               | 44     |
| morgan             | 67     |
| express-rate-limit | 130    |

If one of these repos gets a new upstream commit, a visitor who indexes it triggers a real re-index (costs Gemini quota and must fit MAX_CHUNKS).

## 3. Free-host measurements

### 3a. One container in Docker on a Mac (`-m 512m --memory-swap 512m --cpus 0.1`)

| Measurement                                   | Result                                                                                                            |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Express answering                             | 45 s after start                                                                                                  |
| rag-service `/health` ready                   | 115 s                                                                                                             |
| Peak memory                                   | 230 MB (anon 164 MB, file cache 50 MB), OOMKilled=false                                                           |
| Register / login (secure cookie)              | worked                                                                                                            |
| Index cors (44 chunks) with Gemini embeddings | 30 s                                                                                                              |
| First token                                   | 4 s after sending a question                                                                                      |
| Citation click                                | opened the code panel                                                                                             |
| Retrieval stages (cumulative)                 | open 0.1 s, vector 1.3 s (incl. Gemini query embedding), fetch 1.4 s, BM25 1.5 s, fusion 1.5 s, Jina rerank 3.0 s |
| Baked morgan "index" request                  | "unchanged, skipping (67 chunks)", 15.6 s, 0 Gemini requests                                                      |
| Baked morgan question                         | 570 token events, 0 errors, 13.8 s for the whole stream                                                           |

### 3b. Render free instance (Singapore, 0.1 CPU, 512 MB RAM), Nov 20 2026

| Measurement                                              | Result                                                                                  |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| First deploy (build and start)                           | 1m35s                                                                                   |
| Register / login over HTTPS                              | worked                                                                                  |
| Question on baked repo (morgan), right after deploy      | first token 5 s, citations open, no errors                                              |
| Index a new small repo (cookie-parser) with Gemini       | 8 s                                                                                     |
| Question on that repo                                    | first token 2 s, citation opened                                                        |
| After about 3 hours idle: page load                      | under 22 s                                                                              |
| After the sleep: first token on a morgan question        | about 8 s after the page loaded (about 30 s in total)                                   |
| After the sleep: index cookie-parser again / first token | 8 s / 4 s                                                                               |
| Container restart in the Render logs (a later wake-up)   | Express up at 8 s, rag-service ready at 20 s                                            |
| Visitor-indexed repo after a sleep                       | gone: "This repo isn't indexed yet. Index it first."; the chat history stays in MongoDB |
| Baked repos after a sleep                                | still answer                                                                            |

The Render cold start (20 s to ready) was much faster than the Docker test (115 s), so the local `--cpus 0.1` test was pessimistic.

## 4. How retrieval improved (first version, local models)

Measured one change at a time, with local MiniLM embeddings and a local cross-encoder.

### Tuned set (questions.json), Express

| Run             | Change                                      | hit@5 | file-only@5 | MRR   |
| --------------- | ------------------------------------------- | ----- | ----------- | ----- |
| baseline        | naive chunks, vector search                 | 30%   | 55%         | 0.145 |
| path_filter     | Path-based filtering                        | 60%   | 90%         | 0.414 |
| syntax_chunking | Syntax-aware chunking                       | 55%   | 90%         | 0.377 |
| hybrid          | BM25 + Vector Search + RRF                  | 70%   | 95%         | 0.529 |
| rerank          | Hybrid search + cross-encoder reranking     | 85%   | 95%         | 0.693 |
| rewrite         | Query rewriting + hybrid search + reranking | 85%   | 95%         | 0.693 |

### Held-out set (questions2.json, 20 new Express questions, not tuned on)

| Run                 | Setup                                           | hit@5 | file-only@5 | MRR   |
| ------------------- | ----------------------------------------------- | ----- | ----------- | ----- |
| heldout-rewrite-on  | path filter + hybrid + rerank + query rewriting | 95%   | 100%        | 0.825 |
| heldout-rewrite-off | path filter + hybrid + rerank (final setup)     | 95%   | 100%        | 0.817 |

## 5. Detailed runs with hosted services (Nov 2026)

Settings were fixed before each run; only the named component changed.

### Tuned set (questions.json), Express

| Run                                       | Reranker                | Embedder                    | hit@5 | file-only@5 | MRR   |
| ----------------------------------------- | ----------------------- | --------------------------- | ----- | ----------- | ----- |
| rerank (PyTorch, and identical with ONNX) | local cross-encoder     | local MiniLM                | 85%   | 95%         | 0.693 |
| jina-tuned                                | Jina (jina-reranker-v3) | local ONNX MiniLM           | 95%   | 100%        | 0.827 |
| gemini-tuned                              | Jina                    | Gemini (gemini-embedding-2) | 90%   | 100%        | 0.900 |

### Held-out set (questions2.json), Express

| Run                                                                      | Reranker            | Embedder          | hit@5 | file-only@5 | MRR   |
| ------------------------------------------------------------------------ | ------------------- | ----------------- | ----- | ----------- | ----- |
| ONNX / PyTorch (identical)                                               | local cross-encoder | local MiniLM      | 95%   | 100%        | 0.817 |
| jina-heldout (not clean: 1 Jina timeout, fell back to hybrid order once) | Jina                | local ONNX MiniLM | 100%  | 100%        | 0.950 |
| jina-heldout-2 (valid: 0 failures, 0 retries)                            | Jina                | local ONNX MiniLM | 100%  | 100%        | 0.950 |
| gemini-heldout (valid: 0 failures, 0 retries)                            | Jina                | Gemini            | 100%  | 100%        | 0.950 |

Notes:

- Jina improved both sets (tuned +2 questions, held-out +1). Gemini embeddings are equal to local embeddings within noise: tuned -1 question (a new miss on Q20, ETags, right files but wrong chunk range), held-out identical.
- Known misses: tuned Q8 (package.json, wrong chunk range) in every hybrid run (it hit at rank 4 with BM25 only); Q10 and Q18 fixed by Jina.
- Jina rerank free tier: 10M one-time tokens, about 5K tokens per question. Non-commercial license, fine for a portfolio demo.
- Gemini embeddings free tier: 100 requests/min, 30K tokens/min, 1,000 requests/day. Measured: a batch of N texts counts as N requests, and a 1000-character chunk is about 300 tokens. Indexing express (107 chunks) uses about 11% of the daily quota. Free-tier content may be used by Google to improve its products.

## 6. Engineering notes

### ONNX swap (fastembed, same MiniLM weights)

Quality unchanged vs PyTorch (tuned 85/95/0.693, held-out 95/100/0.817). Every repo must be re-indexed after the swap because the vectors differ slightly.

| Measurement                                    | Result                                                 |
| ---------------------------------------------- | ------------------------------------------------------ |
| Mac process footprint, PyTorch                 | 1483 MB                                                |
| Docker, 512 MB cap, ONNX, idle (models loaded) | about 297 MiB                                          |
| Docker, indexing axios (2036 chunks)           | about 4 min, peak 512 MiB (at the cap), not OOM-killed |

### CPU timing in Docker (Render free = 0.1 CPU; `--cpus` is an approximation)

| Test                                          | 0.5 CPU      | 0.1 CPU                        |
| --------------------------------------------- | ------------ | ------------------------------ |
| Index express, before `threads=1`             | 4m41s        | did not finish in 11+ min      |
| Index express, after `threads=1` (local ONNX) | about 18 s   | 7m19s                          |
| Question, local CPU reranker                  | 6.1 s        | 1m28s                          |
| Rerank stage alone                            | 4.4 s        | about 90 s                     |
| Question, Jina reranker                       | not measured | first token 6.3 s, done 12.9 s |

Cost of CPU reranking is linear (about 4.4 s per candidate chunk at 0.1 CPU), so trimming candidates would not make it viable. Hosted reranking fixed it. Cold start to /health at 0.1 CPU in that test: 84 to 90 s.

### Chunk cap

MAX_CHUNKS (default 1000) refuses oversized repos before embedding. axios (2036 chunks) is refused, express (107) indexes. The limit is a judgment call, not measured. With Gemini embeddings the default is 200 (about 20% of the daily embedding quota per repo); with local ONNX it stays 1000.

### Gemini quota handling and BM25-only fallback

If the embedding call fails (quota used up or service down), `retrieve()` skips vector search and uses BM25 + Jina rerank only. Question embeddings give up after 2 attempts so users do not wait a minute. `NO_VECTOR=1` forces this mode for testing. Run with 0 Jina failures.

| Setup (Jina rerank)           | Tuned hit@5 | file-only | MRR    | Held-out hit@5 | file-only | MRR   |
| ----------------------------- | ----------- | --------- | ------ | -------------- | --------- | ----- |
| Hybrid, local ONNX embeddings | 95%         | 100%      | 0.827  | 100%           | 100%      | 0.950 |
| Hybrid, Gemini embeddings     | 90%         | 100%      | 0.900  | 100%           | 100%      | 0.950 |
| BM25 only (degraded mode)     | 100%        | 100%      | 0.8375 | 100%           | 100%      | 0.975 |

Notes:

- Degraded mode is as good as hybrid on these sets. This does not show vector search is useless: both sets are 20 Express questions and most name an exact identifier, which favours BM25. Conceptual questions (no identifier in the query) are untested; they need a fresh third question set, ideally on a second repo.
- Three tuned hits are at rank 4 (Q8, Q18, Q20), hence MRR 0.8375 with a 100% hit rate.
- Indexing protections: one index job at a time, MAX_CHUNKS 200 with Gemini, and a failed index run deletes its half-filled collection. A quota failure shows a friendly message. The 429 path was not tested live.
