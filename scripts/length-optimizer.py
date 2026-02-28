#!/usr/bin/env python3
"""Analyze CV section lengths vs 2-page constraint."""

import os
import re
import sys
import yaml
from pathlib import Path

WORKDIR = Path(os.environ.get("WORKDIR", Path(__file__).resolve().parent.parent))

SECTION_PATTERNS = {
    "Profile": r"\\cvsection\{Profile\}",
    "Skills": r"\\cvsection\{Strategic Skills Portfolio\}",
    "Key Wins": r"\\cvsection\{Strategic Key Wins",
    "Experience": r"\\cvsection\{Work Experience\}",
    "Early Career": r"\\cvsection\{Early Career\}",
    "Education": r"\\cvsection\{Education\}",
    "Certifications": r"\\cvsection\{Continuing Education\}",
    "Awards": r"\\cvsection\{Awards",
    "Languages": r"\\cvsection\{Languages",
}


def count_section_lines(tex_path):
    """Estimate lines per section by parsing LaTeX."""
    with open(tex_path, encoding="utf-8") as f:
        content = f.read()

    sections = {}
    lines = content.split("\n")

    current_section = None
    section_lines = []

    for line in lines:
        found = False
        for section_name, pattern in SECTION_PATTERNS.items():
            if re.search(pattern, line):
                if current_section:
                    sections[current_section] = len(section_lines)
                current_section = section_name
                section_lines = []
                found = True
                break
        if not found and current_section:
            if line.strip() and not line.strip().startswith("%"):
                section_lines.append(line)

    if current_section:
        sections[current_section] = len(section_lines)

    return sections


def analyze_pdf_pages(pdf_path):
    """Try to estimate pages from PDF or use page count."""
    if not pdf_path.exists():
        return None

    # Use pdftotext if available
    import subprocess

    try:
        result = subprocess.run(
            ["pdftotext", str(pdf_path), "-"], capture_output=True, text=True
        )
        if result.returncode == 0:
            text = result.stdout
            pages = text.count("\f") + 1
            return pages
    except FileNotFoundError:
        pass

    return None


def main():
    cv_tex = WORKDIR / "CV.tex"
    cv_pdf = WORKDIR / "CV.pdf"

    if not cv_tex.exists():
        print("❌ CV.tex not found. Run: make render")
        return 1

    print("📊 CV Length Analysis")
    print("=" * 50)
    print()

    # Section analysis
    sections = count_section_lines(cv_tex)

    print("📄 Estimated section lengths (non-comment lines):")
    total = 0
    for section, lines in sections.items():
        pct = lines / sum(sections.values()) * 100 if sections else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {section:20s} {lines:4d} lines ({pct:5.1f}%) {bar}")
        total += lines

    print(f"  {'─' * 50}")
    print(f"  {'TOTAL':20s} {total:4d} lines")
    print()

    # Page estimation
    pages = analyze_pdf_pages(cv_pdf)
    if pages:
        print(f"📑 PDF pages: {pages}")
        if pages > 2:
            print("⚠️  WARNING: CV exceeds 2-page limit!")
            print("   Recommendations:")
            for section, lines in sorted(sections.items(), key=lambda x: -x[1]):
                if lines > 50:
                    print(f"   - Consider reducing {section} ({lines} lines)")
    else:
        print("⚠️  Could not determine page count (install poppler-utils)")

    print()

    # Recommendations
    print("💡 Recommendations:")
    if "Experience" in sections and sections["Experience"] > 150:
        print("   - Experience section is long. Consider:")
        print("     * Removing early jobs (keep last 10-15 years)")
        print("     * Shortening job descriptions to 2-3 bullets each")
        print("     * Focusing on achievements over responsibilities")

    if "Skills" in sections and sections["Skills"] > 80:
        print("   - Skills section could be condensed")
        print("     * Use single line per category instead of detailed lists")

    if "Early Career" in sections:
        print("   - Early Career section:")
        print("     * Consider removing or moving to brief mentions")
        print("     * Recruiters focus on recent 10 years")

    return 0


if __name__ == "__main__":
    sys.exit(main())
