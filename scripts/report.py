#!/usr/bin/env python3
"""
Application Report Generator.

Usage:
    scripts/report.py                    # terminal output
    scripts/report.py --format markdown  # markdown output
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from lib.common import company_from_dirname, REPO_ROOT

try:
    import yaml
except ImportError:
    yaml = None

# Funnel stages (ordered). PR labels are used to track status.
# Apply label "status:interview", "status:offer", "status:rejected" on PRs.
FUNNEL_STAGES = ["Draft", "Applied", "Interview", "Offer", "Rejected"]


def get_app_info(app_dir):
    """Extract application metadata from directory."""
    name = app_dir.name
    company = company_from_dirname(name)

    # Find position from file names
    position = "Unknown"
    for f in app_dir.glob("CV - *.tex"):
        match = re.search(r"CV - .+? - (.+)\.tex", f.name)
        if match:
            position = match.group(1)
            break

    return {
        "name": name,
        "company": company,
        "position": position,
        "dir": app_dir,
    }


def check_files(app_dir):
    """Check which files exist."""
    checks = [
        ("CV - *.tex", "CV"),
        ("CoverLetter - *.tex", "CL"),
        ("job.txt", "job.txt"),
        ("meta.yml", "meta"),
    ]
    return {label: bool(list(app_dir.glob(pattern))) for pattern, label in checks}


def get_deadline(app_dir):
    """Read deadline from meta.yml if present."""
    if not yaml:
        return None
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        dl = data.get("deadline")
        if isinstance(dl, datetime.date):
            return dl
        if isinstance(dl, str):
            return datetime.datetime.strptime(dl, "%Y-%m-%d").date()
    except Exception:
        pass
    return None


def get_pr_status(name):
    """Get PR status and labels via gh CLI."""
    branch = f"apply/{name}"
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "all",
             "--json", "state,url,labels,createdAt",
             "--jq", 'if length > 0 then .[0] | tojson else "" end'],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            pr = json.loads(result.stdout.strip())
            label_names = [l["name"] for l in pr.get("labels", [])]
            # Determine funnel stage from labels
            stage = None
            for s in ["offer", "interview", "rejected"]:
                if f"status:{s}" in label_names:
                    stage = s.capitalize()
                    break
            if not stage:
                if pr["state"] == "MERGED":
                    stage = "Applied"
                else:
                    stage = "Draft"
            return {
                "state": pr["state"],
                "url": pr.get("url", ""),
                "stage": stage,
                "created": pr.get("createdAt", "")[:10],
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def count_tex_diffs(app_dir):
    """Count lines changed vs master CV."""
    cv_files = list(app_dir.glob("CV - *.tex"))
    if not cv_files:
        return None
    try:
        result = subprocess.run(
            ["diff", "--brief", "CV.tex", str(cv_files[0])],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return "identical"
        result = subprocess.run(
            ["diff", "-u", "CV.tex", str(cv_files[0])],
            capture_output=True, text=True, timeout=5
        )
        added = sum(1 for l in result.stdout.splitlines() if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in result.stdout.splitlines() if l.startswith("-") and not l.startswith("---"))
        return f"+{added}/-{removed}"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def render_funnel(funnel):
    """Render funnel dashboard in terminal."""
    print("📊 Application Funnel")
    print()
    icons = {"Draft": "📝", "Applied": "📤", "Interview": "🎤", "Offer": "🎉", "Rejected": "❌"}
    max_count = max(funnel.values()) if any(funnel.values()) else 1
    bar_width = 30
    for stage in FUNNEL_STAGES:
        count = funnel.get(stage, 0)
        bar_len = int((count / max_count) * bar_width) if max_count > 0 else 0
        bar = "█" * bar_len + "░" * (bar_width - bar_len)
        icon = icons.get(stage, "•")
        print(f"  {icon} {stage:<12} {bar} {count}")
    print()


def render_terminal(apps):
    """Render report in terminal format."""
    print("📋 Application Report")
    print(f"   Generated: {datetime.date.today()}")
    print()

    funnel = {s: 0 for s in FUNNEL_STAGES}

    for app_dir in apps:
        info = get_app_info(app_dir)
        files = check_files(app_dir)
        pr = get_pr_status(info["name"])
        diff = count_tex_diffs(app_dir)

        print("═" * 65)
        print(f"📁 {info['name']}")
        print(f"   Company:    {info['company']}")
        print(f"   Position:   {info['position']}")

        if pr:
            stage_icons = {
                "Draft": "📝 Draft", "Applied": "📤 Applied",
                "Interview": "🎤 Interview", "Offer": "🎉 Offer",
                "Rejected": "❌ Rejected",
            }
            stage = pr["stage"]
            print(f"   Stage:      {stage_icons.get(stage, stage)}")
            print(f"   PR:         {pr['url']}")
            if pr.get("created"):
                print(f"   Created:    {pr['created']}")
            funnel[stage] = funnel.get(stage, 0) + 1
        else:
            print("   Stage:      ⚪ Local only")
            funnel["Draft"] += 1

        file_parts = []
        for label, exists in files.items():
            file_parts.append(f"{'✅' if exists else '❌'}{label}")
        print(f"   Files:      {'  '.join(file_parts)}")

        if diff and diff != "identical":
            print(f"   Tailoring:  📝 {diff} lines vs master")
        elif diff == "identical":
            print("   Tailoring:  ⚠️  Not tailored (identical to master)")

        deadline = get_deadline(app_dir)
        if deadline:
            days_left = (deadline - datetime.date.today()).days
            if days_left < 0:
                print(f"   Deadline:   🔴 {deadline} (expired {-days_left} days ago)")
            elif days_left <= 3:
                print(f"   Deadline:   🔴 {deadline} ({days_left} days left)")
            elif days_left <= 7:
                print(f"   Deadline:   🟡 {deadline} ({days_left} days left)")
            else:
                print(f"   Deadline:   🟢 {deadline} ({days_left} days left)")

        print()

    print("═" * 65)
    render_funnel(funnel)

    total = len(apps)
    active = total - funnel.get("Rejected", 0)
    print(f"📊 Total: {total} application(s), {active} active")


def render_markdown(apps):
    """Render report in markdown format."""
    print("# Application Report")
    print(f"\nGenerated: {datetime.date.today()}\n")

    funnel = {s: 0 for s in FUNNEL_STAGES}

    print("| Application | Company | Position | Stage | CV | CL | job.txt | Tailored |")
    print("|---|---|---|---|---|---|---|---|")

    for app_dir in apps:
        info = get_app_info(app_dir)
        files = check_files(app_dir)
        pr = get_pr_status(info["name"])
        diff = count_tex_diffs(app_dir)

        if pr:
            stage = pr["stage"]
            state = f"[{stage}]({pr['url']})"
            funnel[stage] = funnel.get(stage, 0) + 1
        else:
            state = "Local"
            funnel["Draft"] += 1

        yn = lambda v: "✅" if v else "❌"
        tailored = diff if diff and diff != "identical" else ("❌" if diff == "identical" else "—")

        print(f"| {info['name']} | {info['company']} | {info['position']} | "
              f"{state} | {yn(files['CV'])} | {yn(files['CL'])} | {yn(files['job.txt'])} | {tailored} |")

    # Funnel summary
    print("\n## Funnel\n")
    print("| Stage | Count |")
    print("|---|---|")
    for stage in FUNNEL_STAGES:
        count = funnel.get(stage, 0)
        if count > 0:
            print(f"| {stage} | {count} |")


def main():
    parser = argparse.ArgumentParser(description="Generate application report")
    parser.add_argument("--format", choices=["terminal", "markdown"],
                        default="terminal", help="Output format")
    args = parser.parse_args()

    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("No applications/ directory found.")
        return 0

    apps = sorted([d for d in apps_dir.iterdir() if d.is_dir()], reverse=True)
    if not apps:
        print("No applications found.")
        return 0

    if args.format == "markdown":
        render_markdown(apps)
    else:
        render_terminal(apps)

    return 0


if __name__ == "__main__":
    sys.exit(main())
