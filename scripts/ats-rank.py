#!/usr/bin/env python3
"""
Rank all applications by ATS score.

Runs ats-score.py --json for each application that has a job.txt and
displays results sorted by score (highest to lowest).

Usage:
    scripts/ats-rank.py [--min-score N] [--json]

Options:
    --min-score N   Only show applications with score >= N (default: 0)
    --json          Output JSON
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from lib.common import load_meta as _lib_load_meta, REPO_ROOT

_SCRIPT_DIR = Path(__file__).parent

OUTCOME_EMOJI = {
    "applied":   "📤",
    "interview": "🗣️",
    "offer":     "🎉",
    "rejected":  "❌",
    "ghosted":   "👻",
    "":          "📝",
}


def load_meta(app_dir: Path) -> dict:
    # Soft fallback: lib.common.load_meta calls require_yaml() which hard-exits
    # when PyYAML is missing. Guard here so ATS ranking still works without it.
    if not HAS_YAML:
        return {}
    return _lib_load_meta(app_dir)


def score_app(app_dir: Path) -> dict | None:
    """Run ats-score.py --json for one app. Returns parsed JSON or None."""
    try:
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "ats-score.py"), str(app_dir), "--json"],
            capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
        )
        # returncode 0 = score>=60%, 1 = score<60% — both are valid results
        if result.stdout.strip():
            return json.loads(result.stdout)
        return None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Rank applications by ATS score")
    parser.add_argument(
        "--min-score", type=float, default=0, metavar="N",
        help="Minimum score to display (default: 0)"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ No applications/ directory found")
        sys.exit(1)

    targets = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "job.txt").exists():
            continue
        targets.append(d)

    if not targets:
        print("⚠️  No applications with job.txt found")
        return 0

    print(
        f"📊 ATS Score Ranking — "
        f"{len(targets)} application{'s' if len(targets) != 1 else ''}"
    )
    print("   Scoring", end="", flush=True)

    results = []
    for app_dir in targets:
        print(".", end="", flush=True)
        meta = load_meta(app_dir)
        score_data = score_app(app_dir)
        if score_data is None:
            continue
        results.append({
            "name":           app_dir.name,
            "company":        meta.get("company", app_dir.name),
            "position":       meta.get("position", ""),
            "outcome":        meta.get("outcome", ""),
            "score":          score_data.get("score", 0),
            "found_count":    score_data.get("found_count", 0),
            "total_keywords": score_data.get("total_keywords", 0),
            "missing_count":  score_data.get("missing_count", 0),
            "missing":        [m["keyword"] for m in score_data.get("missing", [])[:5]],
        })

    print(" done\n")

    if args.min_score > 0:
        results = [r for r in results if r["score"] >= args.min_score]

    results.sort(key=lambda x: -x["score"])

    if not results:
        print(f"⚠️  No applications with score >= {args.min_score:.0f}%")
        return 0

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    # Terminal table
    col_name = 35
    header = f"{'Rank':<5}  {'Application':<{col_name}}  {'Score':>7}  {'Keywords':>12}  Outcome"
    print(header)
    print("─" * len(header))

    for i, r in enumerate(results, 1):
        grade = (
            "🟢" if r["score"] >= 80 else
            "🟡" if r["score"] >= 60 else
            "🟠" if r["score"] >= 40 else
            "🔴"
        )
        outcome = r["outcome"] or ""
        emoji = OUTCOME_EMOJI.get(outcome, "📝")
        outcome_str = f"{emoji} {outcome.title()}" if outcome else "📝 Pending"
        kw_str = f"{r['found_count']}/{r['total_keywords']}"
        print(
            f" #{i:<4}  {r['name']:<{col_name}}  "
            f"{grade} {r['score']:>5.1f}%  {kw_str:>12}  {outcome_str}"
        )

    print()

    # Summary statistics
    scores = [r["score"] for r in results]
    avg   = sum(scores) / len(scores)
    best  = max(results, key=lambda x: x["score"])
    worst = min(results, key=lambda x: x["score"])
    print(
        f"Average: {avg:.1f}%   "
        f"Best: {best['score']:.1f}% ({best['name']})   "
        f"Worst: {worst['score']:.1f}% ({worst['name']})"
    )
    print()

    # Tips for low scorers
    low = [r for r in results if r["score"] < 60]
    if low:
        print("💡 Low scores (<60%) — top missing keywords:")
        for r in low[:3]:
            if r["missing"]:
                print(f"   {r['name']}: {', '.join(r['missing'][:5])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
