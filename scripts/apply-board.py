#!/usr/bin/env python3
"""
Terminal Kanban board — applications grouped by stage.

Reads meta.yml + milestones.yml from all applications/*/
Displays a colour-coded pipeline board in the terminal.

Usage:
    scripts/apply-board.py [--stage STAGE] [--json]

Options:
    --stage STAGE   Filter to one stage column
    --json          Output raw data as JSON
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, date
from pathlib import Path

from lib.common import REPO_ROOT, require_yaml

yaml = require_yaml()

# ANSI colours
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_BLACK  = "\033[30m"
_RED    = "\033[31m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_WHITE  = "\033[37m"
_BG_BLUE   = "\033[44m"
_BG_CYAN   = "\033[46m"
_BG_GREEN  = "\033[42m"
_BG_RED    = "\033[41m"
_BG_YELLOW = "\033[43m"
_BG_GREY   = "\033[100m"

# Stage definitions: key → (label, emoji, header colour)
STAGES = {
    "applied":       ("Applied",      "📤", _BG_BLUE   + _WHITE),
    "phone-screen":  ("Phone Screen", "📞", _BG_CYAN   + _BLACK),
    "interview":     ("Interview",    "🗣️",  _BG_YELLOW + _BLACK),
    "final":         ("Final Round",  "🎯", _BG_YELLOW + _BLACK),
    "offer":         ("Offer",        "🎉", _BG_GREEN  + _BLACK),
    "rejected":      ("Rejected",     "❌", _BG_RED    + _WHITE),
    "ghosted":       ("Ghosted",      "👻", _BG_GREY   + _WHITE),
}

STAGE_ORDER = ["applied", "phone-screen", "interview", "final", "offer", "rejected", "ghosted"]

# Map meta.yml outcome values → stage keys
OUTCOME_TO_STAGE = {
    "offer":    "offer",
    "rejected": "rejected",
    "ghosted":  "ghosted",
    "interview":"interview",
}

# Map milestones.yml stage values → board stage
MILESTONE_TO_STAGE = {
    "phone-screen":    "phone-screen",
    "technical":       "interview",
    "panel":           "interview",
    "final":           "final",
    "reference-check": "final",
    "offer":           "offer",
}


# ---------------------------------------------------------------------------
# Data collection
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


def _days_ago(dt: datetime | None) -> int:
    if not dt:
        return 0
    return (datetime.now() - dt).days


def _app_stage(meta: dict, milestones: list) -> str:
    """Determine current board stage from meta + milestones."""
    outcome = meta.get("outcome", "").lower().strip()

    # Terminal outcomes take priority
    if outcome in OUTCOME_TO_STAGE:
        return OUTCOME_TO_STAGE[outcome]

    # Latest milestone stage
    if milestones:
        last = milestones[-1]
        ms_stage = last.get("stage", "")
        if ms_stage in MILESTONE_TO_STAGE:
            return MILESTONE_TO_STAGE[ms_stage]

    return "applied"


def collect_apps(apps_dir: Path) -> list[dict]:
    apps = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue

        # Load meta
        meta_path = d / "meta.yml"
        meta = {}
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}

        # Load milestones
        milestones = []
        ms_path = d / "milestones.yml"
        if ms_path.exists():
            with open(ms_path, encoding="utf-8") as f:
                ms_data = yaml.safe_load(f) or {}
            milestones = ms_data.get("milestones", [])

        company  = meta.get("company", d.name)
        position = meta.get("position", "")
        created  = _parse_date(meta.get("created", ""))
        deadline = _parse_date(meta.get("deadline", ""))
        stage    = _app_stage(meta, milestones)
        days     = _days_ago(created)

        apps.append({
            "dir":       d.name,
            "company":   company,
            "position":  position,
            "stage":     stage,
            "days":      days,
            "created":   created.isoformat()[:10] if created else "",
            "deadline":  deadline.isoformat()[:10] if deadline else "",
            "outcome":   meta.get("outcome", ""),
            "milestones": len(milestones),
        })

    return apps


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

CARD_WIDTH = 26  # chars per card (+ 2 padding)


def _truncate(s: str, n: int) -> str:
    return s[:n - 1] + "…" if len(s) > n else s


def _days_badge(days: int) -> str:
    if days <= 7:
        return f"{_GREEN}{days}d{_RESET}"
    if days <= 21:
        return f"{_YELLOW}{days}d{_RESET}"
    return f"{_RED}{days}d{_RESET}"


def render_board(apps: list[dict], stage_filter: str = "") -> None:
    today = date.today().isoformat()
    total = len(apps)

    # Group by stage
    by_stage: dict[str, list] = {s: [] for s in STAGE_ORDER}
    for app in apps:
        s = app["stage"]
        if s in by_stage:
            by_stage[s].append(app)
        else:
            by_stage["applied"].append(app)

    # Filter
    active_stages = (
        [stage_filter] if stage_filter in STAGES
        else STAGE_ORDER
    )

    # Remove empty terminal stages when showing all
    if not stage_filter:
        active_stages = [
            s for s in STAGE_ORDER
            if by_stage[s] or s in ("applied", "phone-screen", "interview")
        ]

    term_width = shutil.get_terminal_size((120, 40)).columns

    # Header
    print()
    print(f"{_BOLD}📋 Application Board{_RESET}  "
          f"{_DIM}{today} · {total} applications{_RESET}")
    print()

    # Stage summary bar
    parts = []
    for s in STAGE_ORDER:
        count = len(by_stage[s])
        if count:
            label, emoji, colour = STAGES[s]
            parts.append(f"{colour} {emoji} {label}: {count} {_RESET}")
    print("  " + "  ".join(parts))
    print()

    # Columnar board
    cols = len(active_stages)
    col_w = max(CARD_WIDTH + 4, (term_width - 2) // max(cols, 1))
    col_w = min(col_w, 40)

    # Stage headers
    header_row = ""
    for s in active_stages:
        label, emoji, colour = STAGES[s]
        count = len(by_stage[s])
        h = f"{emoji} {label} ({count})"
        h = _truncate(h, col_w - 2)
        header_row += f"{colour}{_BOLD} {h:<{col_w - 2}} {_RESET} "
    print(header_row)
    print("─" * min(cols * (col_w + 1), term_width))

    # Cards — interleave rows
    max_cards = max((len(by_stage[s]) for s in active_stages), default=0)

    for row in range(max_cards):
        line = ""
        for s in active_stages:
            cards = by_stage[s]
            if row < len(cards):
                app = cards[row]
                company  = _truncate(app["company"], col_w - 8)
                days_b   = _days_badge(app["days"])
                dl       = f" ⏰" if app["deadline"] else ""
                ms       = f" 📍{app['milestones']}" if app["milestones"] else ""
                # line 1: company
                line += f" {_BOLD}{company:<{col_w - 8}}{_RESET}{days_b}{dl}{ms}"
                # pad to col_w
                raw_len = 1 + len(company) + len(str(app["days"])) + 1 + (2 if app["deadline"] else 0) + (3 if app["milestones"] else 0)
                pad = max(0, col_w - raw_len)
                line += " " * pad + " "
            else:
                line += " " * (col_w + 1)
        print(line)

        # Position line
        line2 = ""
        for s in active_stages:
            cards = by_stage[s]
            if row < len(cards):
                app = cards[row]
                pos = _truncate(app["position"], col_w - 2)
                line2 += f"  {_DIM}{pos:<{col_w - 2}}{_RESET} "
            else:
                line2 += " " * (col_w + 1)
        print(line2)
        print()

    print(f"{_DIM}Legend: 📍=milestones  ⏰=deadline  green<7d  yellow<21d  red>21d{_RESET}")
    print()


def render_stacked(apps: list[dict], stage_filter: str = "") -> None:
    """Fallback: stacked sections for narrow terminals."""
    today = date.today().isoformat()
    by_stage: dict[str, list] = {s: [] for s in STAGE_ORDER}
    for app in apps:
        s = app["stage"]
        by_stage.get(s, by_stage["applied"]).append(app)

    active = ([stage_filter] if stage_filter else
              [s for s in STAGE_ORDER if by_stage[s]])

    print(f"\n📋 Application Board — {today}  ({len(apps)} total)\n")
    for s in active:
        cards = by_stage[s]
        if not cards:
            continue
        label, emoji, _ = STAGES[s]
        print(f"{_BOLD}{emoji} {label} ({len(cards)}){_RESET}")
        for app in cards:
            days_b = _days_badge(app["days"])
            dl = f"  ⏰ {app['deadline']}" if app["deadline"] else ""
            print(f"  • {_BOLD}{app['company']}{_RESET}  {days_b}{dl}")
            if app["position"]:
                print(f"    {_DIM}{app['position']}{_RESET}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Terminal Kanban board for job applications"
    )
    parser.add_argument(
        "--stage",
        choices=STAGE_ORDER,
        default="",
        help="Filter to one stage"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw data as JSON"
    )
    args = parser.parse_args()

    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ applications/ directory not found")
        return 1

    apps = collect_apps(apps_dir)

    if not apps:
        print("📋 No applications found.")
        return 0

    if args.json:
        print(json.dumps(apps, indent=2, ensure_ascii=False))
        return 0

    term_width = shutil.get_terminal_size((80, 40)).columns
    if term_width >= 100:
        render_board(apps, stage_filter=args.stage)
    else:
        render_stacked(apps, stage_filter=args.stage)

    return 0


if __name__ == "__main__":
    sys.exit(main())
