#!/usr/bin/env python3
"""
Archive a completed application with a full summary report.

Richer alternative to `make archive` — in addition to moving files:
  - Sets final outcome in meta.yml (if not already set)
  - Generates ARCHIVE.md: timeline, ATS score, milestones, days elapsed
  - Creates a git tag: archived/YYYY-MM-company
  - Moves applications/NAME/ → archive/NAME/
  - Commits the move to git
  - Deletes local + remote branch apply/NAME

Usage:
    scripts/archive-app.py <app-dir> [--outcome OUTCOME] [--no-commit] [--no-tag]

Outcomes: applied | interview | offer | rejected | ghosted
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

from lib.common import REPO_ROOT, require_yaml

yaml = require_yaml()

_SCRIPT_DIR = Path(__file__).parent

VALID_OUTCOMES = {"applied", "interview", "offer", "rejected", "ghosted"}

OUTCOME_EMOJI = {
    "offer":    "🎉",
    "rejected": "❌",
    "ghosted":  "👻",
    "interview":"🗣️",
    "applied":  "📤",
    "":         "📝",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _git(args: list[str], cwd: Path = REPO_ROOT, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, check=check
    )


def _run_ats_score(app_dir: Path) -> dict | None:
    """Run ats-score.py --json and return parsed result."""
    job_txt = app_dir / "job.txt"
    if not job_txt.exists():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "ats-score.py"),
             str(app_dir), "--json"],
            capture_output=True, text=True, timeout=30, cwd=REPO_ROOT
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Archive summary
# ---------------------------------------------------------------------------

def build_archive_md(app_dir: Path, meta: dict, ats: dict | None) -> str:
    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    outcome  = meta.get("outcome", "")
    today    = date.today().isoformat()

    created  = _parse_date(meta.get("created", ""))
    deadline = _parse_date(meta.get("deadline", ""))

    days_elapsed = (datetime.now() - created).days if created else None

    emoji = OUTCOME_EMOJI.get(outcome, "📝")

    lines = [
        f"# Archive — {company}",
        f"*{position} · Archived: {today}*",
        "",
        f"## Outcome: {emoji} {outcome.capitalize() if outcome else 'Unknown'}",
        "",
    ]

    # Timeline
    lines += ["## Timeline", ""]
    if created:
        lines.append(f"| Event | Date |")
        lines.append(f"|-------|------|")
        lines.append(f"| Application created | {created.strftime('%Y-%m-%d')} |")
        if deadline:
            lines.append(f"| Deadline | {deadline.strftime('%Y-%m-%d')} |")
        lines.append(f"| Archived | {today} |")
        if days_elapsed is not None:
            lines.append(f"| **Total duration** | **{days_elapsed} days** |")
        lines.append("")

    # Milestones
    ms_path = app_dir / "milestones.yml"
    if ms_path.exists():
        with open(ms_path, encoding="utf-8") as f:
            ms_data = yaml.safe_load(f) or {}
        milestones = ms_data.get("milestones", [])
        if milestones:
            lines += ["## Interview Stages", ""]
            lines.append("| Stage | Date | Interviewer | Outcome |")
            lines.append("|-------|------|-------------|---------|")
            for m in milestones:
                lines.append(
                    f"| {m.get('stage','')} | {m.get('date','')} | "
                    f"{m.get('interviewer','')} | {m.get('outcome','')} |"
                )
            lines.append("")

    # ATS score
    if ats:
        score = ats.get("score", 0)
        found = ats.get("found_count", 0)
        total = ats.get("total_keywords", 0)
        lines += [
            "## ATS Score",
            "",
            f"**{score:.1f}%** — {found}/{total} keywords matched",
            "",
        ]

    # Meta
    response_days = meta.get("response_days", "")
    if response_days:
        lines += [f"*Response time: {response_days} days*", ""]

    # Files present
    files = sorted(f.name for f in app_dir.iterdir() if f.is_file())
    lines += [
        "## Files",
        "",
        "| File | Description |",
        "|------|-------------|",
    ]
    file_desc = {
        "meta.yml":          "Application metadata",
        "job.txt":           "Job description",
        "job.url":           "Job posting URL",
        "cv-tailored.yml":   "AI-tailored CV (YAML)",
        "coverletter.yml":   "AI-generated cover letter (YAML)",
        "company-research.md": "Company research notes",
        "contacts.md":       "Recruiter/HM contacts",
        "prep.md":           "Interview prep notes",
        "competitors.md":    "Competitor landscape",
        "salary-bench.md":   "Salary benchmarking",
        "linkedin-message.md": "LinkedIn outreach",
        "recruiter-email.md": "Recruiter email",
        "reference-request.md": "Reference request emails",
        "milestones.yml":    "Interview stage log",
        "cover-angles.md":   "Cover letter variants",
        "job-fit.md":        "Personal fit analysis",
    }
    for f in files:
        desc = file_desc.get(f, "")
        lines.append(f"| `{f}` | {desc} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Archive a completed application with full summary"
    )
    parser.add_argument("app_dir", help="Application directory (in applications/)")
    parser.add_argument(
        "--outcome",
        choices=list(VALID_OUTCOMES),
        default="",
        help="Final outcome (updates meta.yml if not already set)"
    )
    parser.add_argument(
        "--no-commit", action="store_true",
        help="Skip git commit after archiving"
    )
    parser.add_argument(
        "--no-tag", action="store_true",
        help="Skip git tag creation"
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Print what would be done without moving files or running git commands",
    )
    args = parser.parse_args()

    dry_run = args.dry_run
    if dry_run:
        print("[DRY RUN] No files will be moved and no git commands will run.")

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        # Try resolving from repo root
        app_dir = REPO_ROOT / "applications" / app_dir.name
        if not app_dir.is_dir():
            print(f"❌ Directory not found: {args.app_dir}")
            sys.exit(1)

    app_name = app_dir.name
    archive_root = REPO_ROOT / "archive"
    archive_dest = archive_root / app_name

    if archive_dest.exists():
        print(f"❌ Already archived: {archive_dest}")
        sys.exit(1)

    # Load meta
    meta_path = app_dir / "meta.yml"
    meta = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_name)
    position = meta.get("position", "")
    outcome  = meta.get("outcome", "")

    # Update outcome if provided
    if args.outcome and not outcome:
        meta["outcome"] = args.outcome
        outcome = args.outcome
        if dry_run:
            print(f"[DRY RUN] Would update outcome in {meta_path} → {outcome}")
        else:
            with open(meta_path, "w", encoding="utf-8") as f:
                yaml.dump(meta, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            print(f"   📝 Updated outcome → {outcome}")
    elif args.outcome and outcome and args.outcome != outcome:
        print(f"   ℹ️  outcome already set to '{outcome}' — use meta.yml to override")

    emoji = OUTCOME_EMOJI.get(outcome, "📝")

    print(f"\n📦 Archiving {company} — {position}")
    print(f"   Outcome: {emoji} {outcome or '(not set)'}")
    print()

    # Run ATS score
    print("   Scoring ATS...")
    ats = _run_ats_score(app_dir)
    if ats:
        print(f"   ATS score: {ats.get('score', 0):.1f}%")

    # Build ARCHIVE.md
    archive_md = build_archive_md(app_dir, meta, ats)
    archive_md_path = app_dir / "ARCHIVE.md"
    if dry_run:
        print(f"[DRY RUN] Would write: {archive_md_path}")
    else:
        archive_md_path.write_text(archive_md, encoding="utf-8")
        print(f"   📄 Generated ARCHIVE.md")

    # Create archive directory + move
    if dry_run:
        print(f"[DRY RUN] Would move: {app_dir} -> {archive_dest}")
    else:
        archive_root.mkdir(exist_ok=True)
        shutil.move(str(app_dir), str(archive_dest))
        print(f"   📁 Moved → archive/{app_name}/")

    # Git tag
    tag = f"archived/{app_name}"
    if not args.no_tag:
        tag_msg = f"Archive: {company} — {position} ({outcome or 'unknown'})"
        if dry_run:
            print(f"[DRY RUN] Would run: git tag -a {tag} -m '{tag_msg}'")
        else:
            r = _git(["tag", "-a", tag, "-m", tag_msg])
            if r.returncode == 0:
                print(f"   🏷️  Tagged: {tag}")
            else:
                print(f"   ⚠️  Tag failed: {r.stderr.strip()}")

    # Delete branches
    branch = f"apply/{app_name}"
    if dry_run:
        print(f"[DRY RUN] Would run: git branch -d {branch} (if it exists)")
        print(f"[DRY RUN] Would run: git push origin --delete {branch} (if remote exists)")
    else:
        r = _git(["show-ref", "--quiet", f"refs/heads/{branch}"])
        if r.returncode == 0:
            _git(["branch", "-d", branch])
            print(f"   🔀 Deleted local branch: {branch}")

        r = _git(["ls-remote", "--heads", "origin", branch])
        if r.stdout.strip():
            _git(["push", "origin", "--delete", branch])
            print(f"   🔀 Deleted remote branch: {branch}")

    # Commit
    if not args.no_commit:
        if dry_run:
            print(f"[DRY RUN] Would run: git add + git commit 'archive: {app_name} — {outcome or 'unknown'} {emoji}'")
        else:
            _git(["add", "-A", str(archive_dest), str(archive_root)])
            # Stage the deletion from applications/
            _git(["add", "-u"])
            r = _git([
                "commit", "-m",
                f"archive: {app_name} — {outcome or 'unknown'} {emoji}\n\n"
                f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
            ])
            if r.returncode == 0:
                print(f"   ✅ Committed archive")
            else:
                print(f"   ⚠️  Commit failed: {r.stderr.strip()}")

    # Push tag
    if not args.no_tag:
        if dry_run:
            print(f"[DRY RUN] Would run: git push origin {tag}")
        else:
            r = _git(["push", "origin", tag])
            if r.returncode == 0:
                print(f"   ✅ Pushed tag {tag}")

    created = _parse_date(meta.get("created", ""))
    days = (datetime.now() - created).days if created else "?"

    print(f"\n✅ Archived: {company} | {outcome or 'unknown'} | {days}d in pipeline")
    print(f"   → archive/{app_name}/ARCHIVE.md")

    return 0


if __name__ == "__main__":
    sys.exit(main())
