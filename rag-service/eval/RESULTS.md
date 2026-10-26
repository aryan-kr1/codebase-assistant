| Run             | Change                                      | hit@5 | file-only@5 | MRR   |
| --------------- | ------------------------------------------- | ----- | ----------- | ----- |
| baseline        | naive chunks, vector search                 | 30%   | 55%         | 0.145 |
| path_filter     | Path-based filtering                        | 60%   | 90%         | 0.414 |
| syntax_chunking | Syntax-aware chunking                       | 55%   | 90%         | 0.377 |
| hybrid          | BM25 + Vector Search + RRF                  | 70%   | 95%         | 0.529 |
| rerank          | Hybrid search + cross-encoder reranking     | 85%   | 95%         | 0.693 |
| rewrite         | Query rewriting + hybrid search + reranking | 85%   | 95%         | 0.693 |
