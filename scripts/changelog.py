#!/usr/bin/env python3
"""
Generate a changelog of CV modifications across applications.

Usage:
    scripts/changelog.py                # terminal output
    scripts/changelog.py --markdown     # markdown output
"""

import re
import subprocess
import sys
from pathlib import Path


def get_diff_summary(master_file, app_file):
    """Get a summary of differences between master and application file."""
    try:
        result = subprocess.run(
            ["diff", "-u", str(master_file), str(app_file)],
            capture_output=True, text=True, timeout=5
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode == 0:
        return {"status": "identical", "added": [], "removed": [], "stats": "no changes"}

    added = []
    removed = []
    for line in result.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            clean = line[1:].strip()
            if clean and not clean.startswith("%") and len(clean) > 5:
                added.append(clean)
        elif line.startswith("-") and not line.startswith("---"):
            clean = line[1:].strip()
            if clean and not clean.startswith("%") and len(clean) > 5:
                removed.append(clean)

    return {
        "status": "modified",
        "added": added,
        "removed": removed,
        "stats": f"+{len(added)}/-{len(removed)} lines",
    }


def detect_sections_changed(diff):
    """Detect which CV sections were modified."""
    patterns = {
        "Profile": r"cvparagraph|profile",
        "Skills": r"cvskill|skills",
        "Key Wins": r"key.wins|business.impact",
        "Experience": r"cventry|cventries|experience",
        "Education": r"education",
        "Certifications": r"certification|continuing",
    }

    text = " ".join(diff.get("added", []) + diff.get("removed", [])).lower()
    return sorted({s for s, p in patterns.items() if re.search(p, text)})


def main():
    markdown = "--markdown" in sys.argv

    apps_dir = Path("applications")
    if not apps_dir.exists():
        print("No applications/ directory found.")
        return 0

    apps = sorted([d for d in apps_dir.iterdir() if d.is_dir()], reverse=True)
    if not apps:
        print("No applications found.")
        return 0

    if markdown:
        print("# CV Changelog\n")
        print("Modifications across tailored applications vs master CV.\n")
    else:
        print("📝 CV Changelog")
        print("   Modifications vs master CV\n")

    for app_dir in apps:
        name = app_dir.name
        cv_files = list(app_dir.glob("CV - *.tex"))
        cl_files = list(app_dir.glob("CoverLetter - *.tex"))

        cv_diff = get_diff_summary("CV.tex", cv_files[0]) if cv_files and Path("CV.tex").exists() else None
        cl_diff = get_diff_summary("CoverLetter.tex", cl_files[0]) if cl_files and Path("CoverLetter.tex").exists() else None

        if markdown:
            print(f"## {name}\n")
            if cv_diff:
                sections = detect_sections_changed(cv_diff)
                print(f"**CV:** {cv_diff['stats']}")
                if sections:
                    print(f"**Sections:** {', '.join(sections)}")
                if cv_diff["added"][:5]:
                    print("\nKey additions:")
                    for line in cv_diff["added"][:5]:
                        print(f"- `{line[:80]}`")
                print("")
            if cl_diff and cl_diff["status"] != "identical":
                print(f"**Cover Letter:** {cl_diff['stats']}\n")
        else:
            print(f"{'═' * 65}")
            print(f"📁 {name}")
            if cv_diff:
                if cv_diff["status"] == "identical":
                    print("   CV:       ⚠️  Not tailored")
                else:
                    sections = detect_sections_changed(cv_diff)
                    print(f"   CV:       📝 {cv_diff['stats']}")
                    if sections:
                        print(f"   Sections: {', '.join(sections)}")
                    for line in cv_diff["added"][:3]:
                        print(f"     + {line[:70]}")
            else:
                print("   CV:       ❌ Not found")
            if cl_diff:
                if cl_diff["status"] == "identical":
                    print("   CL:       ⚠️  Not tailored")
                else:
                    print(f"   CL:       📝 {cl_diff['stats']}")
            print("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
