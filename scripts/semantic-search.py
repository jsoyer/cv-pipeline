#!/usr/bin/env python3
"""
Semantic search — find similar CV bullets, jobs, and applications using TF-IDF cosine similarity.

No API key or external ML library required. Uses stdlib only.

Modes:
  bullets  : find CV bullets similar to a query string
  jobs     : rank past applications by similarity to a new job description
  keywords : find applications with overlapping keywords

Usage:
    scripts/semantic-search.py bullets "led cross-functional team to deliver"
    scripts/semantic-search.py jobs applications/2026-03-newco/job.txt
    scripts/semantic-search.py keywords "python api kubernetes"
    make semantic QUERY="..."
    make semantic MODE=jobs NAME=2026-03-newco
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT, STOP_WORDS

# ---------------------------------------------------------------------------
# TF-IDF helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stop words."""
    tokens = re.findall(r"\b[a-z][a-z0-9]{1,}\b", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 2]


def _tf(tokens: list[str]) -> dict[str, float]:
    """Term frequency (normalized)."""
    counts = Counter(tokens)
    total = max(len(tokens), 1)
    return {t: c / total for t, c in counts.items()}


def _build_idf(documents: list[list[str]]) -> dict[str, float]:
    """Inverse document frequency over a corpus."""
    n = len(documents)
    df: Counter = Counter()
    for doc in documents:
        for term in set(doc):
            df[term] += 1
    return {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}


