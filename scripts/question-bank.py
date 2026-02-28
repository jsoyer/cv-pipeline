#!/usr/bin/env python3
"""
Aggregate interview questions from all prep.md files into a searchable Q&A bank.

Parses applications/*/prep.md, deduplicates questions (60% token-overlap
threshold), and writes question-bank.md to the repo root.

Usage:
    scripts/question-bank.py [--name NAME] [--json]

Options:
    --name NAME   Include only this application
    --json        Output JSON
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

# Section header keywords → canonical category
CATEGORY_MAP = {
    "questions to ask": "Questions to Ask",
    "questions":        "Questions to Ask",
    "to ask":           "Questions to Ask",
    "role":             "Questions to Ask — Role",
    "company":          "Questions to Ask — Company",
    "culture":          "Questions to Ask — Culture",
    "team":             "Questions to Ask — Team",
    "potential gaps":   "Potential Gaps",
    "gaps":             "Potential Gaps",
    "checklist":        "Checklist",
    "star":             "STAR Stories",
    "stories":          "STAR Stories",
    "behavioral":       "STAR Stories",
}

STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "your", "our", "their", "its",
    "this", "that", "these", "those", "what", "how", "why", "when",
    "where", "who", "which",
})

QUESTION_WORDS = frozenset({
    "what", "how", "why", "when", "where", "who", "which",
    "is", "are", "do", "does", "can", "will", "would", "could", "should",
    "have", "has",
})


def _tokenize(text: str) -> frozenset:
    words = re.findall(r"[a-z][a-z']+", text.lower())
    return frozenset(w for w in words if w not in STOP_WORDS and len(w) > 2)


def _overlap(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _strip_item_marker(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^-\s*\[[ xX]\]\s*", "", line)  # checkbox
    line = re.sub(r"^[-*]\s+", "", line)             # bullet
    line = re.sub(r"^\d+\.\s+", "", line)            # numbered
    return line.strip()


def _ensure_question_mark(text: str) -> str:
    text = text.strip()
    if not text or text.endswith("?") or text.endswith("."):
        return text
    first_word = text.split()[0].lower() if text.split() else ""
    if first_word in QUESTION_WORDS:
        text = text + "?"
    return text


def _classify_section(header: str) -> str | None:
    h = header.lower().strip()
    for key, cat in CATEGORY_MAP.items():
        if key in h:
            return cat
    return None


def parse_prep_md(path: Path) -> dict:
    """
    Parse a prep.md file.
    Returns dict: {category_name: [item_text, ...]}
    """
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return {}

    sections = defaultdict(list)
    current_cat = None
    parent_cat = None

    for line in content.splitlines():
        # ## header → category
        if line.startswith("## "):
            header = line[3:].strip()
            cat = _classify_section(header)
            if cat:
                current_cat = cat
                parent_cat = cat
            else:
                current_cat = None
                parent_cat = None
            continue

        # ### subheader → refine category
        if line.startswith("### "):
            header = line[4:].strip()
            if parent_cat:
                sub_cat = _classify_section(header)
                if sub_cat and "—" in sub_cat:
                    current_cat = sub_cat
                else:
                    current_cat = f"{parent_cat} — {header}"
            continue

        if not current_cat:
            continue

        stripped = line.strip()
        is_list_item = (
            stripped.startswith("-")
            or stripped.startswith("*")
            or re.match(r"^\d+\.", stripped)
        )
        if stripped and is_list_item:
            item = _strip_item_marker(stripped)
            if item:
                item = _ensure_question_mark(item)
                sections[current_cat].append(item)

    return dict(sections)


def deduplicate(items_with_sources: list) -> list:
    """
    Deduplicate list of (text, app_name) tuples.
    Returns list of (text, count, source_apps) sorted by count desc.
    """
    clusters = []  # [(canonical_text, [app_name, ...], tokens)]

    for text, app_name in items_with_sources:
        tokens = _tokenize(text)
        if not tokens:
            continue

        best_cluster = None
        best_overlap = 0.0
        for i, (_, _, ctokens) in enumerate(clusters):
            ov = _overlap(tokens, ctokens)
            if ov > best_overlap:
                best_overlap = ov
                best_cluster = i

        if best_cluster is not None and best_overlap >= 0.6:
            _, sources, ctokens = clusters[best_cluster]
            sources.append(app_name)
            clusters[best_cluster] = (clusters[best_cluster][0], sources, ctokens | tokens)
        else:
            clusters.append((text, [app_name], tokens))

    return sorted(
        [(text, len(sources), sources) for text, sources, _ in clusters],
        key=lambda x: -x[1],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate questions from all prep.md files"
    )
    parser.add_argument(
        "--name", default="", metavar="APP_NAME",
        help="Only include this application"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    apps_dir = _REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ No applications/ directory found")
        sys.exit(1)

    prep_files = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        if args.name and d.name != args.name:
            continue
        prep_path = d / "prep.md"
        if prep_path.exists():
            prep_files.append((d.name, prep_path))

    if not prep_files:
        if args.name:
            print(f"⚠️  No prep.md found for: {args.name}")
        else:
            print("⚠️  No prep.md files found in any application directory")
        return 0

    print(f"📚 Question Bank — {len(prep_files)} prep.md file{'s' if len(prep_files) != 1 else ''}")

    # Collect items by category
    all_items: dict[str, list] = defaultdict(list)
    for app_name, prep_path in prep_files:
        sections = parse_prep_md(prep_path)
        for cat, items in sections.items():
            for item in items:
                all_items[cat].append((item, app_name))

    if not all_items:
        print("⚠️  No structured content found in prep.md files")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")

    sections_md = [
        "# Question Bank\n",
        f"*{len(prep_files)} applications · Updated: {today}*\n",
        "\n---\n",
    ]
    json_data = {}

    cat_order = [
        "Questions to Ask",
        "Questions to Ask — Role",
        "Questions to Ask — Company",
        "Questions to Ask — Culture",
        "Questions to Ask — Team",
        "Potential Gaps",
        "Checklist",
        "STAR Stories",
    ]
    all_cats = cat_order + [c for c in sorted(all_items.keys()) if c not in cat_order]

    for cat in all_cats:
        if cat not in all_items:
            continue
        deduped = deduplicate(all_items[cat])
        if not deduped:
            continue

        print(f"   {cat}: {len(deduped)} unique items ({len(all_items[cat])} raw)")
        sections_md.append(f"\n## {cat}\n")
        json_data[cat] = []

        for text, count, sources in deduped:
            suffix = f" *({count} apps)*" if count > 1 else ""
            if cat in ("Potential Gaps", "Checklist"):
                sections_md.append(f"- [ ] {text}{suffix}")
            else:
                sections_md.append(f"- {text}{suffix}")
            json_data[cat].append({"text": text, "count": count, "apps": sources})

        sections_md.append("")

    content = "\n".join(sections_md)
    out_path = _REPO_ROOT / "question-bank.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n✅ Saved to {out_path}")

    if args.json:
        print(json.dumps(json_data, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
