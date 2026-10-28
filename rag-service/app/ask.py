import os
import sys

from sentence_transformers import CrossEncoder

import re
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from app.config import DB_DIR, get_embeddings

load_dotenv()

PROMPT = ChatPromptTemplate.from_template(
    """You answer questions about a codebase using ONLY the context below.
Cite sources inline in exactly this form: [path/to/file.js:10-42]
Rules for citations:
- Use square brackets and a plain hyphen (-) between the line numbers.
- Never use a non-breaking hyphen, en dash, or any other bracket character.
- Copy the path and line numbers exactly as they appear in the context headers.
If the context is not enough, say so.

Context:
{context}

{history}Question: {question}"""
)


POOL = 20
RRF_C = 60
CANDIDATES = 20
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def tokenize(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())


REWRITE_PROMPT = ChatPromptTemplate.from_template(
    "Rewrite this question about a codebase as a short search query: "
    "include likely function names, file names and keywords. "
    "Output only the query.\n\nQuestion: {question}"
)


def rewrite_query(question: str) -> str:
    llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), temperature=0
    )
    chain = REWRITE_PROMPT | llm | StrOutputParser()
    return chain.invoke({"question": question}).strip()


def format_history(history, limit=500):
    lines = []
    for m in history:
        role = "User" if m["role"] == "user" else "Assistant"
        content = m["content"]
        if len(content) > limit:
            content = content[:limit] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


STANDALONE_PROMPT = ChatPromptTemplate.from_template(
    "Given the conversation about a codebase and a follow-up question, "
    "rewrite the follow-up as one standalone question that makes sense "
    "without the conversation. If it is already standalone, return it "
    "unchanged. Output only the question.\n\n"
    "Conversation:\n{history}\n\nFollow-up: {question}"
)


def standalone_question(history, question: str) -> str:
    llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), temperature=0
    )
    chain = STANDALONE_PROMPT | llm | StrOutputParser()
    return chain.invoke(
        {"history": format_history(history), "question": question}
    ).strip()


def retrieve(repo: str, question: str, k: int = 5, embeddings=None, reranker=None):
    store = Chroma(
        collection_name=repo,
        embedding_function=embeddings or get_embeddings(),
        persist_directory=str(DB_DIR),
    )

    search_q = rewrite_query(question) if os.getenv("REWRITE", "0") == "1" else question

    # vector top 20
    vec_docs = store.similarity_search(search_q, k=POOL)

    # BM25 top 20 over all chunks in the collection
    data = store.get()
    all_docs = [
        Document(page_content=t, metadata=m)
        for t, m in zip(data["documents"], data["metadatas"])
    ]
    bm25 = BM25Okapi([tokenize(d.page_content) for d in all_docs])
    scores = bm25.get_scores(tokenize(search_q))
    top = sorted(range(len(all_docs)), key=lambda i: scores[i], reverse=True)[:POOL]
    bm25_docs = [all_docs[i] for i in top]

    # Reciprocal Rank Fusion
    fused = {}
    by_key = {}
    for ranked in (vec_docs, bm25_docs):
        for rank, d in enumerate(ranked, start=1):
            key = (d.metadata["file"], d.metadata["start_line"], d.metadata["end_line"])
            by_key[key] = d
            fused[key] = fused.get(key, 0) + 1 / (RRF_C + rank)

    best = sorted(fused, key=fused.get, reverse=True)[:CANDIDATES]
    candidates = [by_key[key] for key in best]

    # rerank against the ORIGINAL question
    reranker = reranker or CrossEncoder(RERANK_MODEL)
    scores = reranker.predict([(question, d.page_content) for d in candidates])
    order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    return [candidates[i] for i in order[:k]]


def format_context(docs):
    return "\n\n".join(
        f"[{d.metadata['file']}:{d.metadata['start_line']}-{d.metadata['end_line']}]\n{d.page_content}"
        for d in docs
    )


def answer(repo: str, question: str, k: int = 5):
    docs = retrieve(repo, question, k)
    llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), temperature=0
    )
    chain = PROMPT | llm | StrOutputParser()
    return (
        chain.invoke(
            {"context": format_context(docs), "history": "", "question": question}
        ),
        docs,
    )


if __name__ == "__main__":
    repo, question = sys.argv[1], sys.argv[2]
    text, docs = answer(repo, question)
    print(text)
    print("\nRetrieved:")
    for d in docs:
        print(
            f"  {d.metadata['file']}:{d.metadata['start_line']}-{d.metadata['end_line']}"
        )
