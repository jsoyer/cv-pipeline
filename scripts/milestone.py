#!/usr/bin/env python3
"""
Log and display interview milestones for job applications.

Each milestone records a stage (phone-screen, technical, panel, final, offer),
date, interviewer, notes, and outcome. Stored in applications/NAME/milestones.yml.

Usage:
    # Add a milestone
    scripts/milestone.py <app-dir> --stage STAGE [--date DATE] [--interviewer TEXT]
                         [--notes TEXT] [--outcome passed|failed|pending]

    # View timeline for one application
    scripts/milestone.py <app-dir>

    # View all applications with milestones
    scripts/milestone.py

Stages: phone-screen | technical | panel | final | reference-check | offer
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT

VALID_STAGES = [
    "phone-screen", "technical", "panel", "final", "reference-check", "offer",
]

STAGE_EMOJI = {
    "phone-screen":    "📞",
    "technical":       "💻",
    "panel":           "👥",
    "final":           "🏁",
    "reference-check": "📋",
    "offer":           "🎉",
}

OUTCOME_EMOJI = {
    "passed":  "✅",
    "failed":  "❌",
    "pending": "⏳",
    "":        "⏳",
}


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def _load_milestones(app_dir: Path) -> list:
    path = app_dir / "milestones.yml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("milestones", [])


def _save_milestones(app_dir: Path, milestones: list) -> None:
    path = app_dir / "milestones.yml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"milestones": milestones},
            f, default_flow_style=False, allow_unicode=True, sort_keys=False,
        )


def _load_meta(app_dir: Path) -> dict:
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return {}
    with open(meta_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _display_timeline(app_dir: Path) -> None:
    milestones = _load_milestones(app_dir)
    meta = _load_meta(app_dir)
    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")

    print(f"\n📅 Interview Timeline — {company}")
    if position:
        print(f"   {position}")
    print("─" * 55)

    if not milestones:
        print("   No milestones recorded yet.")
        print(f"   Add one: make milestone NAME={app_dir.name} STAGE=phone-screen")
    else:
        for m in milestones:
            stage   = m.get("stage", "?")
            dt      = m.get("date", "?")
            outcome = m.get("outcome", "")
            interviewer = m.get("interviewer", "")
            notes   = m.get("notes", "")

            s_emoji = STAGE_EMOJI.get(stage, "📌")
            o_emoji = OUTCOME_EMOJI.get(outcome, "⏳")

            print(f"\n   {s_emoji} {stage.upper()}")
            print(f"      Date:    {dt}")
            if interviewer:
                print(f"      With:    {interviewer}")
            print(f"      Outcome: {o_emoji} {outcome or 'pending'}")
            if notes:
                # Wrap notes
                import textwrap
                wrapped = textwrap.fill(notes, width=55, initial_indent="      Notes:   ",
                                        subsequent_indent="               ")
                print(wrapped)
    print()


def _display_all() -> None:
    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ No applications/ directory found")
        return

    found = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        milestones = _load_milestones(d)
        if milestones:
            meta = _load_meta(d)
            found.append((d, milestones, meta))

    if not found:
        print("⚠️  No applications with milestones found.")
        print("   Add one: make milestone NAME=2026-02-company STAGE=phone-screen")
        return

    print(f"\n📅 Interview Milestones — {len(found)} application{'s' if len(found) != 1 else ''}\n")
    print(f"  {'Application':<35}  {'Stages':<40}  Latest")
    print("─" * 85)

    for app_dir, milestones, meta in found:
        company  = meta.get("company", app_dir.name)
        stages   = [STAGE_EMOJI.get(m.get("stage", ""), "📌") + " " + m.get("stage", "?")
                    for m in milestones]
        latest   = milestones[-1] if milestones else {}
        outcome  = OUTCOME_EMOJI.get(latest.get("outcome", ""), "⏳")
        latest_stage = latest.get("stage", "")
        print(f"  {app_dir.name:<35}  {' → '.join(s.split()[1] for s in stages):<40}  {outcome} {latest_stage}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Log and display interview milestones"
    )
    parser.add_argument(
        "app_dir", nargs="?", default=None,
        help="Application directory (omit to list all)"
    )
    parser.add_argument(
        "--stage", choices=VALID_STAGES,
        help=f"Stage to add: {' | '.join(VALID_STAGES)}"
    )
    parser.add_argument(
        "--date", default=None,
        help="Date (YYYY-MM-DD, default: today)"
    )
    parser.add_argument("--interviewer", default="", help="Interviewer name(s) and title")
    parser.add_argument("--notes", default="",    help="Notes about the interview")
    parser.add_argument(
        "--outcome", choices=["passed", "failed", "pending"], default="pending",
        help="Outcome (default: pending)"
    )
    args = parser.parse_args()

    # No app_dir → show all
    if not args.app_dir:
        _display_all()
        return 0

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    # No stage → show timeline for this app
    if not args.stage:
        _display_timeline(app_dir)
        return 0

    # Add milestone
    milestone_date = args.date or date.today().isoformat()
    entry = {
        "stage":   args.stage,
        "date":    milestone_date,
        "outcome": args.outcome,
    }
    if args.interviewer:
        entry["interviewer"] = args.interviewer
    if args.notes:
        entry["notes"] = args.notes

    milestones = _load_milestones(app_dir)

    # Update existing stage if already present, else append
    existing = next((i for i, m in enumerate(milestones) if m.get("stage") == args.stage), None)
    if existing is not None:
        milestones[existing] = entry
        print(f"✏️  Updated {args.stage} milestone")
    else:
        milestones.append(entry)
        print(f"✅ Added {args.stage} milestone")

    _save_milestones(app_dir, milestones)

    # Show updated timeline
    _display_timeline(app_dir)

    meta     = _load_meta(app_dir)
    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")

    # Suggest next steps
    stage_idx = VALID_STAGES.index(args.stage)
    if args.outcome == "passed" and stage_idx + 1 < len(VALID_STAGES):
        next_stage = VALID_STAGES[stage_idx + 1]
        print(f"💡 Next: make milestone NAME={app_dir.name} STAGE={next_stage}")
    elif args.stage in ("panel", "final") and args.outcome == "passed":
        print(f"💡 Prepare: make thankyou NAME={app_dir.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
