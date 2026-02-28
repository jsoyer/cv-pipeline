#!/usr/bin/env python3
"""Reverse ATS - Score master CV against a job description without creating an application."""

import os
import sys
import json
import argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)

WORKDIR = Path(os.environ.get("WORKDIR", Path(__file__).resolve().parent.parent))

JOB_KEYWORDS = {
    "leadership": [
        "leadership",
        "management",
        "team lead",
        "director",
        "vp",
        "chief",
        "manage team",
        "manage people",
        "managers of managers",
    ],
    "sales": [
        "sales",
        "revenue",
        "arr",
        "quota",
        "book",
        "commercial",
        "deal",
        "pipeline",
        "forecast",
    ],
    "engineering": [
        "sales engineering",
        "solution architect",
        "pre-sales",
        "technical sales",
        "se",
        "sa",
        "architect",
    ],
    "strategy": [
        "strategy",
        "strategic",
        "planning",
        "roadmap",
        "transformation",
        "optimization",
    ],
    "growth": ["growth", "scale", "expand", "accelerate", "hypergrowth", "startup"],
    "enterprise": [
        "enterprise",
        "large account",
        "strategic account",
        "fortune",
        "corporate",
    ],
    "technical": [
        "technical",
        "technology",
        "product",
        "cloud",
        "saas",
        "infrastructure",
        "security",
        "data",
        "ai",
        "ml",
    ],
    "negotiation": [
        "negotiation",
        "contract",
        "pricing",
        "deal structure",
        "meddpicc",
        "value selling",
    ],
    "team": ["team", "hire", "recruit", "build team", "org design", "restructure"],
    "executive": ["c-level", "ceo", "cto", "cfo", "cro", "vp sales", "evp", "svp"],
}

SKILL_KEYWORDS = {
    "leadership": [
        "managers of managers",
        "m&a",
        "change management",
        "talent acquisition",
        "high-performance culture",
    ],
    "sales_metrics": [
        "arr growth",
        "quota attainment",
        "pipeline generation",
        "win rate",
        "nrr",
        "tam",
    ],
    "methodologies": [
        "meddpicc",
        "value-based selling",
        "land and expand",
        "consumption-based",
    ],
    "domains": [
        "saas",
        "cloud",
        "cybersecurity",
        "data governance",
        "ai/trism",
        "dspm",
        "dam",
    ],
    "tools": [
        "salesforce",
        "hubspot",
        "linkedin",
        "zoominfo",
        "gong",
        "salesloft",
        "outreach",
    ],
}


def load_cv_skills(cv_path):
    """Extract skills from CV YAML."""
    with open(cv_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    skills = []
    if "skills" in data:
        for cat in data["skills"]:
            if "items" in cat:
                for item in cat["items"].split(","):
                    skills.append(item.strip().lower())
    return skills


def extract_keywords_from_text(text):
    """Extract keywords from job description text."""
    text = text.lower()
    found = {}

    all_keywords = {**JOB_KEYWORDS, **SKILL_KEYWORDS}
    for category, keywords in all_keywords.items():
        count = sum(1 for kw in keywords if kw.lower() in text)
        if count > 0:
            found[category] = count

    return found


def score_match(job_keywords, cv_skills):
    """Calculate match score between job and CV."""
    score = 0
    max_score = 0
    matched = []
    missing = []

    for skill in cv_skills:
        max_score += 2
        if any(
            skill.lower() in kw.lower() or kw.lower() in skill.lower()
            for kw in job_keywords.keys()
        ):
            score += 2
            matched.append(skill)
        else:
            if any(
                skill.lower() in cat or cat in skill.lower()
                for cat in job_keywords.keys()
            ):
                score += 1
                matched.append(skill + " (partial)")
            else:
                missing.append(skill)

    # Bonuses only fire when the job description strongly emphasizes these areas
    # (2+ keyword matches in the category, not just any single mention)
    if job_keywords.get("leadership", 0) >= 2 or job_keywords.get("executive", 0) >= 2:
        score += 5
        max_score += 5

    if job_keywords.get("sales", 0) >= 2:
        score += 5
        max_score += 5

    if job_keywords.get("technical", 0) >= 2 or job_keywords.get("engineering", 0) >= 2:
        score += 3
        max_score += 3

    final_score = (score / max_score * 100) if max_score > 0 else 0

    return {
        "score": final_score,
        "matched": matched[:10],
        "missing": missing[:10],
        "job_keywords": dict(sorted(job_keywords.items(), key=lambda x: -x[1])[:10]),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Score master CV against job description"
    )
    parser.add_argument("source", help="Job description text, URL, or file path")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    source = args.source

    if source.startswith(("http://", "https://")):
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            print("❌ requests and beautifulsoup4 required for URL fetching")
            print("   pip install requests beautifulsoup4")
            sys.exit(1)

        print(f"🌐 Fetching job description from {source}...")
        try:
            response = requests.get(source, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text()
            for tag in [
                "article",
                "div[role='main']",
                "main",
                ".job-description",
                "#job-description",
            ]:
                try:
                    main = soup.select_one(tag)
                    if main:
                        text = main.get_text()
                        break
                except:
                    pass
            job_text = text[:5000]
        except Exception as e:
            print(f"❌ Failed to fetch URL: {e}")
            sys.exit(1)

    elif Path(source).exists():
        with open(source, encoding="utf-8") as f:
            job_text = f.read()
    else:
        job_text = source

    cv_path = WORKDIR / "data" / "cv.yml"
    if not cv_path.exists():
        print("❌ CV data not found: data/cv.yml")
        sys.exit(1)

    cv_skills = load_cv_skills(cv_path)
    job_keywords = extract_keywords_from_text(job_text)
    result = score_match(job_keywords, cv_skills)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("📊 CV Match Score")
        print("=" * 50)
        print(f"\n🎯 Overall Match: {result['score']:.0f}%")
        print()

        if result["job_keywords"]:
            print("📋 Job Keywords Found:")
            for kw, count in result["job_keywords"].items():
                print(f"   • {kw}: {count}")
            print()

        if result["matched"]:
            print("✅ Matching Skills:")
            for skill in result["matched"]:
                print(f"   ✓ {skill}")
            print()

        if result["missing"]:
            print("❌ Skills Not Found:")
            for skill in result["missing"]:
                print(f"   ✗ {skill}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