def _tfidf_vec(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    tf = _tf(tokens)
    return {t: tf[t] * idf.get(t, 1.0) for t in tf}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _bar(score: float, width: int = 20) -> str:
    filled = max(0, min(width, int(score * width)))
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def load_cv_bullets(cv_path: Path) -> list[dict]:
    """Extract all bullet points from cv.yml with their context."""
    data = yaml.safe_load(cv_path.read_text(encoding="utf-8")) or {}
    bullets = []

    for exp in data.get("experience", []):
        company = exp.get("company", "")
        role = exp.get("position", "")
        for item in exp.get("items", []):
            text = item.get("text", item.get("label", "")) if isinstance(item, dict) else str(item)
            if text:
                bullets.append({"text": text, "context": f"{role} @ {company}", "section": "experience"})

    for section in ("projects", "volunteer"):
        for entry in data.get(section, []):
            for item in entry.get("items", []):
                text = item.get("text", item.get("label", "")) if isinstance(item, dict) else str(item)
                if text:
                    bullets.append({"text": text, "context": entry.get("name", section), "section": section})

    return bullets


def load_applications(apps_dir: Path) -> list[dict]:
    """Load all applications with job descriptions."""
    apps = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.yml"
        job_path = d / "job.txt"
        if not meta_path.exists():
            continue
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        job_text = job_path.read_text(encoding="utf-8") if job_path.exists() else ""
        apps.append(
            {
                "name": d.name,
                "company": meta.get("company", d.name),
                "position": meta.get("position", ""),
                "outcome": meta.get("outcome", "applied"),
                "provider": meta.get("tailor_provider", ""),
                "text": job_text,
            }
        )
    return apps


# ---------------------------------------------------------------------------
# Search modes
# ---------------------------------------------------------------------------


def search_bullets(query: str, cv_path: Path, top_n: int = 10) -> list[dict]:
    """Find CV bullets most similar to query."""
    bullets = load_cv_bullets(cv_path)
    if not bullets:
        return []

    corpus = [_tokenize(b["text"]) for b in bullets]
    query_tokens = _tokenize(query)
    all_docs = corpus + [query_tokens]

    idf = _build_idf(all_docs)
    query_vec = _tfidf_vec(query_tokens, idf)

    results = []
    for i, bullet in enumerate(bullets):
        vec = _tfidf_vec(corpus[i], idf)
        score = _cosine(query_vec, vec)
        results.append({**bullet, "score": round(score, 4)})

    results.sort(key=lambda x: -x["score"])
    return results[:top_n]


def search_jobs(query_text: str, apps_dir: Path, top_n: int = 10) -> list[dict]:
    """Rank past job applications by similarity to query text."""
    apps = [a for a in load_applications(apps_dir) if a["text"]]
    if not apps:
        return []

    corpus = [_tokenize(a["text"]) for a in apps]
    query_tokens = _tokenize(query_text)
    all_docs = corpus + [query_tokens]

    idf = _build_idf(all_docs)
    query_vec = _tfidf_vec(query_tokens, idf)

    results = []
    for i, app in enumerate(apps):
        vec = _tfidf_vec(corpus[i], idf)
        score = _cosine(query_vec, vec)
        results.append({**app, "score": round(score, 4), "text": app["text"][:200]})

    results.sort(key=lambda x: -x["score"])
    return results[:top_n]


def search_keywords(query: str, apps_dir: Path, top_n: int = 10) -> list[dict]:
    """Find applications with highest keyword overlap with query."""
    query_kws = set(_tokenize(query))
    apps = load_applications(apps_dir)

    results = []
    for app in apps:
        app_kws = set(_tokenize(app["text"] + " " + app["position"]))
        overlap = query_kws & app_kws
        score = len(overlap) / max(len(query_kws), 1)
        results.append(
            {
                **app,
                "score": round(score, 4),
                "matched_keywords": sorted(overlap),
                "text": "",
            }
        )

    results.sort(key=lambda x: -x["score"])
    return results[:top_n]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_bullets(results: list[dict], query: str) -> None:
    print(f'\n🔍 Bullets similar to: "{query}"\n')
    if not results:
        print("  No results.")
        return
    for r in results:
        bar = _bar(r["score"])
        print(f"  {r['score']:.3f}  {bar}  [{r['context']}]")
        print(f"         {r['text'][:90]}")
    print()


def print_jobs(results: list[dict], label: str) -> None:
    print(f"\n🔍 Applications similar to: {label}\n")
    if not results:
        print("  No results.")
        return
    for r in results:
        bar = _bar(r["score"])
        outcome = f" ({r['outcome']})" if r.get("outcome") else ""
        print(f"  {r['score']:.3f}  {bar}  {r['name']}{outcome}")
        print(f"         {r['company']} — {r['position']}")
    print()


def print_keywords(results: list[dict], query: str) -> None:
    print(f'\n🔍 Keyword matches for: "{query}"\n')
    if not results:
        print("  No results.")
        return
    for r in results:
        bar = _bar(r["score"])
        kws = ", ".join(r["matched_keywords"][:8])
        print(f"  {r['score']:.3f}  {bar}  {r['name']}")
        print(f"         Matched: {kws or '(none)'}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic search across CV bullets and past applications")
    parser.add_argument("mode", choices=["bullets", "jobs", "keywords"], help="Search mode: bullets | jobs | keywords")
    parser.add_argument("query", help="Query string or path to job.txt file")
    parser.add_argument("--top", type=int, default=10, help="Number of results (default: 10)")
    parser.add_argument("--json", action="store_true", dest="json_mode", help="Output JSON")
    args = parser.parse_args()

    cv_path = REPO_ROOT / "data" / "cv.yml"
    apps_dir = REPO_ROOT / "applications"

    query = args.query

    # If query is a file path, read it
    query_path = Path(query)
    if query_path.exists() and query_path.is_file():
        query_text = query_path.read_text(encoding="utf-8")
        query_label = str(query_path)
    else:
        query_text = query
        query_label = query

    if args.mode == "bullets":
        if not cv_path.exists():
            print(f"❌ {cv_path} not found")
            return 1
        results = search_bullets(query_text, cv_path, args.top)
        if args.json_mode:
            print(json.dumps([{k: v for k, v in r.items() if k != "text"} for r in results], indent=2))
        else:
            print_bullets(results, query_label[:60])

    elif args.mode == "jobs":
        if not apps_dir.is_dir():
            print("❌ applications/ directory not found")
            return 1
        results = search_jobs(query_text, apps_dir, args.top)
        if args.json_mode:
            print(json.dumps([{k: v for k, v in r.items() if k != "text"} for r in results], indent=2))
        else:
            print_jobs(results, query_label[:60])

    elif args.mode == "keywords":
        if not apps_dir.is_dir():
            print("❌ applications/ directory not found")
            return 1
        results = search_keywords(query_text, apps_dir, args.top)
        if args.json_mode:
            print(json.dumps([{k: v for k, v in r.items() if k != "text"} for r in results], indent=2))
        else:
            print_keywords(results, query_label[:60])

    return 0


if __name__ == "__main__":
    sys.exit(main())
