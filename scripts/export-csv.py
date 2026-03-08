#!/usr/bin/env python3
"""
Export all application data to CSV.

Reads meta.yml + milestones.yml from applications/*/
Optionally runs ats-score.py --json for each app with job.txt.

Output: applications-export.csv (repo root) or --output PATH

Columns:
  app_dir, company, position, created, deadline, outcome, response_days,
  ats_score, ats_found, ats_total, milestone_count, last_stage,
  days_in_pipeline, has_job_txt, has_cv_tailored, has_coverletter,
  has_research, has_contacts, has_prep

Usage:
    scripts/export-csv.py [--output PATH] [--no-ats] [--json]
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent

from lib.common import REPO_ROOT

FIELDNAMES = [
    "app_dir", "company", "position", "created", "deadline",
    "outcome", "response_days",
    "ats_score", "ats_found", "ats_total",
    "milestone_count", "last_stage", "days_in_pipeline",
    "has_job_txt", "has_cv_tailored", "has_coverletter",
    "has_research", "has_contacts", "has_prep",
]


def _parse_date(val) -> datetime | None:
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _ats_score(app_dir: Path) -> tuple[float, int, int]:
    """Return (score, found_count, total_keywords) or (0,0,0) on failure."""
    if not (app_dir / "job.txt").exists():
        return 0.0, 0, 0
    try:
        r = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "ats-score.py"), str(app_dir), "--json"],
            capture_output=True, text=True, timeout=30, cwd=REPO_ROOT,
        )
        if r.stdout.strip():
            data = json.loads(r.stdout)
            return (
                round(float(data.get("score", 0)), 1),
                int(data.get("found_count", 0)),
                int(data.get("total_keywords", 0)),
            )
    except Exception:
        pass
    return 0.0, 0, 0


def collect(apps_dir: Path, run_ats: bool = True) -> list[dict]:
    rows = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue

        # meta.yml
        meta = {}
        if (d / "meta.yml").exists():
            with open(d / "meta.yml", encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}

        # milestones
        milestones = []
        if (d / "milestones.yml").exists():
            with open(d / "milestones.yml", encoding="utf-8") as f:
                ms = yaml.safe_load(f) or {}
            milestones = ms.get("milestones", [])

        created  = _parse_date(meta.get("created", ""))
        deadline = _parse_date(meta.get("deadline", ""))
        days     = (datetime.now() - created).days if created else ""
        last_stage = milestones[-1].get("stage", "") if milestones else ""

        ats_score, ats_found, ats_total = (0.0, 0, 0)
        if run_ats:
            ats_score, ats_found, ats_total = _ats_score(d)

        rows.append({
            "app_dir":        d.name,
            "company":        meta.get("company", ""),
            "position":       meta.get("position", ""),
            "created":        created.strftime("%Y-%m-%d") if created else "",
            "deadline":       deadline.strftime("%Y-%m-%d") if deadline else "",
            "outcome":        meta.get("outcome", ""),
            "response_days":  meta.get("response_days", ""),
            "ats_score":      ats_score if ats_score else "",
            "ats_found":      ats_found if ats_found else "",
            "ats_total":      ats_total if ats_total else "",
            "milestone_count":len(milestones),
            "last_stage":     last_stage,
            "days_in_pipeline": days,
            "has_job_txt":    "yes" if (d / "job.txt").exists() else "",
            "has_cv_tailored":"yes" if (d / "cv-tailored.yml").exists() else "",
            "has_coverletter":"yes" if (d / "coverletter.yml").exists() else "",
            "has_research":   "yes" if (d / "company-research.md").exists() else "",
            "has_contacts":   "yes" if (d / "contacts.md").exists() else "",
            "has_prep":       "yes" if (d / "prep.md").exists() else "",
        })

    return rows


def main():
    parser = argparse.ArgumentParser(description="Export all application data to CSV")
    parser.add_argument("--output", "-o", default="",
                        help="Output file path (default: applications-export.csv)")
    parser.add_argument("--no-ats", action="store_true",
                        help="Skip ATS scoring (faster)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of CSV")
    args = parser.parse_args()

    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ applications/ directory not found")
        return 1

    if not args.no_ats:
        print("   Scoring ATS for apps with job.txt (use --no-ats to skip)...")

    rows = collect(apps_dir, run_ats=not args.no_ats)

    if not rows:
        print("📋 No applications found.")
        return 0

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    out_path = Path(args.output) if args.output else REPO_ROOT / "applications-export.csv"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    # Terminal summary
    total    = len(rows)
    outcomes = {}
    for r in rows:
        o = r["outcome"] or "pending"
        outcomes[o] = outcomes.get(o, 0) + 1

    print(f"📊 Exported {total} applications → {out_path}")
    print()
    print(f"  {'Outcome':<15} {'Count':>5}")
    print("  " + "─" * 22)
    for outcome, count in sorted(outcomes.items(), key=lambda x: -x[1]):
        print(f"  {outcome:<15} {count:>5}")
    print()
    print(f"  Columns: {', '.join(FIELDNAMES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
