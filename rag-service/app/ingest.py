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


def main(url: str):
    name, root = clone(url)
    chunks = chunk_repo(root)
    print(f"{name}: {len(chunks)} chunks")

    store = Chroma(
        collection_name=name,
        embedding_function=get_embeddings(),
        persist_directory=str(DB_DIR),
    )
    store.delete_collection()  # re-index from scratch
    store = Chroma(
        collection_name=name,
        embedding_function=get_embeddings(),
        persist_directory=str(DB_DIR),
    )
    for i in range(0, len(chunks), 500):
        store.add_documents(chunks[i : i + 500])
    print("Done. Indexed as:", name)


if __name__ == "__main__":
    main(sys.argv[1])
