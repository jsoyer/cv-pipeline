#!/usr/bin/env python3
"""Generate Mermaid Gantt chart of all applications."""

import os
import sys
import yaml
from pathlib import Path
from datetime import datetime, timedelta

WORKDIR = Path(os.environ.get("WORKDIR", Path(__file__).resolve().parent.parent))


def get_applications():
    apps = []
    apps_dir = WORKDIR / "applications"
    if not apps_dir.exists():
        return apps

    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        meta_file = d / "meta.yml"
        if meta_file.exists():
            with open(meta_file, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        else:
            meta = {}

        name = d.name
        company = meta.get("company", name.split("-", 2)[-1].replace("-", " ").title())
        position = meta.get("position", "Unknown")
        created = meta.get("created", name.split("-")[0] + "-01")
        deadline = meta.get("deadline", "")
        status = meta.get("status", "pending")

        apps.append(
            {
                "name": name,
                "company": company,
                "position": position,
                "created": created,
                "deadline": deadline,
                "status": status,
            }
        )
    return apps


def generate_mermaid(apps):
    lines = ["# Applications Timeline", "```mermaid", "gantt"]
    lines.append("    title Job Application Timeline")
    lines.append("    dateFormat YYYY-MM-DD")
    lines.append("    axisFormat %b %Y")
    lines.append("")

    # Group by status
    for app in apps:
        status_emoji = {
            "pending": "📋",
            "applied": "✅",
            "interview": "🎯",
            "rejected": "❌",
            "offer": "💰",
        }.get(app["status"], "📋")
        title = f"{status_emoji} {app['company']} - {app['position']}"

        # Timeline: created to deadline or +60 days if no deadline
        start = app["created"]
        # Handle YYYY-MM format (add day)
        if len(start) == 7:
            start = start + "-01"
        if app["deadline"]:
            end = app["deadline"]
        else:
            # Default 60 days timeline
            end_date = datetime.strptime(start, "%Y-%m-%d") + timedelta(days=60)
            end = end_date.strftime("%Y-%m-%d")

        lines.append(f"    {title} :{start}, {end}")

    lines.append("```")
    return "\n".join(lines)


def main():
    apps = get_applications()

    if not apps:
        print("No applications found.")
        return 1

    # Generate mermaid
    mermaid = generate_mermaid(apps)
    print(mermaid)

    # Also save to file
    output = WORKDIR / "applications.md"
    with open(output, "w", encoding="utf-8") as f:
        f.write(mermaid)

    print(f"\n✅ Saved to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
