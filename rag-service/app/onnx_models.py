from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from langchain_core.embeddings import Embeddings

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class OnnxEmbeddings(Embeddings):
    def __init__(self):
        self.model = TextEmbedding(model_name=EMBED_MODEL)

    def embed_documents(self, texts):
        return [v.tolist() for v in self.model.embed(texts)]

    def embed_query(self, text):
        return next(iter(self.model.embed([text]))).tolist()


class OnnxReranker:
    # Same predict() shape as sentence-transformers CrossEncoder,
    # so ask.py's retrieve() code does not change.
    def __init__(self):
        self.model = TextCrossEncoder(model_name=RERANK_MODEL)

    def predict(self, pairs):
        query = pairs[0][0]
        docs = [p[1] for p in pairs]
        return list(self.model.rerank(query, docs))
