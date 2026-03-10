#!/usr/bin/env python3
"""
Application funnel analytics — conversion rates, ATS correlation, provider comparison.

Reads meta.yml from all applications and computes:
  - Funnel stage conversion rates (applied → screen → interview → offer)
  - ATS score vs outcome correlation (Pearson r)
  - Breakdown by AI provider, theme, company size
  - Time-to-response analysis

Usage:
    scripts/funnel-analytics.py [--json] [--provider PROVIDER]
    make funnel
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT

# Funnel stage ordering (positive = progressed beyond applied)
STAGE_ORDER = {
    "applied": 0,
    "rejected": -1,
    "ghosted": -1,
    "withdrawn": -1,
    "phone_screen": 1,
    "screen": 1,
    "technical": 2,
    "interview": 2,
    "final": 3,
    "final_round": 3,
    "offer": 4,
    "accepted": 5,
    "declined": 4,  # got offer, declined
}

POSITIVE_STAGES = {
    "phone_screen",
    "screen",
    "technical",
    "interview",
    "final",
    "final_round",
    "offer",
    "accepted",
    "declined",
}


def _stage_level(outcome: str) -> int:
    outcome = outcome.lower().replace("-", "_").replace(" ", "_")
    for key, level in STAGE_ORDER.items():
        if key in outcome:
            return level
    return 0  # default to 'applied'


def load_applications(apps_dir: Path) -> list[dict]:
    """Load all application meta.yml records."""
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

        # Get latest ATS score from history or legacy field
        history = meta.get("ats_history", [])
        ats_score = None
        if history:
            ats_score = history[-1].get("score")
        elif "ats_score" in meta:
            ats_score = meta["ats_score"]

        outcome = str(meta.get("outcome", "applied")).lower()
        records.append(
            {
                "name": app_dir.name,
                "company": meta.get("company", ""),
                "position": meta.get("position", ""),
                "outcome": outcome,
                "stage_level": _stage_level(outcome),
                "provider": str(meta.get("tailor_provider", "unknown") or "unknown"),
                "theme": str(meta.get("theme", "") or ""),
                "ats_score": ats_score,
                "response_days": meta.get("response_days"),
                "ats_history_count": len(history),
            }
        )
    return records


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return num / (sx * sy)


def _pct(num: int, den: int) -> str:
    if den == 0:
        return "n/a"
    return f"{num / den * 100:.0f}%"


def _bar(pct: float, width: int = 20) -> str:
    filled = max(0, min(width, int(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def print_report(records: list[dict], provider_filter: str | None = None) -> None:
    if provider_filter:
        records = [r for r in records if r["provider"] == provider_filter]

    total = len(records)
    if total == 0:
        print("No applications found.")
        return

    print(f"\n{'FUNNEL ANALYTICS':=^72}")
    print(f"Total applications: {total}\n")

    # ── Funnel stages ──────────────────────────────────────────────────────
    stage_counts: Counter = Counter()
    for r in records:
        stage_counts[r["outcome"]] += 1

    print("FUNNEL STAGES")
    print(f"  {'Stage':<18} {'Count':>6}  {'Rate':>6}  Bar")
    print(f"  {'-' * 18} {'-' * 6}  {'-' * 6}  {'-' * 20}")

    # Positive funnel progression
    progressed = sum(1 for r in records if r["stage_level"] > 0)
    rejected = sum(1 for r in records if r["stage_level"] < 0)
    still_active = total - progressed - rejected

    print(f"  {'Applied (all)':<18} {total:>6}  {'100%':>6}  {_bar(100)}")
    print(
        f"  {'Response (any)':<18} {progressed + rejected:>6}  {_pct(progressed + rejected, total):>6}  {_bar((progressed + rejected) / total * 100)}"
    )
    print(f"  {'Progressed':<18} {progressed:>6}  {_pct(progressed, total):>6}  {_bar(progressed / total * 100)}")
    print(
        f"  {'Still active':<18} {still_active:>6}  {_pct(still_active, total):>6}  {_bar(still_active / total * 100)}"
    )
    print(f"  {'Rejected/Ghosted':<18} {rejected:>6}  {_pct(rejected, total):>6}  {_bar(rejected / total * 100)}")
    print()

    # Detailed stage breakdown
    for stage, count in stage_counts.most_common():
        bar = _bar(count / total * 100, 15)
        print(f"    {stage:<20} {count:>4}  {_pct(count, total):>6}  {bar}")
    print()

    # ── ATS score correlation ──────────────────────────────────────────────
    scored = [r for r in records if r["ats_score"] is not None]
    if scored:
        print("ATS SCORE ANALYSIS")
        avg_all = sum(r["ats_score"] for r in scored) / len(scored)
        avg_prog = sum(r["ats_score"] for r in scored if r["stage_level"] > 0) / max(
            1, sum(1 for r in scored if r["stage_level"] > 0)
        )
        avg_rej = sum(r["ats_score"] for r in scored if r["stage_level"] < 0) / max(
            1, sum(1 for r in scored if r["stage_level"] < 0)
        )

        print(f"  Average ATS score (all):        {avg_all:.1f}%")
        print(f"  Average ATS score (progressed): {avg_prog:.1f}%")
        print(f"  Average ATS score (rejected):   {avg_rej:.1f}%")

        # Pearson correlation: ATS score vs stage_level
        xs = [r["ats_score"] for r in scored]
        ys = [float(r["stage_level"]) for r in scored]
        r_val = _pearson(xs, ys)
        if r_val is not None:
            strength = "strong" if abs(r_val) > 0.6 else ("moderate" if abs(r_val) > 0.3 else "weak")
            direction = "positive" if r_val > 0 else "negative"
            print(f"  Pearson correlation (ATS vs outcome): r={r_val:.3f} ({strength} {direction})")
        print()

    # ── Breakdown by provider ──────────────────────────────────────────────
    by_provider: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_provider[r["provider"]].append(r)

    if len(by_provider) > 1:
        print("BY AI PROVIDER")
        print(f"  {'Provider':<12} {'Apps':>5}  {'Progressed':>11}  {'Avg ATS':>8}")
        print(f"  {'-' * 12} {'-' * 5}  {'-' * 11}  {'-' * 8}")
        for prov, recs in sorted(by_provider.items()):
            prog = sum(1 for r in recs if r["stage_level"] > 0)
            scored_recs = [r for r in recs if r["ats_score"] is not None]
            avg_ats = (sum(r["ats_score"] for r in scored_recs) / len(scored_recs)) if scored_recs else None
            ats_str = f"{avg_ats:.1f}%" if avg_ats is not None else "  n/a"
            print(f"  {prov:<12} {len(recs):>5}  {prog:>5}/{len(recs):<5} {_pct(prog, len(recs)):>5}  {ats_str:>8}")
        print()

    # ── Time to response ───────────────────────────────────────────────────
    ttr = [
        r["response_days"]
        for r in records
        if r["response_days"] is not None and isinstance(r["response_days"], (int, float))
    ]
    if ttr:
        avg_ttr = sum(ttr) / len(ttr)
        min_ttr = min(ttr)
        max_ttr = max(ttr)
        print("TIME TO RESPONSE")
        print(f"  Applications with response data: {len(ttr)}")
        print(f"  Average: {avg_ttr:.0f} days  (min: {min_ttr}, max: {max_ttr})")

        # By outcome
        by_outcome_ttr: dict[str, list] = defaultdict(list)
        for r in records:
            if r["response_days"] is not None and isinstance(r["response_days"], (int, float)):
                by_outcome_ttr[r["outcome"]].append(r["response_days"])
        for outcome, days in sorted(by_outcome_ttr.items()):
            avg = sum(days) / len(days)
            print(f"  {outcome:<20} avg {avg:.0f}d  (n={len(days)})")
        print()

    # ── ATS iteration count ────────────────────────────────────────────────
    iterated = [r for r in records if r["ats_history_count"] > 1]
    if iterated:
        print(f"ATS ITERATIONS: {len(iterated)} apps with multiple score records")
        for r in iterated:
            print(f"  {r['name']:<35} {r['ats_history_count']} iterations")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Application funnel analytics")
    parser.add_argument("--json", action="store_true", dest="json_mode", help="Output JSON")
    parser.add_argument("--provider", metavar="NAME", help="Filter by AI provider")
    args = parser.parse_args()

    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.is_dir():
        print("❌ applications/ directory not found")
        return 1

    records = load_applications(apps_dir)

    if args.json_mode:
        # Compute summary stats for JSON
        total = len(records)
        progressed = sum(1 for r in records if r["stage_level"] > 0)
        scored = [r for r in records if r["ats_score"] is not None]
        xs = [r["ats_score"] for r in scored]
        ys = [float(r["stage_level"]) for r in scored]
        r_val = _pearson(xs, ys)
        output = {
            "total": total,
            "progressed": progressed,
            "conversion_rate": round(progressed / total * 100, 1) if total else 0,
            "ats_outcome_correlation": round(r_val, 3) if r_val is not None else None,
            "records": records,
        }
        print(json.dumps(output, indent=2))
        return 0

    print_report(records, args.provider)
    return 0


if __name__ == "__main__":
    sys.exit(main())
