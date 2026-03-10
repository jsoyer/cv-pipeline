#!/usr/bin/env python3
"""
Generate Hugo-compatible JSON data files and _index.md from data/cv.yml.

Usage:
    scripts/hugo-export.py
    scripts/hugo-export.py -d data/cv.yml -o data/
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pyyaml required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def format_dates(text):
    """Replace LaTeX en-dash (--) with unicode en-dash (–)."""
    return text.replace(" -- ", " – ")


def strip_bold(text):
    """Remove **bold** markers for plain text output."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def items_to_markdown(items):
    """Convert cv.yml items list to a markdown string."""
    if not items:
        return ""
    lines = []
    for it in items:
        text = it.get("text", "")
        label = it.get("label")
        if label:
            lines.append(f"**{label}:** {text}")
        else:
            lines.append(text)
    return "  \n".join(lines)


def build_skills(data):
    return [{"name": s["category"], "icon": s.get("icon", ""), "details": s["items"]} for s in data["skills"]]


def build_achievements(data):
    return [{"title": w["title"], "description": w["text"]} for w in data["key_wins"]]


def build_experience(data):
    entries = []
    for e in data.get("experience", []):
        entries.append(
            {
                "role": e["title"],
                "company": e["company"],
                "location": e["location"],
                "range": format_dates(e["dates"]),
                "summary": items_to_markdown(e.get("items")),
            }
        )
    for e in data.get("early_career", []):
        entries.append(
            {
                "role": e["title"],
                "company": e["company"],
                "location": e["location"],
                "range": format_dates(e["dates"]),
                "summary": "",
            }
        )
    return entries


def build_education(data):
    return [
        {
            "school": e["school"],
            "degree": e["degree"],
            "major": "",
            "range": format_dates(e["dates"]),
            "location": e["location"],
            "notes": e.get("note", ""),
        }
        for e in data["education"]
    ]


def build_training(data):
    return [
        {
            "name": c["name"],
            "provider": c["institution"],
            "date": format_dates(c["date"]),
        }
        for c in data["certifications"]
    ]


def build_publications(data):
    awards = strip_bold(data.get("awards", "")).strip()
    publications = strip_bold(data.get("publications", "")).strip()
    entries = []
    if awards:
        entries.append({"title": "Quota Overachievement", "description": awards, "year": ""})
    if publications:
        entries.append({"title": "Press & Media Coverage", "description": publications, "year": ""})
    return entries


def build_interests(data):
    return [
        {"name": "Languages", "items": data["languages"]},
        {"name": "Interests", "items": data["interests"]},
    ]


def build_index_md(data):
    profile = strip_bold(data["profile"])
    return f'---\ntitle: "About Me"\n---\n\n{profile}\n'


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  {path}")


def main():
    parser = argparse.ArgumentParser(description="Generate Hugo JSON data files from cv.yml")
    parser.add_argument("-d", "--data", default="data/cv.yml", help="YAML source file")
    parser.add_argument("-o", "--output", default="data", help="Output directory for JSON files")
    args = parser.parse_args()

    data_path = Path(args.data)
    out_dir = Path(args.output)

    if not data_path.exists():
        print(f"Data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    out_dir.mkdir(parents=True, exist_ok=True)

    print("Generating Hugo data files:")
    write_json(out_dir / "skills.json", build_skills(data))
    write_json(out_dir / "achievements.json", build_achievements(data))
    write_json(out_dir / "experience.json", build_experience(data))
    write_json(out_dir / "education.json", build_education(data))
    write_json(out_dir / "training.json", build_training(data))
    write_json(out_dir / "publications.json", build_publications(data))
    write_json(out_dir / "interests.json", build_interests(data))

    index_path = out_dir / "_index.md"
    index_path.write_text(build_index_md(data), encoding="utf-8")
    print(f"  {index_path}")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
