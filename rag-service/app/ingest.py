import json
import os

import chromadb

import shutil
import subprocess
import sys

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DB_DIR,
    EXTS,
    MAX_FILE_BYTES,
    REPOS_DIR,
    SKIP_DIRS,
    SKIP_FILES,
    get_embeddings,
    repo_name_from_url,
)

STATE_FILE = REPOS_DIR.parent / "index_state.json"  # data/index_state.json


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def remote_head(url: str) -> str:
    # Latest commit on the remote, without downloading the repo
    out = subprocess.run(
        ["git", "ls-remote", url, "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    ).stdout.split()
    if not out:
        raise RuntimeError(f"No HEAD found for {url}")
    return out[0]


def local_head(root) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def indexed_count(name: str) -> int:
    try:
        client = chromadb.PersistentClient(path=str(DB_DIR))
        return client.get_collection(name).count()
    except Exception:
        return 0


def clone(url: str):
    name = repo_name_from_url(url)
    dest = REPOS_DIR / name
    if dest.exists():
        shutil.rmtree(dest)
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True)
    return name, dest


def iter_files(root):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.name in SKIP_FILES or p.suffix not in EXTS:
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            continue
        yield p


def chunk_repo(root):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True
    )
    chunks = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(root).as_posix()
        for doc in splitter.create_documents([text], metadatas=[{"file": rel}]):
            start = doc.metadata["start_index"]
            doc.metadata["start_line"] = text.count("\n", 0, start) + 1
            doc.metadata["end_line"] = doc.metadata[
                "start_line"
            ] + doc.page_content.count("\n")

            chunks.append(doc)
    return chunks


def ingest(url: str, embeddings=None, force: bool = False):
    name = repo_name_from_url(url)
    state = load_state()

    # Skip everything if the remote has not changed since the last index
    if not force and state.get(name) == remote_head(url):
        count = indexed_count(name)
        if count > 0 and (REPOS_DIR / name).exists():
            print(f"{name}: unchanged, skipping ({count} chunks)")
            return name, count

    # Forget the old hash first, so a failed rebuild is never marked as up to date
    state.pop(name, None)
    save_state(state)

    embeddings = embeddings or get_embeddings()
    name, root = clone(url)
    head = local_head(root)
    chunks = chunk_repo(root)
    print(f"{name}: {len(chunks)} chunks")

    store = Chroma(
        collection_name=name,
        embedding_function=embeddings,
        persist_directory=str(DB_DIR),
    )
    store.delete_collection()  # re-index from scratch
    store = Chroma(
        collection_name=name,
        embedding_function=embeddings,
        persist_directory=str(DB_DIR),
    )
    for i in range(0, len(chunks), 500):
        store.add_documents(chunks[i : i + 500])

    state[name] = head
    save_state(state)
    print("Done. Indexed as:", name)
    return name, len(chunks)


if __name__ == "__main__":
    ingest(sys.argv[1], force="--force" in sys.argv)
