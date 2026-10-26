| Run             | Change                      | hit@5 | file-only@5 | MRR   |
| --------------- | --------------------------- | ----- | ----------- | ----- |
| baseline        | naive chunks, vector search | 30%   | 55%         | 0.145 |
| path_filter     | Path-based filtering        | 60%   | 90%         | 0.414 |
| syntax_chunking | Syntax-aware chunking       | 55%   | 90%         | 0.377 |
