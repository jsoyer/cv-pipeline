#!/usr/bin/env python3
"""
Export data/cv.yml to JSON Resume v1.0.0 format.

JSON Resume schema: https://jsonresume.org/schema/

Usage:
    scripts/json-resume.py [-d data/cv.yml] [-o cv.json]
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT

MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _strip_bold(text: str) -> str:
    """Remove **bold** markers."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(text or ""))


def _parse_date_range(dates_str: str) -> tuple:
    """
    Parse date range like "Jan. 2022 -- Present" or "2003 -- 2007".
    Returns (startDate, endDate) as ISO strings.
    """
    if not dates_str:
        return "", ""
    parts = re.split(r"\s*--\s*", str(dates_str))

    def parse_one(s):
        s = s.strip().rstrip(".")
        if s.lower() in ("present", "now", "current", ""):
            return ""
        # "Jan. 2022" or "Jan 2022"
        m = re.match(r"([A-Za-z]+)\.?\s+(\d{4})", s)
        if m:
            month_abbr = m.group(1).lower()[:3]
            year = m.group(2)
            month = MONTH_MAP.get(month_abbr, "01")
            return f"{year}-{month}"
        # Year only: "2003"
        m2 = re.match(r"(\d{4})$", s)
        if m2:
            return m2.group(1)
        return s

    start = parse_one(parts[0]) if len(parts) > 0 else ""
    end   = parse_one(parts[1]) if len(parts) > 1 else ""
    return start, end


def _flatten_items(items) -> list:
    """Flatten experience items (str or {label, text}) to plain text."""
    result = []
    if not items:
        return result
    for item in items:
        if isinstance(item, str):
            result.append(_strip_bold(item))
        elif isinstance(item, dict):
            text  = item.get("text", "")
            label = item.get("label", "")
            if label and text:
                result.append(_strip_bold(f"{label}: {text}"))
            elif text:
                result.append(_strip_bold(text))
            elif label:
                result.append(_strip_bold(label))
    return result


def build_basics(personal: dict, profile: str) -> dict:
    p = personal
    basics = {
        "name":    f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
        "label":   p.get("position", ""),
        "email":   p.get("email", ""),
        "phone":   p.get("mobile", "") or p.get("phone", ""),
        "summary": _strip_bold(profile or ""),
        "location": {"address": p.get("address", "")},
        "profiles": [],
    }
    if p.get("url") or p.get("website"):
        basics["url"] = p.get("url") or p.get("website", "")
    if p.get("linkedin"):
        basics["profiles"].append({
            "network":  "LinkedIn",
            "username": p["linkedin"],
            "url":      f"https://www.linkedin.com/in/{p['linkedin']}",
        })
    if p.get("github"):
        basics["profiles"].append({
            "network":  "GitHub",
            "username": p["github"],
            "url":      f"https://github.com/{p['github']}",
        })
    return basics


def build_work(experience: list, early_career: list = None) -> list:
    work = []
    for exp in (experience or []):
        start, end = _parse_date_range(exp.get("dates", ""))
        entry = {
            "name":       exp.get("company", ""),
            "position":   exp.get("title", ""),
            "location":   exp.get("location", ""),
            "startDate":  start,
            "endDate":    end,
            "highlights": _flatten_items(exp.get("items", [])),
        }
        if exp.get("description"):
            entry["summary"] = _strip_bold(exp["description"])
        work.append(entry)
    for exp in (early_career or []):
        start, end = _parse_date_range(exp.get("dates", ""))
        entry = {
            "name":       exp.get("company", ""),
            "position":   exp.get("title", ""),
            "location":   exp.get("location", ""),
            "startDate":  start,
            "endDate":    end,
            "highlights": _flatten_items(exp.get("items", [])),
        }
        work.append(entry)
    return work


def build_education(education: list) -> list:
    result = []
    for edu in (education or []):
        start, end = _parse_date_range(edu.get("dates", ""))
        entry = {
            "institution": edu.get("institution", ""),
            "area":        edu.get("degree", ""),
            "studyType":   edu.get("type", ""),
            "startDate":   start,
            "endDate":     end,
            "location":    edu.get("location", ""),
        }
        if edu.get("score") or edu.get("gpa"):
            entry["score"] = str(edu.get("score") or edu.get("gpa", ""))
        result.append(entry)
    return result


def build_skills(skills: list) -> list:
    result = []
    for skill in (skills or []):
        items = skill.get("items", "")
        if isinstance(items, str):
            keywords = [k.strip() for k in items.split(",") if k.strip()]
        elif isinstance(items, list):
            keywords = [_strip_bold(str(k)) for k in items]
        else:
            keywords = []
        result.append({
            "name":     skill.get("category", ""),
            "keywords": keywords,
        })
    return result


