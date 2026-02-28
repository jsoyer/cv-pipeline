#!/usr/bin/env python3
"""
Export CV (and Cover Letter) as ATS-safe plain text.

Without <app-dir>: data/cv.yml → CV.txt (repo root)
With <app-dir>:    cv-tailored.yml (or data/cv.yml) → applications/NAME/CV.txt
                   coverletter.yml                  → applications/NAME/CoverLetter.txt

Text conversion rules:
  - **bold** markers stripped (ATS reads plain text)
  - -- date ranges converted to – (en-dash)
  - Section dividers: ─ × 77
  - Lines wrapped at 78 characters

Usage:
    scripts/ats-text.py [<app-dir>] [--no-cl] [-o output.txt]
"""

import argparse
import re
import sys
import textwrap
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

DIVIDER = "─" * 77


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _strip_bold(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(text or ""))


def _clean(text: str) -> str:
    return _strip_bold(text).replace(" -- ", " – ")


def _wrap(text: str, width: int = 78, indent: str = "") -> str:
    return textwrap.fill(
        _clean(text), width=width,
        initial_indent=indent, subsequent_indent=indent,
    )


def _flatten_items(items) -> list:
    """Flatten experience items (str or {label, text}) to plain text."""
    result = []
    if not items:
        return result
    for item in items:
        if isinstance(item, str):
            result.append(_clean(item))
        elif isinstance(item, dict):
            text  = _clean(item.get("text", ""))
            label = _clean(item.get("label", ""))
            if label and text:
                result.append(f"{label}: {text}")
            elif text:
                result.append(text)
            elif label:
                result.append(label)
    return result


def _render_list_field(field) -> str:
    """Render languages/interests (list of dicts, list of str, or str)."""
    if isinstance(field, list):
        parts = []
        for item in field:
            if isinstance(item, dict):
                n   = item.get("name", "") or item.get("language", "")
                lvl = item.get("level", "") or item.get("fluency", "")
                parts.append(f"{n} ({lvl})" if lvl else n)
            else:
                parts.append(_clean(str(item)))
        return ", ".join(parts)
    elif isinstance(field, str):
        return _clean(field)
    return ""


# ---------------------------------------------------------------------------
# CV plain-text renderer
# ---------------------------------------------------------------------------

