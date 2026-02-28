#!/usr/bin/env python3
"""
Skills Gap Analysis — Cross-job-posting keyword analysis.

Analyzes all job.txt files to find the most demanded skills,
then compares against your CV to identify gaps and trends.

Usage:
    scripts/skills-gap.py                # terminal output
    scripts/skills-gap.py --json         # JSON output
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

STOP_WORDS = frozenset({
    "a", "ab", "able", "about", "above", "across", "after", "again", "all",
    "also", "am", "an", "and", "any", "are", "as", "at", "back", "be",
    "because", "been", "before", "being", "between", "both", "but", "by",
    "can", "come", "could", "day", "de", "did", "do", "does", "each",
    "even", "every", "few", "first", "for", "from", "further", "get",
    "great", "had", "has", "have", "he", "help", "her", "here", "high",
    "him", "his", "how", "i", "if", "in", "including", "into", "is", "it",
    "its", "just", "know", "la", "last", "le", "les", "like", "long",
    "look", "make", "many", "may", "me", "might", "more", "most", "much",
    "must", "my", "need", "new", "no", "nor", "not", "now", "of", "on",
    "one", "only", "or", "other", "our", "out", "over", "own", "part",
    "plus", "re", "role", "same", "she", "should", "so", "some", "such",
    "take", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "through", "time", "to", "too",
    "two", "under", "up", "upon", "us", "use", "used", "using", "very",
    "want", "was", "way", "we", "well", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "work",
    "working", "would", "year", "years", "you", "your",
    "ability", "apply", "bonus", "candidate", "company", "description",
    "equal", "employer", "experience", "job", "looking", "opportunity",
    "position", "preferred", "qualifications", "required", "requirements",
    "responsibilities", "team", "strong", "excellent", "proven", "deep",
})


def tokenize(text):
    """Extract words (3+ chars, no stop words)."""
    words = re.findall(r"[a-z][a-z0-9-]+", text.lower())
    return [w for w in words if len(w) >= 3 and w not in STOP_WORDS]


def extract_bigrams(tokens):
    """Extract two-word phrases."""
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]


def extract_cv_text(cv_path):
    """Read CV.tex and strip LaTeX commands."""
    with open(cv_path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"\\[a-zA-Z]+\*?\s*\{", " ", text)
    text = re.sub(r"[{}\\%$~^]", " ", text)
    text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
    return text.lower()


def main():
    json_mode = "--json" in sys.argv

    apps_dir = Path("applications")
    if not apps_dir.exists():
        print("No applications/ directory found.")
        return 1

    # Collect all job.txt files
    job_files = sorted(apps_dir.glob("*/job.txt"))
    if not job_files:
        print("No job.txt files found in applications/.")
        print("   Run: make fetch NAME=... to fetch job descriptions first.")
        return 0

    # Extract keywords from each job posting
    all_keywords = Counter()       # keyword → total count across postings
    keyword_presence = Counter()   # keyword → number of postings containing it
    per_posting = {}               # app_name → set of keywords

    for job_file in job_files:
        app_name = job_file.parent.name
        with open(job_file, encoding="utf-8") as f:
            text = f.read().lower()

        tokens = tokenize(text)
        unigrams = Counter(tokens)
        bigrams = Counter(extract_bigrams(tokens))

        # Build keyword set for this posting
        kw_set = set()
        for word, count in unigrams.most_common(60):
            kw_set.add(word)
            all_keywords[word] += count
        for bigram, count in bigrams.most_common(30):
            if count >= 2:
                kw_set.add(bigram)
                all_keywords[bigram] += count * 2

        for kw in kw_set:
            keyword_presence[kw] += 1

        per_posting[app_name] = kw_set

    n_postings = len(job_files)

    # Read master CV
    cv_path = Path("CV.tex")
    cv_text = extract_cv_text(cv_path) if cv_path.exists() else ""

    # Find trending keywords (appear in 2+ postings)
    trending = [(kw, count) for kw, count in keyword_presence.most_common()
                if count >= 2 or (count == 1 and n_postings == 1)]

    # Split into covered vs gap
    covered = [(kw, count) for kw, count in trending if kw in cv_text]
    gaps = [(kw, count) for kw, count in trending if kw not in cv_text]

    if json_mode:
        result = {
            "postings_analyzed": n_postings,
            "total_trending": len(trending),
            "covered": [{"keyword": kw, "postings": c} for kw, c in covered],
            "gaps": [{"keyword": kw, "postings": c} for kw, c in gaps],
        }
        print(json.dumps(result, indent=2))
        return 0

    # Terminal output
    print(f"📊 Skills Gap Analysis")
    print(f"   {n_postings} job posting(s) analyzed")
    print()

    if gaps:
        print(f"❌ Skills NOT in your CV ({len(gaps)}):")
        print(f"   {'KEYWORD':<30} {'POSTINGS':>8}")
        print(f"   {'─' * 30} {'─' * 8}")
        for kw, count in gaps[:25]:
            bar = "█" * count + "░" * (n_postings - count)
            pct = f"{count}/{n_postings}"
            print(f"   {kw:<30} {pct:>8}  {bar}")
        print()

    if covered:
        print(f"✅ Skills IN your CV ({len(covered)}):")
        print(f"   {'KEYWORD':<30} {'POSTINGS':>8}")
        print(f"   {'─' * 30} {'─' * 8}")
        for kw, count in covered[:20]:
            pct = f"{count}/{n_postings}"
            print(f"   {kw:<30} {pct:>8}")
        print()

    # Top gaps summary
    if gaps:
        top_gaps = [kw for kw, _ in gaps[:5]]
        print(f"💡 Top skills to add: {', '.join(top_gaps)}")
        print()
        print("   Consider adding these keywords to your CV naturally.")
        print("   Use: make tailor NAME=... to have Gemini integrate them.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
