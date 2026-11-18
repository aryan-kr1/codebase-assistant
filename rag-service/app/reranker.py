import logging
import os
import time

import httpx

log = logging.getLogger("reranker")

JINA_URL = "https://api.jina.ai/v1/rerank"
TIMEOUT_S = 10
ATTEMPTS = 2


class JinaReranker:
    """Same predict(pairs) -> scores interface as OnnxReranker.
    Tries the call twice; if both fail, returns scores that keep the incoming (hybrid) order."""

    def predict(self, pairs):
        if not pairs:
            return []
        query = pairs[0][0]
        docs = [p[1] for p in pairs]
        fallback = [float(len(docs) - i) for i in range(len(docs))]
        key = os.getenv("JINA_API_KEY")
        if not key:
            log.warning("JINA_API_KEY missing; using hybrid order")
            return fallback
        last_error = None
        for attempt in range(1, ATTEMPTS + 1):
            try:
                r = httpx.post(
                    JINA_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": os.getenv("JINA_RERANK_MODEL", "jina-reranker-v3"),
                        "query": query,
                        "documents": docs,
                        "top_n": len(docs),
                    },
                    timeout=TIMEOUT_S,
                )
                r.raise_for_status()
                out = list(fallback)
                for item in r.json()["results"]:
                    out[item["index"]] = float(item["relevance_score"])
                return out
            except Exception as e:
                last_error = e
                if attempt < ATTEMPTS:
                    log.warning("Jina rerank retry (%s)", e)
                    time.sleep(1)
        log.warning("Jina rerank failed (%s); using hybrid order", last_error)
        return fallback


def get_reranker():
    if os.getenv("RERANKER", "onnx") == "jina":
        return JinaReranker()
    from app.onnx_models import OnnxReranker

    return OnnxReranker()
