#!/usr/bin/env python3
"""
Advanced ATS Keyword Scoring — Compare job description against your CV.

Features:
  - Section-aware parsing (required vs preferred vs nice-to-have)
  - Weighted scoring (required keywords count more)
  - Skill category grouping
  - Combined CV + Cover Letter analysis
  - JSON output for CI integration

No API key required. Pure local analysis.

Usage:
    scripts/ats-score.py <application-dir>
    scripts/ats-score.py <application-dir> --json
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

from lib.common import STOP_WORDS

# Patterns to detect job description sections
SECTION_PATTERNS = {
    "required": [
        r"(?:required|must[\s-]have|essential|mandatory|minimum)\s*(?:qualifications?|skills?|experience)?",
        r"requirements?\s*[:—\-]",
        r"what you(?:'ll)? need",
        r"what we(?:'re)? looking for",
    ],
    "preferred": [
        r"(?:preferred|nice[\s-]to[\s-]have|bonus|desired|optional|ideal)\s*(?:qualifications?|skills?)?",
        r"(?:plus|advantage|assets?)\s*[:—\-]",
        r"what would be great",
    ],
    "responsibilities": [
        r"responsibilities\s*[:—\-]",
        r"what you(?:'ll)? do",
        r"(?:key )?duties",
        r"(?:the )?role\s*[:—\-]",
    ],
}

# Keyword categories for grouping
CATEGORY_HINTS = {
    "Leadership": {"leadership", "management", "manager", "director", "vp",
                   "executive", "mentor", "hire", "hiring", "coaching",
                   "people", "culture", "talent", "headcount"},
    "Sales & GTM": {"sales", "revenue", "pipeline", "quota", "deal", "enterprise",
                    "meddpicc", "challenger", "selling", "account", "customer",
                    "upsell", "cross-sell", "arr", "arr-growth", "nrr",
                    "land-expand", "gtm", "go-to-market"},
    "Technical": {"engineering", "architecture", "architect", "cloud", "saas",
                  "api", "platform", "data", "security", "cyber", "ai",
                  "machine-learning", "infrastructure", "devops", "software"},
    "Methodology": {"agile", "scrum", "okr", "kpi", "meddpicc",
                    "value-selling", "poc", "pov", "rfp", "rfi"},
    "Domain": {"compliance", "governance", "regulation", "gdpr", "dspm",
               "insider-threat", "identity", "access", "encryption"},
}


def extract_text_from_tex(filepath):
    """Read .tex file and strip LaTeX commands to get plain text."""
    with open(filepath, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"\\[a-zA-Z]+\*?\s*\{", " ", text)
    text = re.sub(r"[{}\\%$~^]", " ", text)
    text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
    return text.lower()


def extract_text_from_file(filepath):
    """Read a file and return lowercase text."""
    with open(filepath, encoding="utf-8") as f:
        return f.read().lower()


def tokenize(text):
    """Extract words (3+ chars, no stop words)."""
    words = re.findall(r"[a-z][a-z0-9-]+", text)
    return [w for w in words if len(w) >= 3 and w not in STOP_WORDS]


def extract_bigrams(tokens):
    """Extract meaningful two-word phrases."""
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]


def detect_sections(text):
    """Split job description into weighted sections."""
    lines = text.split("\n")
    sections = {"required": [], "preferred": [], "responsibilities": [], "general": []}
    current = "general"

    for line in lines:
        line_lower = line.lower().strip()
        if not line_lower:
            continue

        # Check if this line is a section header
        matched = False
        for section, patterns in SECTION_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, line_lower):
                    current = section
                    matched = True
                    break
            if matched:
                break

        if not matched:
            sections[current].append(line)

    return sections


def extract_keywords(text, top_n=50):
    """Extract top keywords and bigrams from text."""
    tokens = tokenize(text)
    unigrams = Counter(tokens)
    bigrams = Counter(extract_bigrams(tokens))

    combined = {}
    for word, count in unigrams.most_common(top_n * 2):
        combined[word] = count
    for bigram, count in bigrams.most_common(top_n):
        if count >= 2:
            combined[bigram] = count * 2

    sorted_kw = sorted(combined.items(), key=lambda x: -x[1])
    return [kw for kw, _ in sorted_kw[:top_n]]


def categorize_keyword(kw):
    """Assign a keyword to a category."""
    kw_words = set(kw.replace("-", " ").split())
    best_cat = "Other"
    best_overlap = 0
    for cat, hints in CATEGORY_HINTS.items():
        overlap = len(kw_words & hints)
        if overlap > best_overlap:
            best_overlap = overlap
            best_cat = cat
    # Also check if the keyword itself is in hints
    if best_overlap == 0:
        for cat, hints in CATEGORY_HINTS.items():
            if kw in hints or kw.replace(" ", "-") in hints:
                return cat
    return best_cat


def main():
    parser = argparse.ArgumentParser(
        prog="ats-score.py",
        description=(
            "Advanced ATS Keyword Scoring — Compare job description against your CV.\n\n"
            "Section-aware parsing with weighted scoring. No API key required."
        ),
    )
    parser.add_argument(
        "app_dir",
        metavar="application-dir",
        help="Path to the application directory (must contain job.txt and a CV .tex file)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Output results as JSON (exits 1 if score < 60)",
    )
    args = parser.parse_args()

    app_dir = args.app_dir
    json_mode = args.json_mode

    if not os.path.isdir(app_dir):
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    # Find job description
    job_text = None
    job_path = os.path.join(app_dir, "job.txt")
    url_path = os.path.join(app_dir, "job.url")

    if os.path.exists(job_path):
        job_text = extract_text_from_file(job_path)
    elif os.path.exists(url_path):
        print("⚠️  job.url found but ATS scoring needs the text content.")
        print(f"   Save the job description as: {app_dir}/job.txt")
        sys.exit(1)
    else:
        print(f"❌ No job description found in {app_dir}/")
        print("   Create job.txt with the pasted job description.")
        sys.exit(1)

    # Find CV and optional Cover Letter
    cv_file = None
    cl_file = None
    for fname in os.listdir(app_dir):
        if fname.startswith("CV ") and fname.endswith(".tex"):
            cv_file = os.path.join(app_dir, fname)
        elif fname.startswith("CoverLetter ") and fname.endswith(".tex"):
            cl_file = os.path.join(app_dir, fname)

    if not cv_file:
        print(f"❌ No CV .tex file found in {app_dir}/")
        sys.exit(1)

    cv_text = extract_text_from_tex(cv_file)
    combined_text = cv_text
    if cl_file:
        combined_text += " " + extract_text_from_tex(cl_file)

    # Detect sections in job description
    sections = detect_sections(job_text)

    # Extract keywords per section with weights
    required_kw = extract_keywords("\n".join(sections["required"]), top_n=25) if sections["required"] else []
    preferred_kw = extract_keywords("\n".join(sections["preferred"]), top_n=15) if sections["preferred"] else []
    general_kw = extract_keywords(job_text, top_n=40)

    # Build weighted keyword list (required=2x, preferred=1x, general=1x)
    weighted = {}
    for kw in required_kw:
        weighted[kw] = weighted.get(kw, 0) + 2.0
    for kw in preferred_kw:
        weighted[kw] = weighted.get(kw, 0) + 1.0
    for kw in general_kw:
        weighted[kw] = weighted.get(kw, 0) + 1.0

    # Deduplicate: keep top keywords by weight
    sorted_kw = sorted(weighted.items(), key=lambda x: -x[1])[:40]

    # Score against combined CV + CL text
    found = []
    missing = []
    found_weight = 0
    total_weight = 0

    for kw, weight in sorted_kw:
        total_weight += weight
        if kw in combined_text:
            found.append((kw, weight))
            found_weight += weight
        else:
            missing.append((kw, weight))

    score = (found_weight / total_weight * 100) if total_weight > 0 else 0

    # Categorize missing keywords
    missing_by_cat = {}
    for kw, weight in missing:
        cat = categorize_keyword(kw)
        missing_by_cat.setdefault(cat, []).append((kw, weight))

    # JSON output
    if json_mode:
        result = {
            "score": round(score, 1),
            "found_count": len(found),
            "missing_count": len(missing),
            "total_keywords": len(sorted_kw),
            "sections_detected": {k: len(v) for k, v in sections.items() if v},
            "found": [{"keyword": kw, "weight": w} for kw, w in found],
            "missing": [{"keyword": kw, "weight": w, "category": categorize_keyword(kw)} for kw, w in missing],
        }
        print(json.dumps(result, indent=2))
        return 0 if score >= 60 else 1

    # Terminal output
    print(f"📊 ATS Keyword Score: {score:.0f}%")
    print(f"   ({len(found)}/{len(sorted_kw)} keywords matched, weighted)")
    if cl_file:
        print(f"   📨 Cover letter included in analysis")

    # Section detection summary
    detected = [k for k, v in sections.items() if v and k != "general"]
    if detected:
        print(f"   📋 Sections detected: {', '.join(detected)}")
    print()

    if score >= 80:
        print("🟢 Excellent match")
    elif score >= 60:
        print("🟡 Good match — consider adding missing keywords")
    elif score >= 40:
        print("🟠 Fair match — several important keywords missing")
    else:
        print("🔴 Low match — significant tailoring needed")

    print()
    print(f"✅ Found ({len(found)}):")
    for kw, weight in found:
        marker = " ⭐" if weight > 1 else ""
        print(f"   • {kw}{marker}")

    print()
    print(f"❌ Missing ({len(missing)}):")
    for cat, kws in sorted(missing_by_cat.items()):
        print(f"   [{cat}]")
        for kw, weight in kws:
            marker = " ⭐ REQUIRED" if weight > 2 else (" ⭐" if weight > 1 else "")
            print(f"     • {kw}{marker}")

    print()
    print("💡 Tips:")
    print("   - ⭐ = higher weight from Required/Qualifications section")
    print("   - Add missing keywords naturally into your CV sections")
    print("   - Focus on REQUIRED keywords first")
    if not cl_file:
        print("   - Add a cover letter to improve keyword coverage")

    return 0 if score >= 60 else 1


if __name__ == "__main__":
    sys.exit(main())
