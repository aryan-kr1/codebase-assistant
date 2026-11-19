import os

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOS_DIR = ROOT / "data" / "repos"
EMBEDDER = os.getenv("EMBEDDER", "onnx")
_SUFFIX = "" if EMBEDDER == "onnx" else f"-{EMBEDDER}"
DB_DIR = ROOT / "data" / f"chroma{_SUFFIX}"
STATE_FILE = ROOT / "data" / f"index_state{_SUFFIX}.json"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

EXTS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
}
SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "vendor",
    "coverage",
    ".next",
    "test",
    "tests",
    "examples",
}
SKIP_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "History.md",
    "Readme.md",
    "CHANGELOG.md",
    "CHANGES.md",
}
MAX_FILE_BYTES = 200_000
MAX_CHUNKS = int(os.getenv("MAX_CHUNKS", "200" if EMBEDDER == "gemini" else "1000"))


def get_embeddings():
    if EMBEDDER == "gemini":
        from app.gemini_embed import GeminiEmbeddings

        return GeminiEmbeddings()
    from app.onnx_models import OnnxEmbeddings

    return OnnxEmbeddings()


def repo_name_from_url(url: str) -> str:
    return url.rstrip("/").removesuffix(".git").split("/")[-1]
