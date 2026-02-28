#!/usr/bin/env python3
"""
CV keyword gap analysis — no AI required.

Aggregates all keywords found across applications/*/job.txt files,
then checks which high-frequency market keywords are absent from your
master CV (data/cv.yml) or tailored CVs.

Outputs a ranked gap table and a list of CV keywords that rarely appear
in job postings (potentially outdated or over-specific).

Output: data/cv-keywords.md + terminal table

Usage:
    scripts/cv-keywords.py [--min-count N] [--cv NAME] [--json]

    --min-count N   Only show keywords present in ≥ N job postings (default: 2)
    --cv NAME       Use applications/NAME/cv-tailored.yml instead of data/cv.yml
    --json          Print JSON instead of table
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT   = _SCRIPT_DIR.parent

# Common English + French stopwords to filter
STOPWORDS = frozenset({
    # articles / determiners
    "the", "a", "an", "this", "that", "these", "those", "its",
    "le", "la", "les", "un", "une", "des", "du", "au", "aux",
    # prepositions
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "as", "into", "through", "across", "about", "above", "within",
    "between", "among", "during", "including", "until", "against",
    "throughout", "despite", "towards", "upon", "concerning",
    # conjunctions
    "and", "or", "but", "if", "than", "then", "so", "yet",
    "both", "either", "neither", "not", "nor",
    "que", "qui", "dont", "où", "mais", "ou", "donc", "car",
    # pronouns
    "you", "we", "they", "our", "your", "their", "its", "all",
    "each", "every", "both", "few", "more", "most", "other",
    "such", "same", "own", "just", "now", "here", "how", "what",
    # common verbs
    "be", "is", "are", "was", "were", "been", "being",
    "have", "has", "had", "do", "does", "did",
    "will", "would", "can", "could", "should", "may", "might",
    "shall", "must", "need", "get", "make", "take", "use",
    "work", "help", "provide", "ensure", "support", "manage",
    "include", "require", "drive", "build", "create", "develop",
    "define", "lead", "own", "run", "set", "serve", "partner",
    # common adjectives / adverbs
    "new", "key", "strong", "high", "large", "small", "great",
    "good", "best", "top", "first", "main", "full", "real",
    "able", "well", "also", "often", "highly", "deeply",
    # common nouns too generic to be useful
    "role", "team", "company", "business", "position", "job",
    "year", "time", "way", "day", "part", "level", "type",
    "areas", "area", "impact", "approach", "experience",
    "ability", "skills", "knowledge", "understanding", "mindset",
    "environment", "culture", "world", "people", "person",
    "candidate", "opportunity", "responsibilities", "requirements",
    "plus", "based", "across", "who", "they", "their",
    # misc
    "etc", "e.g", "i.e", "via", "per", "non",
})

MIN_WORD_LEN = 3


def tokenize(text: str) -> list[str]:
    """Extract meaningful lowercase tokens from text."""
    raw = re.findall(r'[a-zA-Z][a-zA-Z0-9+#.-]*', text.lower())
    return [
        t.rstrip(".-")
        for t in raw
        if len(t) >= MIN_WORD_LEN and t not in STOPWORDS
    ]


def cv_text(cv_data: dict) -> str:
    """Flatten cv.yml to a single text blob for keyword matching."""
    parts = []

    # Profile
    profile = cv_data.get("profile", "")
    if isinstance(profile, str):
        parts.append(profile)

    # Skills
    for skill_group in cv_data.get("skills", []):
        if isinstance(skill_group, dict):
            parts.append(skill_group.get("category", ""))
            items = skill_group.get("items", "")
            if isinstance(items, str):
                parts.append(items)
            elif isinstance(items, list):
                parts.extend(str(i) for i in items)

    # Experience
    for exp in cv_data.get("experience", []) + cv_data.get("early_career", []):
        if isinstance(exp, dict):
            parts.append(exp.get("position", ""))
            parts.append(exp.get("company", ""))
            for item in exp.get("items", []):
                if isinstance(item, dict):
                    parts.append(item.get("label", ""))
                    parts.append(item.get("text", ""))
                else:
                    parts.append(str(item))

    # Key wins
    for win in cv_data.get("key_wins", []):
        if isinstance(win, dict):
            parts.append(win.get("title", ""))
            parts.append(win.get("text", ""))

    # Certifications, languages, interests
    for cert in cv_data.get("certifications", []):
        if isinstance(cert, dict):
            parts.append(cert.get("name", ""))
    for lang in cv_data.get("languages", []):
        if isinstance(lang, dict):
            parts.append(lang.get("language", ""))
    for interest in cv_data.get("interests", []):
        parts.append(str(interest))

    return " ".join(str(p) for p in parts)


def suggest_section(word: str, cv_data: dict) -> str:
    """Suggest which CV section is best to insert a missing keyword."""
    skills_text = " ".join(
        str(sg.get("items", "")) for sg in cv_data.get("skills", [])
        if isinstance(sg, dict)
    ).lower()
    profile_text = str(cv_data.get("profile", "")).lower()

    # Heuristics
    tech_indicators = {"api", "cloud", "saas", "sql", "python", "aws", "azure",
                       "security", "siem", "soar", "xdr", "dlp", "dspm", "sase",
                       "zero", "trust", "kubernetes", "docker", "terraform"}
    business_indicators = {"arr", "mrr", "acv", "quota", "pipeline", "forecast",
                           "meddic", "meddpicc", "spin", "challenger", "crm",
                           "salesforce", "revenue", "enterprise", "saas"}

    if word in tech_indicators or any(w in word for w in ["tech", "soft", "tool", "platform"]):
        return "Skills"
    if word in business_indicators:
        return "Profile or Experience"
    return "Profile or Experience"


def analyze(apps_dir: Path, cv_data: dict, min_count: int) -> dict:
    """
    Returns:
      missing: list of {word, job_count, total_jobs, pct, section}
      surplus: list of {word, job_count, total_jobs}
      total_jobs: int
      cv_word_count: int
    """
    job_files = sorted(apps_dir.glob("*/job.txt"))
    total_jobs = len(job_files)

    if total_jobs == 0:
        return {"missing": [], "surplus": [], "total_jobs": 0, "cv_word_count": 0}

    # Count how many job files contain each word (not total occurrences)
    job_word_files: Counter = Counter()
    for jf in job_files:
        words = set(tokenize(jf.read_text(encoding="utf-8", errors="ignore")))
        job_word_files.update(words)

    # CV words
    flat_cv = cv_text(cv_data)
    cv_words = set(tokenize(flat_cv))

    # Missing: high-freq market words absent from CV
    missing = []
    for word, count in job_word_files.most_common():
        if count < min_count:
            break
        if word not in cv_words:
            missing.append({
                "word": word,
                "job_count": count,
                "total_jobs": total_jobs,
                "pct": round(100 * count / total_jobs),
                "section": suggest_section(word, cv_data),
            })

    # Surplus: CV words rarely (or never) in job postings
    surplus = []
    for word in sorted(cv_words):
        count = job_word_files.get(word, 0)
        if count == 0 and len(word) > 4:
            surplus.append({
                "word": word,
                "job_count": count,
                "total_jobs": total_jobs,
            })

    return {
        "missing": missing[:40],   # cap at 40 for readability
        "surplus": surplus[:20],
        "total_jobs": total_jobs,
        "cv_word_count": len(cv_words),
    }


def main():
    parser = argparse.ArgumentParser(description="CV keyword gap analysis")
    parser.add_argument("--min-count", type=int, default=2,
                        help="Min job postings a keyword must appear in (default: 2)")
    parser.add_argument("--cv", default="",
                        help="Use cv-tailored.yml from this application name")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of formatted table")
    args = parser.parse_args()

    apps_dir = _REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ applications/ directory not found")
        sys.exit(1)

    # Load CV
    if args.cv:
        cv_src = apps_dir / args.cv / "cv-tailored.yml"
        if not cv_src.exists():
            cv_src = _REPO_ROOT / "data" / "cv.yml"
    else:
        cv_src = _REPO_ROOT / "data" / "cv.yml"

    if not cv_src.exists():
        print(f"❌ CV not found: {cv_src}")
        sys.exit(1)

    with open(cv_src, encoding="utf-8") as f:
        cv_data = yaml.safe_load(f) or {}

    result = analyze(apps_dir, cv_data, args.min_count)
    total = result["total_jobs"]
    missing = result["missing"]
    surplus = result["surplus"]

    if total == 0:
        print("📋 No job.txt files found in applications/")
        sys.exit(0)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    # Terminal output
    cv_label = f"applications/{args.cv}/cv-tailored.yml" if args.cv else "data/cv.yml"
    print(f"\n📊 CV Keyword Gap Analysis")
    print(f"   {total} job postings · {result['cv_word_count']} unique CV words · min threshold: {args.min_count} jobs")
    print(f"   CV source: {cv_label}\n")

    if missing:
        print(f"{'─'*68}")
        print(f"  Keywords MISSING from your CV (present in ≥{args.min_count} job postings)")
        print(f"{'─'*68}")
        print(f"  {'Jobs':>6}  {'%':>4}  {'Keyword':<28}  Suggested section")
        print(f"{'─'*68}")
        for row in missing[:25]:
            bar = "█" * (row["pct"] // 10)
            print(f"  {row['job_count']:>4}/{total}  {row['pct']:>3}%  {row['word']:<28}  {row['section']}")
        if len(missing) > 25:
            print(f"  ... and {len(missing) - 25} more (see cv-keywords.md)")
        print()

    if surplus:
        print(f"{'─'*68}")
        print(f"  CV keywords NOT FOUND in any job posting (possibly outdated)")
        print(f"{'─'*68}")
        words_str = ", ".join(row["word"] for row in surplus[:15])
        print(f"  {words_str}")
        print()

    if not missing:
        print("✅ No significant keyword gaps found.")

    # Coverage stat
    all_market = sum(1 for _ in (apps_dir / "applications").glob("*/job.txt") if True)
    job_files = sorted(apps_dir.glob("*/job.txt"))
    all_words_in_market = set()
    for jf in job_files:
        words = set(tokenize(jf.read_text(encoding="utf-8", errors="ignore")))
        all_words_in_market.update(words)
    cv_words_set = set(tokenize(cv_text(cv_data)))
    covered = len(cv_words_set & all_words_in_market)
    total_market = len(all_words_in_market)
    if total_market:
        pct = round(100 * covered / total_market)
        print(f"  CV market coverage: {covered}/{total_market} market keywords ({pct}%)")
        print()

    # Save markdown
    from datetime import date
    today = date.today().isoformat()
    lines = [
        "# CV Keyword Gap Analysis",
        f"*{total} job postings · {today} · source: {cv_label}*",
        "",
    ]
    if missing:
        lines += [
            f"## Missing Keywords (present in ≥{args.min_count} job postings)",
            "",
            f"| Jobs | % | Keyword | Suggested section |",
            f"|------|---|---------|-------------------|",
        ]
        for row in missing:
            lines.append(f"| {row['job_count']}/{total} | {row['pct']}% | `{row['word']}` | {row['section']} |")
        lines.append("")
    if surplus:
        lines += [
            "## CV Keywords Not Found in Job Postings",
            "",
            "Consider replacing or removing these from your master CV:",
            "",
        ]
        for row in surplus:
            lines.append(f"- `{row['word']}`")
        lines.append("")

    out = _REPO_ROOT / "data" / "cv-keywords.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
