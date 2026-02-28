#!/usr/bin/env python3
"""
Terminal flashcard quiz from interview prep notes.

Parses prep.md files across applications and runs an interactive
Q&A session in the terminal.

Usage:
    scripts/prep-quiz.py [<app-dir>]           # Quiz from one application
    scripts/prep-quiz.py                        # Quiz from all applications
    scripts/prep-quiz.py --category behavioral  # Filter by category
    scripts/prep-quiz.py --list                 # List available questions

Categories: behavioral | technical | company | to-ask | all (default)
Rating: 1=Missed  2=OK  3=Nailed it
"""

import argparse
import random
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

# ANSI colours
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_CYAN   = "\033[36m"
_BLUE   = "\033[34m"

CATEGORY_KEYWORDS = {
    "behavioral": ["behavioral", "behaviour", "situational", "star stories", "star story",
                   "tell me about", "experience", "background"],
    "technical":  ["technical", "architecture", "platform", "product", "demo", "use case"],
    "company":    ["company", "culture", "team", "why us", "strategy", "market"],
    "to-ask":     ["questions to ask", "ask the interviewer", "questions for", "to ask"],
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _classify_section(header: str) -> str:
    h = header.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in h for k in keywords):
            return cat
    return "general"


def parse_prep_md(path: Path) -> list[dict]:
    """Parse a prep.md file and return list of {question, answer, category, source}."""
    if not path.exists():
        return []

    text     = path.read_text(encoding="utf-8")
    sections = re.split(r"^(#{1,3} .+)$", text, flags=re.MULTILINE)
    cards    = []
    category = "general"

    i = 0
    while i < len(sections):
        part = sections[i].strip()

        # Section header
        if part.startswith("#"):
            header = re.sub(r"^#+\s*", "", part)
            category = _classify_section(header)
            i += 1
            continue

        # Extract Q&A from section body
        lines = [l.strip() for l in part.splitlines() if l.strip()]

        # STAR story blocks: bold header + body text
        star_match = re.findall(
            r"\*\*(.+?)\*\*[:\s]*(.+?)(?=\*\*|\Z)", part, re.DOTALL
        )
        if star_match and category == "behavioral":
            for q, a in star_match:
                q = q.strip(" :")
                a = a.strip()
                if len(q) > 5 and len(a) > 10:
                    cards.append({
                        "question": q + "?",
                        "answer":   a,
                        "category": category,
                        "source":   path.parent.name,
                    })
            i += 1
            continue

        # List items — treat as questions or checklist items
        for line in lines:
            # Strip list markers
            q = re.sub(r"^[-*•]\s*\[.\]\s*", "", line)
            q = re.sub(r"^[-*•]\s*", "", q)
            q = re.sub(r"^\d+\.\s*", "", q)
            q = q.strip()

            if len(q) < 10:
                continue

            # "to-ask" questions are Q only (no answer expected)
            if category == "to-ask":
                if not q.endswith("?"):
                    q += "?"
                cards.append({
                    "question": q,
                    "answer":   "(Your question to the interviewer — no answer needed)",
                    "category": "to-ask",
                    "source":   path.parent.name,
                })
            else:
                # Generic flashcard
                if not q.endswith("?") and not q.endswith("."):
                    q += "?"
                cards.append({
                    "question": q,
                    "answer":   "(Prepare your answer using the STAR method)",
                    "category": category,
                    "source":   path.parent.name,
                })

        i += 1

    return cards


def collect_cards(apps_dir: Path, name_filter: str = "") -> list[dict]:
    all_cards = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        if name_filter and name_filter.lower() not in d.name.lower():
            continue
        prep = d / "prep.md"
        if prep.exists():
            all_cards.extend(parse_prep_md(prep))
    return all_cards


# ---------------------------------------------------------------------------
# Quiz runner
# ---------------------------------------------------------------------------

CAT_LABEL = {
    "behavioral": f"{_YELLOW}Behavioral{_RESET}",
    "technical":  f"{_CYAN}Technical{_RESET}",
    "company":    f"{_BLUE}Company{_RESET}",
    "to-ask":     f"{_GREEN}To Ask{_RESET}",
    "general":    f"{_DIM}General{_RESET}",
}


def _clear_line():
    print("\033[2K\r", end="")


