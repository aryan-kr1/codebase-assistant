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

## Hosted services and free-host measurements (Nov 2026)

Settings were fixed before each run; only the named component changed. A run counts only if the log has 0 "Jina rerank failed" lines.

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

- Each set has only 20 questions, so one question is 5 points. Jina improved both sets (tuned +2 questions, held-out +1). Gemini embeddings are equal to local embeddings within noise: tuned -1 question (a new miss on Q20, ETags, right files but wrong chunk range), held-out identical.
- The held-out set is saturated (100%). The next honest test needs a fresh third question set.
- Known misses: tuned Q8 (package.json, wrong chunk range) in every run; Q10 and Q18 fixed by Jina.
- Jina rerank free tier: 10M one-time tokens, about 5K tokens per question. Non-commercial license, fine for a portfolio demo.
- Gemini embeddings free tier: 100 requests/min, 30K tokens/min, 1,000 requests/day. Measured: a batch of N texts counts as N requests, and a 1000-character chunk is about 300 tokens. Indexing express (107 chunks) uses about 11% of the daily quota. Free-tier content may be used by Google to improve its products.

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

Cost of CPU reranking is linear (about 4.4 s per candidate chunk at 0.1 CPU), so trimming candidates would not make it viable. Hosted reranking fixed it. Cold start to /health at 0.1 CPU: 84 to 90 s.

### Chunk cap

MAX_CHUNKS (default 1000) refuses oversized repos before embedding. axios (2036 chunks) is refused, express (107) indexes. The limit is a judgment call, not measured. With Gemini embeddings it should be lowered (planned: about 200).
