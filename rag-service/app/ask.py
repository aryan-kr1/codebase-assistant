import os
import sys

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from app.config import DB_DIR, get_embeddings

load_dotenv()

PROMPT = ChatPromptTemplate.from_template(
    """You answer questions about a codebase using ONLY the context below.
Cite sources inline like [path/to/file.js:10-42]. If the context is not enough, say so.

Context:
{context}

Question: {question}"""
)


def retrieve(repo: str, question: str, k: int = 5):
    store = Chroma(
        collection_name=repo,
        embedding_function=get_embeddings(),
        persist_directory=str(DB_DIR),
    )
    return store.similarity_search(question, k=k)


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
    return chain.invoke({"context": format_context(docs), "question": question}), docs


if __name__ == "__main__":
    repo, question = sys.argv[1], sys.argv[2]
    text, docs = answer(repo, question)
    print(text)
    print("\nRetrieved:")
    for d in docs:
        print(
            f"  {d.metadata['file']}:{d.metadata['start_line']}-{d.metadata['end_line']}"
        )