def run_quiz(cards: list[dict], shuffle: bool = True) -> None:
    if not cards:
        print("   No cards to quiz.")
        return

    if shuffle:
        cards = random.sample(cards, len(cards))

    total   = len(cards)
    ratings = []

    print(f"\n{_BOLD}📚 Quiz — {total} cards{_RESET}  "
          f"{_DIM}(Enter=reveal · 1=Missed · 2=OK · 3=Nailed){_RESET}\n")
    print(f"{_DIM}Press Ctrl+C to quit early.{_RESET}\n")
    print("─" * 60)

    try:
        for idx, card in enumerate(cards, 1):
            cat   = card.get("category", "general")
            src   = card.get("source", "")
            q     = card["question"]
            a     = card["answer"]

            cat_label = CAT_LABEL.get(cat, cat)
            print(f"\n{_BOLD}[{idx}/{total}]{_RESET}  {cat_label}  {_DIM}({src}){_RESET}")
            print(f"\n  {_BOLD}{q}{_RESET}\n")

            input(f"  {_DIM}Press Enter to reveal answer...{_RESET}")

            print(f"\n  {_GREEN}▶ {a}{_RESET}\n")

            # Rating
            while True:
                raw = input(
                    f"  Rate: {_RED}1=Missed{_RESET}  "
                    f"{_YELLOW}2=OK{_RESET}  "
                    f"{_GREEN}3=Nailed{_RESET}  > "
                ).strip()
                if raw in ("1", "2", "3"):
                    ratings.append(int(raw))
                    break
                if raw == "":
                    ratings.append(2)
                    break

            print("─" * 60)

    except KeyboardInterrupt:
        print(f"\n\n{_DIM}Quiz interrupted.{_RESET}")

    # Summary
    if not ratings:
        return

    done    = len(ratings)
    missed  = ratings.count(1)
    ok      = ratings.count(2)
    nailed  = ratings.count(3)
    avg     = sum(ratings) / done

    print(f"\n{_BOLD}📊 Session Summary{_RESET}  ({done}/{total} cards)\n")
    print(f"   {_RED}Missed  {missed:>3}{_RESET}  {'█' * missed}")
    print(f"   {_YELLOW}OK      {ok:>3}{_RESET}  {'█' * ok}")
    print(f"   {_GREEN}Nailed  {nailed:>3}{_RESET}  {'█' * nailed}")
    print(f"\n   Score: {avg:.1f}/3  —  ", end="")
    if avg >= 2.5:
        print(f"{_GREEN}Excellent! You're ready.{_RESET}")
    elif avg >= 1.8:
        print(f"{_YELLOW}Good — review the missed ones.{_RESET}")
    else:
        print(f"{_RED}Keep practising — focus on behavioral cards.{_RESET}")

    if missed > 0:
        print(f"\n{_DIM}Tip: re-run with --category behavioral to focus on missed areas.{_RESET}")
    print()


def list_cards(cards: list[dict]) -> None:
    by_cat: dict[str, list] = {}
    for c in cards:
        by_cat.setdefault(c.get("category", "general"), []).append(c)

    print(f"\n📋 Questions ({len(cards)} total)\n")
    for cat, items in sorted(by_cat.items()):
        label = CAT_LABEL.get(cat, cat)
        print(f"  {label}  ({len(items)})")
        for c in items:
            src = c.get("source", "")
            print(f"    • {c['question'][:80]}  {_DIM}({src}){_RESET}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Terminal flashcard quiz from interview prep notes"
    )
    parser.add_argument(
        "app_dir", nargs="?", default="",
        help="Application directory (default: all apps)"
    )
    parser.add_argument(
        "--category", "-c",
        choices=["behavioral", "technical", "company", "to-ask", "general", "all"],
        default="all",
        help="Filter by category (default: all)"
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List available questions without running quiz"
    )
    parser.add_argument(
        "--no-shuffle", action="store_true",
        help="Keep original order instead of shuffling"
    )
    args = parser.parse_args()

    apps_dir = _REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ applications/ directory not found")
        return 1

    name_filter = ""
    if args.app_dir:
        p = Path(args.app_dir)
        name_filter = p.name if p.is_dir() else args.app_dir

    cards = collect_cards(apps_dir, name_filter=name_filter)

    if not cards:
        print("❌ No prep.md files found.")
        print("   Generate one: make interview-prep NAME=...")
        return 1

    # Filter by category
    if args.category != "all":
        cards = [c for c in cards if c.get("category") == args.category]
        if not cards:
            print(f"❌ No cards found for category: {args.category}")
            return 1

    if args.list:
        list_cards(cards)
        return 0

    run_quiz(cards, shuffle=not args.no_shuffle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