def render_cv(data: dict) -> str:
    p = data.get("personal", {})
    lines = []

    # Header
    name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip().upper()
    position = _clean(p.get("position", ""))
    contact_parts = [x for x in [
        p.get("address", ""),
        p.get("email", ""),
        p.get("mobile", "") or p.get("phone", ""),
    ] if x]
    if p.get("linkedin"):
        contact_parts.append(f"linkedin.com/in/{p['linkedin']}")

    lines.append(name)
    if position:
        lines.append(position)
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    # Profile
    profile = data.get("profile", "")
    if profile:
        lines += ["PROFILE", DIVIDER, _wrap(profile), ""]

    # Skills
    skills = data.get("skills", [])
    if skills:
        lines += ["SKILLS", DIVIDER]
        for skill in skills:
            cat   = _clean(skill.get("category", ""))
            items = skill.get("items", "")
            if isinstance(items, str):
                items_str = _clean(items)
            elif isinstance(items, list):
                items_str = ", ".join(_clean(str(i)) for i in items)
            else:
                items_str = ""
            if cat and items_str:
                prefix  = f"{cat}: "
                wrapped = textwrap.fill(
                    items_str, width=78,
                    initial_indent=prefix,
                    subsequent_indent=" " * len(prefix),
                )
                lines.append(wrapped)
        lines.append("")

    # Key Achievements
    key_wins = data.get("key_wins", [])
    if key_wins:
        lines += ["KEY ACHIEVEMENTS", DIVIDER]
        for win in key_wins:
            title = _clean(win.get("title", ""))
            text  = _clean(win.get("text", ""))
            if title and text:
                wrapped = textwrap.fill(
                    f"• {title}: {text}", width=78, subsequent_indent="  "
                )
            elif title:
                wrapped = f"• {title}"
            else:
                continue
            lines.append(wrapped)
        lines.append("")

    # Professional Experience
    experience = data.get("experience", [])
    if experience:
        lines += ["PROFESSIONAL EXPERIENCE", DIVIDER]
        for exp in experience:
            title    = _clean(exp.get("title", ""))
            company  = _clean(exp.get("company", ""))
            location = _clean(exp.get("location", ""))
            dates    = _clean(exp.get("dates", ""))
            header_parts = [x for x in [title, company, location, dates] if x]
            lines.append(" | ".join(header_parts))
            for item in _flatten_items(exp.get("items", [])):
                lines.append(textwrap.fill(f"• {item}", width=78, subsequent_indent="  "))
            lines.append("")

    # Early Career
    early_career = data.get("early_career", [])
    if early_career:
        lines += ["EARLY CAREER", DIVIDER]
        for exp in early_career:
            title    = _clean(exp.get("title", ""))
            company  = _clean(exp.get("company", ""))
            location = _clean(exp.get("location", ""))
            dates    = _clean(exp.get("dates", ""))
            header_parts = [x for x in [title, company, location, dates] if x]
            lines.append(" | ".join(header_parts))
            for item in _flatten_items(exp.get("items", [])):
                lines.append(textwrap.fill(f"• {item}", width=78, subsequent_indent="  "))
            lines.append("")

    # Education
    education = data.get("education", [])
    if education:
        lines += ["EDUCATION", DIVIDER]
        for edu in education:
            degree      = _clean(edu.get("degree", ""))
            institution = _clean(edu.get("institution", ""))
            location    = _clean(edu.get("location", ""))
            dates       = _clean(edu.get("dates", ""))
            header_parts = [x for x in [degree, institution, location, dates] if x]
            lines.append(" | ".join(header_parts))
            if edu.get("description"):
                lines.append(_wrap(edu["description"], indent="  "))
        lines.append("")

    # Certifications
    certifications = data.get("certifications", [])
    if certifications:
        lines += ["CERTIFICATIONS", DIVIDER]
        for cert in certifications:
            cert_name   = _clean(cert.get("name", "") or cert.get("title", ""))
            institution = _clean(cert.get("institution", "") or cert.get("issuer", ""))
            dates       = _clean(cert.get("dates", ""))
            parts = [cert_name]
            if institution:
                parts.append(institution)
            if dates:
                parts.append(f"({dates})")
            lines.append(f"• {' — '.join(parts)}")
        lines.append("")

    # Awards & Publications
    awards = data.get("awards", "")
    pubs   = data.get("publications", "")
    if awards or pubs:
        lines += ["AWARDS & PUBLICATIONS", DIVIDER]
        if awards:
            lines.append(_wrap(str(awards)))
        if pubs:
            lines.append(_wrap(str(pubs)))
        lines.append("")

    # Languages & Interests
    lang_str = _render_list_field(data.get("languages", []))
    int_str  = _render_list_field(data.get("interests", []))
    if lang_str or int_str:
        lines += ["LANGUAGES & INTERESTS", DIVIDER]
        if lang_str:
            lines.append(f"Languages: {lang_str}")
        if int_str:
            lines.append(f"Interests: {int_str}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cover letter plain-text renderer
# ---------------------------------------------------------------------------

def render_coverletter(cl_data: dict, personal: dict) -> str:
    p = personal
    lines = []

    # Sender header
    name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    contact_parts = [x for x in [
        p.get("address", ""),
        p.get("email", ""),
        p.get("mobile", "") or p.get("phone", ""),
    ] if x]
    lines.append(name)
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    # Date
    lines.append(date.today().strftime("%B %d, %Y"))
    lines.append("")

    # Recipient
    r = cl_data.get("recipient", {})
    if isinstance(r, dict):
        if r.get("name"):
            lines.append(_clean(r["name"]))
        if r.get("company"):
            lines.append(_clean(r["company"]))
    elif isinstance(r, str) and r:
        lines.append(_clean(r))
    lines.append("")

    # Re: line
    title = _clean(cl_data.get("title", ""))
    if title:
        lines += [f"Re: {title}", ""]

    # Salutation / opening
    opening = _clean(cl_data.get("opening", "Dear Hiring Manager,"))
    lines += [opening, ""]

    # Body sections
    for section in cl_data.get("sections", []):
        if isinstance(section, dict):
            sec_title = _clean(section.get("title", ""))
            content   = _clean(section.get("content", ""))
            if sec_title:
                lines += [sec_title.upper(), ""]
            if content:
                lines += [_wrap(content), ""]
        elif isinstance(section, str):
            lines += [_wrap(section), ""]

    # Closing paragraph
    closing_para = cl_data.get("closing_paragraph", "")
    if closing_para:
        lines += [_wrap(_clean(closing_para)), ""]

    # Sign-off
    closing = _clean(cl_data.get("closing", "Sincerely,"))
    lines += [closing, "", name]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export CV (and Cover Letter) as ATS-safe plain text"
    )
    parser.add_argument(
        "app_dir", nargs="?", default=None,
        help="Application directory (omit for master CV from data/cv.yml)"
    )
    parser.add_argument(
        "--no-cl", action="store_true",
        help="Skip Cover Letter export even if coverletter.yml exists"
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output file path (default: auto-detected)"
    )
    args = parser.parse_args()

    # Determine source and output paths
    if args.app_dir:
        app_dir = Path(args.app_dir)
        if not app_dir.is_dir():
            print(f"❌ Directory not found: {app_dir}")
            sys.exit(1)

        cv_data_path = app_dir / "cv-tailored.yml"
        if not cv_data_path.exists():
            cv_data_path = _REPO_ROOT / "data" / "cv.yml"
            print(f"ℹ️  No cv-tailored.yml found — using {cv_data_path}")

        cv_out_path = Path(args.output) if args.output else app_dir / "CV.txt"
    else:
        app_dir      = None
        cv_data_path = _REPO_ROOT / "data" / "cv.yml"
        cv_out_path  = Path(args.output) if args.output else _REPO_ROOT / "CV.txt"

    # Load and render CV
    if not cv_data_path.exists():
        print(f"❌ CV data not found: {cv_data_path}")
        sys.exit(1)

    with open(cv_data_path, encoding="utf-8") as f:
        cv_data = yaml.safe_load(f)

    print(f"📄 Rendering CV: {cv_data_path.name} → {cv_out_path}")
    cv_text = render_cv(cv_data)
    cv_out_path.write_text(cv_text, encoding="utf-8")
    print(f"   ✅ Saved: {cv_out_path} ({len(cv_text.splitlines())} lines)")

    # Cover letter (only when app-dir is provided and coverletter.yml exists)
    if app_dir and not args.no_cl:
        cl_path = app_dir / "coverletter.yml"
        if cl_path.exists():
            cl_out_path = app_dir / "CoverLetter.txt"
            with open(cl_path, encoding="utf-8") as f:
                cl_data = yaml.safe_load(f)

            personal = cv_data.get("personal", {})
            print(f"📨 Rendering Cover Letter: {cl_path.name} → {cl_out_path}")
            cl_text = render_coverletter(cl_data, personal)
            cl_out_path.write_text(cl_text, encoding="utf-8")
            print(f"   ✅ Saved: {cl_out_path} ({len(cl_text.splitlines())} lines)")
        else:
            print("ℹ️  No coverletter.yml found — skipping Cover Letter")

    return 0


if __name__ == "__main__":
    sys.exit(main())