def build_certificates(certifications: list) -> list:
    result = []
    for cert in (certifications or []):
        start, _ = _parse_date_range(cert.get("dates", ""))
        entry = {
            "name":   cert.get("name", "") or cert.get("title", ""),
            "issuer": cert.get("institution", "") or cert.get("issuer", ""),
            "date":   start,
        }
        if cert.get("url"):
            entry["url"] = cert["url"]
        result.append(entry)
    return result


def build_projects(key_wins: list) -> list:
    result = []
    for win in (key_wins or []):
        result.append({
            "name":        win.get("title", ""),
            "description": _strip_bold(win.get("text", "")),
            "highlights":  [],
        })
    return result


def build_languages(languages) -> list:
    result = []
    if isinstance(languages, list):
        for lang in languages:
            if isinstance(lang, dict):
                result.append({
                    "language": lang.get("name", "") or lang.get("language", ""),
                    "fluency":  lang.get("level", "") or lang.get("fluency", ""),
                })
            elif isinstance(lang, str):
                result.append({"language": lang, "fluency": ""})
    elif isinstance(languages, str):
        for lang in languages.split(","):
            result.append({"language": lang.strip(), "fluency": ""})
    return result


def build_interests(interests) -> list:
    result = []
    if isinstance(interests, list):
        for item in interests:
            if isinstance(item, dict):
                result.append({
                    "name":     item.get("name", "") or item.get("category", ""),
                    "keywords": item.get("keywords", []),
                })
            elif isinstance(item, str):
                result.append({"name": item, "keywords": []})
    elif isinstance(interests, str):
        for item in interests.split(","):
            result.append({"name": item.strip(), "keywords": []})
    return result


def build_awards(awards) -> list:
    if not awards:
        return []
    if isinstance(awards, str):
        return [{"title": "Awards & Publications", "awarder": "", "summary": _strip_bold(awards)}]
    if isinstance(awards, list):
        result = []
        for a in awards:
            if isinstance(a, dict):
                result.append({
                    "title":   a.get("title", ""),
                    "awarder": a.get("awarder", "") or a.get("organization", ""),
                    "date":    a.get("date", ""),
                    "summary": _strip_bold(a.get("summary", "") or a.get("description", "")),
                })
            elif isinstance(a, str):
                result.append({"title": _strip_bold(a), "awarder": "", "summary": ""})
        return result
    return []


def convert(data: dict) -> dict:
    """Convert cv.yml data to JSON Resume v1.0.0."""
    personal = data.get("personal", {})

    resume = {
        "$schema": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        "basics":       build_basics(personal, data.get("profile", "")),
        "work":         build_work(data.get("experience", []), data.get("early_career", [])),
        "education":    build_education(data.get("education", [])),
        "skills":       build_skills(data.get("skills", [])),
        "certificates": build_certificates(data.get("certifications", [])),
        "projects":     build_projects(data.get("key_wins", [])),
        "languages":    build_languages(data.get("languages", [])),
        "interests":    build_interests(data.get("interests", [])),
        "awards":       build_awards(data.get("awards")),
        "publications": build_awards(data.get("publications")),
        "meta": {
            "version":   "v1.0.0",
            "canonical": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        },
    }

    # Remove empty optional sections
    for key in ["certificates", "projects", "awards", "publications"]:
        if not resume.get(key):
            resume.pop(key, None)

    return resume


def main():
    parser = argparse.ArgumentParser(description="Export cv.yml to JSON Resume v1.0.0")
    parser.add_argument("-d", "--data",   default="data/cv.yml", help="YAML source file")
    parser.add_argument("-o", "--output", default="cv.json",      help="Output JSON file")
    args = parser.parse_args()

    data_path = REPO_ROOT / args.data
    if not data_path.exists():
        print(f"❌ Data file not found: {data_path}")
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    print(f"📄 Converting {args.data} → JSON Resume...")
    resume = convert(data)

    out_path = REPO_ROOT / args.output
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resume, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"✅ Saved to {out_path}")
    print(f"   🔍 Validate at: https://jsonresume.org/schema/")

    name    = resume["basics"]["name"]
    n_work  = len(resume.get("work", []))
    n_edu   = len(resume.get("education", []))
    n_skill = len(resume.get("skills", []))
    print(f"\n   👤 {name}")
    print(f"   💼 {n_work} work entries")
    print(f"   🎓 {n_edu} education entries")
    print(f"   🔧 {n_skill} skill categories")

    return 0


if __name__ == "__main__":
    sys.exit(main())
