#!/usr/bin/env python3
"""
Export CV data from YAML to various formats.

Usage:
    scripts/export.py json          # JSON output
    scripts/export.py markdown      # Markdown output
    scripts/export.py text          # Plain text output
    scripts/export.py json -o cv.json  # Write to file
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)


def strip_bold(text):
    """Remove **bold** markers for plain text output."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def render_json(data):
    """Export as JSON."""
    return json.dumps(data, indent=2, ensure_ascii=False)


def render_markdown(data):
    """Export as Markdown."""
    p = data["personal"]
    lines = [
        f"# {p['first_name']} {p['last_name']}",
        f"**{p['position']}** | {p['address']}",
        f"{p['email']} | [LinkedIn](https://linkedin.com/in/{p['linkedin']})",
        "",
        "## Profile",
        "",
        strip_bold(data["profile"]),
        "",
        "## Skills",
        "",
    ]
    for s in data["skills"]:
        lines.append(f"- **{s['category']}:** {s['items']}")
    lines.append("")

    lines.append("## Key Wins")
    lines.append("")
    for w in data["key_wins"]:
        lines.append(f"- **{w['title']}:** {strip_bold(w['text'])}")
    lines.append("")

    lines.append("## Experience")
    lines.append("")
    for e in data["experience"]:
        lines.append(f"### {e['title']} — {e['company']} ({e['dates']})")
        lines.append(f"*{e['location']}*")
        lines.append("")
        for it in e.get("items", []):
            text = strip_bold(it["text"])
            label = it.get("label")
            if label:
                lines.append(f"- **{label}:** {text}")
            else:
                lines.append(f"- {text}")
        lines.append("")

    lines.append("## Early Career")
    lines.append("")
    for e in data["early_career"]:
        lines.append(f"- **{e['title']}** — {e['company']}, {e['location']} ({e['dates']})")
    lines.append("")

    lines.append("## Education")
    lines.append("")
    for e in data["education"]:
        note = f" — {e['note']}" if e.get("note") else ""
        lines.append(f"- **{e['degree']}** — {e['school']}, {e['location']} ({e['dates']}){note}")
    lines.append("")

    lines.append("## Certifications")
    lines.append("")
    for c in data["certifications"]:
        lines.append(f"- **{c['name']}** — {c['institution']} ({c['date']})")
    lines.append("")

    lines.append("## Awards & Publications")
    lines.append("")
    lines.append(strip_bold(data["awards"]))
    lines.append("")
    lines.append(strip_bold(data["publications"]))
    lines.append("")

    lines.append("## Languages")
    lines.append("")
    lines.append(", ".join(data["languages"]))
    lines.append("")

    lines.append("## Interests")
    lines.append("")
    lines.append(", ".join(data["interests"]))
    lines.append("")

    return "\n".join(lines)


def render_text(data):
    """Export as plain text (for job portal paste)."""
    p = data["personal"]
    lines = [
        f"{p['first_name']} {p['last_name']}",
        f"{p['position']}",
        f"{p['address']} | {p['mobile']} | {p['email']}",
        f"LinkedIn: linkedin.com/in/{p['linkedin']}",
        "",
        "=" * 60,
        "PROFILE",
        "=" * 60,
        "",
        strip_bold(data["profile"]),
        "",
        "=" * 60,
        "SKILLS",
        "=" * 60,
        "",
    ]
    for s in data["skills"]:
        lines.append(f"{s['category']}: {s['items']}")
    lines.append("")

    lines.append("=" * 60)
    lines.append("KEY WINS")
    lines.append("=" * 60)
    lines.append("")
    for w in data["key_wins"]:
        lines.append(f"* {w['title']}: {strip_bold(w['text'])}")
    lines.append("")

    lines.append("=" * 60)
    lines.append("EXPERIENCE")
    lines.append("=" * 60)
    lines.append("")
    for e in data["experience"]:
        lines.append(f"{e['title']} — {e['company']}")
        lines.append(f"{e['location']} | {e['dates']}")
        for it in e.get("items", []):
            text = strip_bold(it["text"])
            label = it.get("label")
            if label:
                lines.append(f"  - {label}: {text}")
            else:
                lines.append(f"  - {text}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("EARLY CAREER")
    lines.append("=" * 60)
    lines.append("")
    for e in data["early_career"]:
        lines.append(f"{e['title']} — {e['company']}, {e['location']} ({e['dates']})")
    lines.append("")

    lines.append("=" * 60)
    lines.append("EDUCATION")
    lines.append("=" * 60)
    lines.append("")
    for e in data["education"]:
        note = f" — {e['note']}" if e.get("note") else ""
        lines.append(f"{e['degree']} — {e['school']}, {e['location']} ({e['dates']}){note}")
    lines.append("")

    lines.append("=" * 60)
    lines.append("CERTIFICATIONS")
    lines.append("=" * 60)
    lines.append("")
    for c in data["certifications"]:
        lines.append(f"{c['name']} — {c['institution']} ({c['date']})")
    lines.append("")

    lines.append("=" * 60)
    lines.append("AWARDS & PUBLICATIONS")
    lines.append("=" * 60)
    lines.append("")
    lines.append(strip_bold(data["awards"]))
    lines.append(strip_bold(data["publications"]))
    lines.append("")

    lines.append(f"Languages: {', '.join(data['languages'])}")
    lines.append(f"Interests: {', '.join(data['interests'])}")
    lines.append("")

    return "\n".join(lines)


FORMATS = {
    "json": render_json,
    "markdown": render_markdown,
    "md": render_markdown,
    "text": render_text,
    "txt": render_text,
}


def main():
    parser = argparse.ArgumentParser(description="Export CV data to various formats")
    parser.add_argument("format", choices=["json", "markdown", "md", "text", "txt"],
                        help="Output format")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument("-d", "--data", default="data/cv.yml",
                        help="YAML data file (default: data/cv.yml)")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"❌ Data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    result = FORMATS[args.format](data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"✅ Exported to {args.output}", file=sys.stderr)
    else:
        print(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
