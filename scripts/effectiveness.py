#!/usr/bin/env python3
"""Analyze application effectiveness based on outcomes and ATS scores."""

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)

WORKDIR = Path(os.environ.get("WORKDIR", Path(__file__).resolve().parent.parent))


def load_applications():
    """Load all applications with their metadata and ATS scores."""
    apps_dir = WORKDIR / "applications"
    if not apps_dir.exists():
        return []

    apps = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue

        app = {"name": d.name, "dir": d}

        # Load meta.yml
        meta_path = d / "meta.yml"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
            app.update(meta)
        else:
            continue

        # Try to get ATS score
        job_txt = d / "job.txt"
        if job_txt.exists():
            try:
                result = subprocess.run(
                    ["python3", str(WORKDIR / "scripts" / "ats-score.py"), str(d), "--json"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode in (0, 1):
                    score_data = json.loads(result.stdout)
                    app["ats_score"] = score_data.get("score", 0)
                    app["found_count"] = score_data.get("found_count", 0)
                    app["total_keywords"] = score_data.get("total_keywords", 0)
            except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
                pass

        apps.append(app)

    return apps


def main():
    apps = load_applications()

    if not apps:
        print("📊 No applications found with meta.yml")
        return 0

    print("📊 Application Effectiveness Report")
    print("=" * 55)
    print()

    # Overall stats
    outcomes = Counter(a.get("outcome", "unknown") for a in apps)
    total = len(apps)
    with_outcome = sum(1 for a in apps if a.get("outcome") and a["outcome"] != "unknown")

    print(f"📈 Total applications: {total}")
    print(f"   Tracked outcomes: {with_outcome}/{total}")
    print()

    if with_outcome > 0:
        print("📋 Outcome Breakdown:")
        order = ["interview", "offer", "applied", "rejected", "ghosted", "unknown"]
        emojis = {"interview": "🎯", "offer": "🏆", "applied": "📬",
                  "rejected": "❌", "ghosted": "👻", "unknown": "❓"}
        for outcome in order:
            count = outcomes.get(outcome, 0)
            if count > 0:
                pct = count / total * 100
                emoji = emojis.get(outcome, "•")
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                print(f"   {emoji} {outcome:12s} {count:3d} ({pct:5.1f}%) {bar}")
        print()

        # Response rate
        interviews = outcomes.get("interview", 0) + outcomes.get("offer", 0)
        response_rate = interviews / with_outcome * 100 if with_outcome > 0 else 0
        print(f"🎯 Interview rate: {response_rate:.0f}% ({interviews}/{with_outcome})")
        print()

    # ATS score analysis
    scored = [a for a in apps if "ats_score" in a]
    if scored:
        print("📊 ATS Score vs Outcome:")
        print(f"   {'Application':30s} {'Score':>6s}  {'Outcome':>10s}")
        print(f"   {'─' * 50}")
        for a in sorted(scored, key=lambda x: x.get("ats_score", 0), reverse=True):
            score = a.get("ats_score", 0)
            outcome = a.get("outcome", "—")
            emoji = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")
            print(f"   {a['name']:30s} {emoji} {score:4.0f}%  {outcome:>10s}")
        print()

        # Correlation
        interviewed = [a["ats_score"] for a in scored
                       if a.get("outcome") in ("interview", "offer")]
        not_interviewed = [a["ats_score"] for a in scored
                           if a.get("outcome") in ("rejected", "ghosted")]

        if interviewed and not_interviewed:
            avg_good = sum(interviewed) / len(interviewed)
            avg_bad = sum(not_interviewed) / len(not_interviewed)
            print(f"💡 Insight:")
            print(f"   Avg ATS score (got interview): {avg_good:.0f}%")
            print(f"   Avg ATS score (no interview):  {avg_bad:.0f}%")
            diff = avg_good - avg_bad
            if diff > 5:
                print(f"   → Higher ATS scores correlate with +{diff:.0f}% more interviews")
            print()

    # Response time
    with_response = [a for a in apps if a.get("response_days")]
    if with_response:
        avg_days = sum(a["response_days"] for a in with_response) / len(with_response)
        print(f"⏱️  Average response time: {avg_days:.0f} days")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
