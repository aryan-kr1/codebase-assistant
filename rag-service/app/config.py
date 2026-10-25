from pathlib import Path
from langchain_huggingface import HuggingFaceEmbeddings

ROOT = Path(__file__).resolve().parent.parent
REPOS_DIR = ROOT / "data" / "repos"
DB_DIR = ROOT / "data" / "chroma"

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
}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
MAX_FILE_BYTES = 200_000


def get_embeddings():
    # Local and free. The first run downloads ~90MB.
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def repo_name_from_url(url: str) -> str:
    return url.rstrip("/").removesuffix(".git").split("/")[-1]
