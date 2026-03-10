#!/usr/bin/env python3
"""
Quick application status overview.

Reads all applications/*/meta.yml files and prints a compact table showing
stage, days since creation, latest ATS score, and AI provider used.

Usage:
    scripts/status.py [--json] [--active]
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pyyaml required: pip install pyyaml")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = REPO_ROOT / "applications"

# Outcomes that count as "active"
ACTIVE_OUTCOMES = {"applied", "interview", "offer"}

# ANSI colour codes (only used when stdout is a tty)
COLOURS = {
    "applied": "\033[33m",  # yellow
    "interview": "\033[36m",  # cyan
    "offer": "\033[32m",  # green
    "rejected": "\033[90m",  # grey
    "ghosted": "\033[90m",  # grey
    "reset": "\033[0m",
}


def _use_colour() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _colour(text: str, outcome: str) -> str:
    if not _use_colour():
        return text
    code = COLOURS.get(outcome.lower(), "")
    reset = COLOURS["reset"]
    return f"{code}{text}{reset}"


def _days_since(created: object) -> int:
    """Return days between created date and today. Accepts date, str, or int."""
    today = date.today()
    if isinstance(created, date):
        return (today - created).days
    if isinstance(created, str):
        # Handle YYYY-MM-DD or YYYY-MM
        for fmt in ("%Y-%m-%d", "%Y-%m"):
            try:
                d = datetime.strptime(created, fmt).date()
                return (today - d).days
            except ValueError:
                continue
    return -1


def _latest_ats(meta: dict) -> str:
    """Extract the most recent ATS score from ats_history or ats_score."""
    history = meta.get("ats_history")
    if isinstance(history, list) and history:
        last = history[-1]
        if isinstance(last, dict):
            score = last.get("score")
            if score is not None:
                return f"{float(score):.0f}%"
    score = meta.get("ats_score")
    if score is not None:
        return f"{float(score):.0f}%"
    return "--"


def load_applications(active_only: bool = False) -> list[dict]:
    """Load all applications from applications/*/meta.yml."""
    if not APPS_DIR.exists():
        return []

    apps = []
    for app_dir in sorted(APPS_DIR.iterdir()):
        if not app_dir.is_dir():
            continue
        meta_path = app_dir / "meta.yml"
        if not meta_path.exists():
            continue
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception:
            continue

        outcome = str(meta.get("outcome", "")).strip().lower() or "applied"
        if active_only and outcome not in ACTIVE_OUTCOMES:
            continue

        created = meta.get("created") or meta.get("applied", "")
        apps.append(
            {
                "name": app_dir.name,
                "outcome": outcome,
                "days": _days_since(created),
                "ats": _latest_ats(meta),
                "provider": str(meta.get("tailor_provider", "--")).strip() or "--",
            }
        )

    return apps


def print_table(apps: list[dict]) -> None:
    if not apps:
        print("No applications found.")
        return

    col_name = 35
    col_stage = 12
    col_days = 6
    col_ats = 7
    col_provider = 10

    header = (
        f"{'Application':<{col_name}}  "
        f"{'Stage':<{col_stage}}  "
        f"{'Days':>{col_days}}  "
        f"{'ATS':>{col_ats}}  "
        f"{'Provider':<{col_provider}}"
    )
    separator = "-" * len(header)

    print(header)
    print(separator)

    for app in apps:
        name = app["name"]
        if len(name) > col_name:
            name = name[: col_name - 1] + "…"

        outcome = app["outcome"]
        days = str(app["days"]) if app["days"] >= 0 else "--"
        ats = app["ats"]
        provider = app["provider"]
        if len(provider) > col_provider:
            provider = provider[:col_provider]

        stage_display = _colour(f"{outcome:<{col_stage}}", outcome)

        print(f"{name:<{col_name}}  {stage_display}  {days:>{col_days}}  {ats:>{col_ats}}  {provider:<{col_provider}}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick overview of all applications from meta.yml files")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output JSON array instead of table",
    )
    parser.add_argument(
        "--active",
        action="store_true",
        help="Only show applied/interview/offer (skip rejected/ghosted)",
    )
    args = parser.parse_args()

    # Run from repo root so relative paths resolve correctly
    os.chdir(REPO_ROOT)

    apps = load_applications(active_only=args.active)

    if args.as_json:
        print(json.dumps(apps, indent=2))
        return

    print_table(apps)


if __name__ == "__main__":
    main()
