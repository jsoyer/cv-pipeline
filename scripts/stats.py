#!/usr/bin/env python3
"""
Application Statistics & Metrics Dashboard.

Tracks conversion rates, ATS scores, timelines, and trends.

Usage:
    scripts/stats.py           # terminal output
    scripts/stats.py --json    # JSON output
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, date
from pathlib import Path


FUNNEL_STAGES = ["Draft", "Applied", "Interview", "Offer", "Rejected"]


def get_pr_info(name):
    """Get PR info including state, labels, dates."""
    branch = f"apply/{name}"
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "all",
             "--json", "state,labels,createdAt,mergedAt,closedAt",
             "--jq", 'if length > 0 then .[0] | tojson else "" end'],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def get_stage(pr):
    """Determine funnel stage from PR info."""
    if not pr:
        return "Draft"
    label_names = [l["name"] for l in pr.get("labels", [])]
    for s in ["offer", "interview", "rejected"]:
        if f"status:{s}" in label_names:
            return s.capitalize()
    if pr["state"] == "MERGED":
        return "Applied"
    return "Draft"


def get_ats_score(app_dir):
    """Run ATS score and get result."""
    job_txt = app_dir / "job.txt"
    if not job_txt.exists():
        return None
    try:
        result = subprocess.run(
            ["python3", "scripts/ats-score.py", str(app_dir), "--json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode in (0, 1) and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            return data.get("score")
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def get_deadline(app_dir):
    """Read deadline from meta.yml if present."""
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return None
    try:
        import yaml
        with open(meta_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        dl = data.get("deadline")
        if isinstance(dl, date):
            return dl
        if isinstance(dl, str):
            return datetime.strptime(dl, "%Y-%m-%d").date()
    except Exception:
        pass
    return None


def parse_date(date_str):
    """Parse ISO date string."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Application Statistics & Metrics Dashboard. "
                    "Tracks conversion rates, ATS scores, timelines, and trends."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Output results as JSON",
    )
    args = parser.parse_args()
    json_mode = args.json_mode

    apps_dir = Path("applications")
    if not apps_dir.exists():
        print("No applications/ directory found.")
        return 0

    app_dirs = sorted([d for d in apps_dir.iterdir() if d.is_dir()], reverse=True)
    if not app_dirs:
        print("No applications found.")
        return 0

    # Collect data
    funnel = Counter()
    ats_scores = []
    timelines = []
    deadlines_upcoming = []
    total = len(app_dirs)

    for app_dir in app_dirs:
        name = app_dir.name
        pr = get_pr_info(name)
        stage = get_stage(pr)
        funnel[stage] += 1

        # ATS score
        score = get_ats_score(app_dir)
        if score is not None:
            ats_scores.append(score)

        # Timeline: created → merged (days to apply)
        if pr:
            created = parse_date(pr.get("createdAt"))
            merged = parse_date(pr.get("mergedAt"))
            if created and merged:
                days = (merged - created).days
                timelines.append(days)

        # Deadlines
        deadline = get_deadline(app_dir)
        if deadline:
            days_left = (deadline - date.today()).days
            if days_left >= 0:
                deadlines_upcoming.append((name, deadline, days_left))

    deadlines_upcoming.sort(key=lambda x: x[2])

    # Compute metrics
    avg_ats = sum(ats_scores) / len(ats_scores) if ats_scores else 0
    avg_timeline = sum(timelines) / len(timelines) if timelines else 0
    applied = funnel.get("Applied", 0) + funnel.get("Interview", 0) + funnel.get("Offer", 0)
    interview_rate = (funnel.get("Interview", 0) + funnel.get("Offer", 0)) / applied * 100 if applied else 0
    offer_rate = funnel.get("Offer", 0) / applied * 100 if applied else 0

    if json_mode:
        result = {
            "total": total,
            "funnel": {s: funnel.get(s, 0) for s in FUNNEL_STAGES},
            "avg_ats_score": round(avg_ats, 1),
            "avg_days_to_apply": round(avg_timeline, 1),
            "interview_rate_pct": round(interview_rate, 1),
            "offer_rate_pct": round(offer_rate, 1),
            "upcoming_deadlines": [
                {"name": n, "deadline": str(d), "days_left": dl}
                for n, d, dl in deadlines_upcoming
            ],
        }
        print(json.dumps(result, indent=2))
        return 0

    # Terminal output
    print("📊 Application Statistics")
    print(f"   Generated: {date.today()}")
    print()

    # Funnel
    print("📈 Pipeline")
    for stage in FUNNEL_STAGES:
        count = funnel.get(stage, 0)
        pct = count / total * 100 if total else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"   {stage:<12} {bar} {count:>3} ({pct:.0f}%)")
    print()

    # Metrics
    print("📉 Metrics")
    print(f"   Total applications:     {total}")
    if ats_scores:
        print(f"   Average ATS score:      {avg_ats:.0f}%")
        print(f"   Best ATS score:         {max(ats_scores):.0f}%")
        print(f"   Worst ATS score:        {min(ats_scores):.0f}%")
    if timelines:
        print(f"   Avg days to finalize:   {avg_timeline:.1f} days")
    if applied:
        print(f"   Interview rate:         {interview_rate:.0f}% ({funnel.get('Interview', 0) + funnel.get('Offer', 0)}/{applied})")
        print(f"   Offer rate:             {offer_rate:.0f}% ({funnel.get('Offer', 0)}/{applied})")
    print()

    # Deadlines
    if deadlines_upcoming:
        print("⏰ Upcoming Deadlines")
        for name, dl, days_left in deadlines_upcoming[:5]:
            if days_left <= 3:
                icon = "🔴"
            elif days_left <= 7:
                icon = "🟡"
            else:
                icon = "🟢"
            print(f"   {icon} {name:<30} {dl} ({days_left} days)")
        print()

    # Recommendations
    print("💡 Insights")
    if ats_scores and avg_ats < 60:
        print("   - Your average ATS score is below 60% — focus on keyword optimization")
    if funnel.get("Draft", 0) > applied and funnel.get("Draft", 0) > 2:
        print(f"   - {funnel['Draft']} drafts pending — consider finalizing or archiving")
    if applied and interview_rate == 0:
        print("   - No interviews yet — review your tailoring strategy")
    if not ats_scores:
        print("   - No ATS scores yet — add job.txt files and run: make score NAME=...")
    if total <= 1:
        print("   - Too few applications for meaningful statistics")
    elif applied and interview_rate >= 20:
        print(f"   - {interview_rate:.0f}% interview rate — keep up the good work!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
