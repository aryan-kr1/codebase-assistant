import uuid
import subprocess
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

import json
import logging
import os

from fastapi.responses import StreamingResponse
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq

from app.ask import PROMPT, RERANK_MODEL, format_context, retrieve

logger = logging.getLogger(__name__)

from app.config import get_embeddings
from app.ingest import ingest

jobs = {}  # job_id -> {"status", "url", "repo", "chunks", "error"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once at startup: load the heavy models and keep them in memory
    app.state.embeddings = get_embeddings()
    app.state.reranker = CrossEncoder(RERANK_MODEL)
    yield


app = FastAPI(lifespan=lifespan)


class IndexRequest(BaseModel):
    url: str


def run_index(job_id: str, url: str):
    jobs[job_id]["status"] = "running"
    try:
        repo, chunks = ingest(url, app.state.embeddings)
        jobs[job_id].update(status="done", repo=repo, chunks=chunks)
    except subprocess.CalledProcessError:
        logger.exception("clone failed for %s", url)
        jobs[job_id].update(
            status="failed",
            error="Could not clone the repository. Check the URL and that the repo is public.",
        )
    except Exception:
        logger.exception("indexing failed for %s", url)
        jobs[job_id].update(status="failed", error="Indexing failed.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/index")
def start_index(req: IndexRequest, background_tasks: BackgroundTasks):
    if not req.url.startswith("https://github.com/"):
        raise HTTPException(
            status_code=400, detail="Only https://github.com/ URLs are supported."
        )
    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "status": "queued",
        "url": req.url,
        "repo": None,
        "chunks": None,
        "error": None,
    }
    background_tasks.add_task(run_index, job_id, req.url)
    return {"job_id": job_id}


@app.get("/index/{job_id}")
def get_index(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return jobs[job_id]


class AskRequest(BaseModel):
    repo: str
    question: str


def sse(event: str, data) -> str:
    # data is JSON-encoded so newlines inside tokens don't break the SSE format
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/ask")
def ask(req: AskRequest):
    def stream():
        try:
            docs = retrieve(
                req.repo, req.question, 5, app.state.embeddings, app.state.reranker
            )
            llm = ChatGroq(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                temperature=0,
            )
            chain = PROMPT | llm | StrOutputParser()
            for token in chain.stream(
                {"context": format_context(docs), "question": req.question}
            ):
                yield sse("token", token)
            citations = [
                {
                    "file": d.metadata["file"],
                    "start_line": d.metadata["start_line"],
                    "end_line": d.metadata["end_line"],
                }
                for d in docs
            ]
            yield sse("citations", citations)
            yield sse("done", {})
        except Exception:
            logger.exception("ask failed for repo %s", req.repo)
            yield sse("error", "Something went wrong answering that question.")

    return StreamingResponse(stream(), media_type="text/event-stream")
