import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime

from app.ask import retrieve
from app.config import CHUNK_OVERLAP, CHUNK_SIZE, REPOS_DIR, ROOT

EVAL_DIR = ROOT / "eval"


def preflight(questions, repo_dir):
    """Check that every expected file exists and the marker appears in one of them."""
    problems = []
    for q in questions:
        marker_found = False
        for f in q["expected_files"]:
            path = repo_dir / f
            if not path.exists():
                problems.append(f"{q['id']}: expected file not found: {f}")
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if q["marker"] in text:
                marker_found = True
        if not marker_found:
            problems.append(
                f"{q['id']}: marker {q['marker']!r} not in any expected file"
            )
    return problems


def score(q, docs):
    expected = set(q["expected_files"])
    hit_rank = None
    file_only = False
    for rank, d in enumerate(docs, 1):
        if d.metadata["file"] in expected:
            file_only = True
            if hit_rank is None and q["marker"] in d.page_content:
                hit_rank = rank
    retrieved_files = {d.metadata["file"] for d in docs}
    all_files = expected <= retrieved_files
    return hit_rank, file_only, all_files


def pct(n, total):
    return f"{n}/{total} ({100 * n / total:.0f}%)" if total else "n/a"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()

    questions = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))

    problems = preflight(questions, REPOS_DIR / args.repo)
    if problems:
        print("Preflight failed. Fix these before running the eval:")
        for p in problems:
            print("  ", p)
        sys.exit(1)

    rows = []
    for q in questions:
        docs = retrieve(args.repo, q["question"], args.k)
        hit_rank, file_only, all_files = score(q, docs)
        ranges = [
            f"{d.metadata['file']}:{d.metadata['start_line']}-{d.metadata['end_line']}"
            for d in docs
        ]
        rows.append(
            {
                "id": q["id"],
                "type": q["type"],
                "question": q["question"],
                "hit": hit_rank is not None,
                "rank": hit_rank,
                "file_only_hit": file_only,
                "all_files_found": all_files,
                "retrieved": ranges,
            }
        )
        status = (
            f"HIT@{hit_rank}" if hit_rank else ("file only" if file_only else "MISS")
        )
        print(f"{q['id']:<4} {q['type']:<9} {status:<10} {q['question'][:60]}")

    total = len(rows)
    hits = sum(r["hit"] for r in rows)
    file_hits = sum(r["file_only_hit"] for r in rows)
    mrr = sum(1 / r["rank"] for r in rows if r["rank"]) / total

    by_type = defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r)

    print(f"\n=== {args.label} | repo={args.repo} | k={args.k} ===")
    print(f"hit@{args.k} (file + marker): {pct(hits, total)}")
    print(f"file-only hit@{args.k}:       {pct(file_hits, total)}")
    print(f"MRR:                          {mrr:.3f}")
    for t, group in by_type.items():
        print(f"  {t:<9} hit: {pct(sum(r['hit'] for r in group), len(group))}")
    multi = by_type.get("multi", [])
    if multi:
        print(
            f"  multi all-files-found: {pct(sum(r['all_files_found'] for r in multi), len(multi))}"
        )

    print("\nMisses:")
    for r in rows:
        if not r["hit"]:
            print(f"  {r['id']}: {r['question']}")
            for rng in r["retrieved"]:
                print(f"      {rng}")

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_path = out_dir / f"{stamp}_{args.label}.json"
    out_path.write_text(
        json.dumps(
            {
                "label": args.label,
                "repo": args.repo,
                "k": args.k,
                "chunk_size": CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
                "hit_at_k": hits / total,
                "file_only_hit_at_k": file_hits / total,
                "mrr": mrr,
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
