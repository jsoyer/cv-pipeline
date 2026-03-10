#!/usr/bin/env python3
"""
ATS score trend tracking — show per-application score history and monthly overview.

Reads ats_history[] from each application's meta.yml (written by ats-score.py).

Usage:
    scripts/ats-history.py [--app NAME] [--json]
    make ats-history [NAME=...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT


def load_history(apps_dir: Path) -> list[dict]:
    """Load all applications with their ATS history."""
    records = []
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        meta_path = app_dir / "meta.yml"
        if not meta_path.exists():
            continue
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        history = meta.get("ats_history", [])
        if not history:
            continue
        records.append(
            {
                "name": app_dir.name,
                "company": meta.get("company", app_dir.name),
                "position": meta.get("position", ""),
                "outcome": meta.get("outcome", "applied"),
                "provider": meta.get("tailor_provider", ""),
                "history": history,
            }
        )
    return records


def _trend_arrow(scores: list[float]) -> str:
    if len(scores) < 2:
        return "  "
    delta = scores[-1] - scores[-2]
    if delta > 2:
        return "↑ "
    if delta < -2:
        return "↓ "
    return "→ "


def _bar(score: float, width: int = 20) -> str:
    filled = int(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def print_history(records: list[dict], app_filter: str | None = None) -> None:
    if app_filter:
        records = [
            r for r in records if app_filter.lower() in r["name"].lower() or app_filter.lower() in r["company"].lower()
        ]

    if not records:
        print("No ATS history found. Run 'make score NAME=...' to record scores.")
        return

    print(f"\n{'ATS SCORE HISTORY':=^72}")

    for rec in records:
        history = rec["history"]
        scores = [h["score"] for h in history]
        latest = scores[-1]
        arrow = _trend_arrow(scores)
        bar = _bar(latest)

        print(f"\n  {rec['name']}")
        print(f"  {rec['company']} — {rec['position'][:45]}")
        print(f"  Provider: {rec['provider'] or 'unknown':10s}  Outcome: {rec['outcome']}")

        if len(scores) == 1:
            print(f"  Score: {latest:.0f}%  {bar}")
        else:
            # Show trend table
            print(f"  {'Date':<22}{'Score':>7}  {'Bar'}")
            for entry in history:
                d = entry.get("date", "")[:10]
                s = entry["score"]
                b = _bar(s, 15)
                print(f"  {d:<22}{s:>6.0f}%  {b}")
            delta = scores[-1] - scores[0]
            sign = "+" if delta >= 0 else ""
            print(f"  Trend: {arrow}{sign}{delta:.1f}% over {len(scores)} runs")

    # Monthly overview (latest score per app per month)
    monthly: dict[str, list[float]] = {}
    for rec in records:
        for entry in rec["history"]:
            month = entry.get("date", "")[:7]
            monthly.setdefault(month, []).append(entry["score"])

    if len(monthly) > 1:
        print(f"\n{'MONTHLY AVERAGES':=^72}")
        for month in sorted(monthly):
            scores = monthly[month]
            avg = sum(scores) / len(scores)
            bar = _bar(avg, 15)
            print(f"  {month}  avg {avg:5.1f}%  {bar}  ({len(scores)} apps)")

    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="ATS score trend tracking")
    parser.add_argument("--app", metavar="NAME", help="Filter by application name or company")
    parser.add_argument("--json", action="store_true", dest="json_mode", help="Output JSON")
    args = parser.parse_args()

    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.is_dir():
        print("❌ applications/ directory not found")
        return 1

    records = load_history(apps_dir)

    if args.app:
        records = [
            r for r in records if args.app.lower() in r["name"].lower() or args.app.lower() in r["company"].lower()
        ]

    if args.json_mode:
        print(json.dumps(records, indent=2))
        return 0

    print_history(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
