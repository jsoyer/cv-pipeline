#!/usr/bin/env python3
"""
Cover Letter Scorer — Score cover letter quality against job description.

Scoring breakdown (0–100):
  - Keyword Coverage  (40 pts): job keywords present in cover letter
  - Personalization   (25 pts): company/role/product mentions
  - Structure         (20 pts): opener, value prop, why-company, closing ask
  - Tone Match        (15 pts): formality alignment with job description

No API key required. Pure local analysis.

Usage:
    scripts/cl-score.py <application-dir>
    scripts/cl-score.py <application-dir> --json
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent

from lib.common import REPO_ROOT, require_yaml

yaml = require_yaml()

# ── Import helpers from ats-score.py ─────────────────────────────────────────
_ats_spec = importlib.util.spec_from_file_location(
    "ats_score", _SCRIPT_DIR / "ats-score.py"
)
_ats_mod = importlib.util.module_from_spec(_ats_spec)
_ats_spec.loader.exec_module(_ats_mod)

tokenize = _ats_mod.tokenize
extract_bigrams = _ats_mod.extract_bigrams
detect_sections = _ats_mod.detect_sections
extract_keywords = _ats_mod.extract_keywords
STOP_WORDS = _ats_mod.STOP_WORDS


# ── Syllable / formality helpers ──────────────────────────────────────────────

def count_syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 1
    count = len(re.findall(r"[aeiouy]+", word))
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def formality_score(text: str) -> float:
    words = re.findall(r"[a-zA-Z]+", text)
    if not words:
        return 50.0
    complex_ratio = sum(1 for w in words if count_syllables(w) >= 3) / len(words)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    avg_len = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    norm_len = min(100.0, max(0.0, (avg_len - 10) / 20 * 100))
    return round(complex_ratio * 60 + norm_len * 0.4, 1)


# ── CL text extraction ─────────────────────────────────────────────────────────

def extract_cl_text(cl_data: dict) -> str:
    """Concatenate all prose from coverletter.yml."""
    parts = []
    opening = cl_data.get("opening", "")
    if opening:
        parts.append(str(opening))
    for section in cl_data.get("sections", []):
        body = section.get("body", "")
        if body:
            parts.append(str(body))
    closing = cl_data.get("closing_paragraph", "")
    if closing:
        parts.append(str(closing))
    return "\n".join(parts)


def bar(score: float, width: int = 10) -> str:
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ── Scoring components ────────────────────────────────────────────────────────

def score_keyword_coverage(cl_text: str, job_text: str) -> dict:
    """Score keyword coverage (0–40 pts)."""
    cl_lower = cl_text.lower()
    job_lower = job_text.lower()

    sections = detect_sections(job_lower)
    required_kw = extract_keywords("\n".join(sections["required"]), top_n=20) if sections["required"] else []
    preferred_kw = extract_keywords("\n".join(sections["preferred"]), top_n=10) if sections["preferred"] else []
    general_kw = extract_keywords(job_lower, top_n=30)

    weighted: dict = {}
    for kw in required_kw:
        weighted[kw] = weighted.get(kw, 0) + 2.0
    for kw in preferred_kw:
        weighted[kw] = weighted.get(kw, 0) + 1.0
    for kw in general_kw:
        weighted[kw] = weighted.get(kw, 0) + 1.0

    sorted_kw = sorted(weighted.items(), key=lambda x: -x[1])[:30]

    found = []
    missing = []
    found_weight = 0.0
    total_weight = 0.0

    for kw, weight in sorted_kw:
        total_weight += weight
        if kw in cl_lower:
            found.append({"keyword": kw, "weight": weight})
            found_weight += weight
        else:
            missing.append({"keyword": kw, "weight": weight, "required": weight > 1.5})

    raw_score = (found_weight / total_weight) if total_weight > 0 else 0
    pts = round(raw_score * 40)

    return {
        "pts": pts,
        "max": 40,
        "found": [f["keyword"] for f in found],
        "missing": missing,
    }


def score_personalization(cl_text: str, company_name: str, job_text: str, cl_data: dict) -> dict:
    """Score personalization (0–25 pts)."""
    cl_lower = cl_text.lower()
    pts = 0
    detail = {}

    # Company name mentions (max 12 pts)
    company_pattern = re.compile(re.escape(company_name.lower()), re.IGNORECASE) if company_name else None
    company_count = len(company_pattern.findall(cl_lower)) if company_pattern else 0
    detail["company_mentions"] = company_count
    if company_count == 0:
        company_pts = 0
    elif company_count == 1:
        company_pts = 8
    else:
        company_pts = 12
    pts += company_pts

    # Specific tech/product mentions from job description (max 8 pts)
    job_tokens = tokenize(job_text.lower())
    # Pick nouns / technical terms (longer words more likely to be specific)
    specific_terms = [t for t in set(job_tokens) if len(t) >= 5 and t not in STOP_WORDS][:20]
    tech_found = [t for t in specific_terms if t in cl_lower]
    detail["tech_mentions"] = len(tech_found)
    if len(tech_found) >= 3:
        pts += 8
    elif len(tech_found) >= 1:
        pts += 5

    # Role title mention (max 5 pts)
    # Try to extract position from CL title or recipient context
    title_field = cl_data.get("title", "")
    if "application for" in title_field.lower():
        role_title = re.sub(r"application for\s*", "", title_field, flags=re.IGNORECASE).strip()
    else:
        role_title = ""

    role_found = bool(role_title) and role_title.lower() in cl_lower
    detail["role_title_found"] = role_found
    detail["role_title"] = role_title
    if role_found:
        pts += 5

    return {"pts": min(pts, 25), "max": 25, "detail": detail}


def score_structure(cl_text: str, cl_data: dict) -> dict:
    """Score structural completeness (0–20 pts)."""
    pts = 0
    detail = {}

    # Opening hook: not just "I am writing to apply" (5 pts)
    opening = str(cl_data.get("opening", "")).lower()
    first_section_body = ""
    sections = cl_data.get("sections", [])
    if sections:
        first_section_body = str(sections[0].get("body", "")).lower()
    generic_patterns = [r"i am writing to", r"i would like to apply", r"please find"]
    is_generic = any(re.search(p, opening + first_section_body) for p in generic_patterns)
    has_specific_hook = not is_generic and bool(first_section_body)
    detail["specific_opener"] = has_specific_hook
    if has_specific_hook:
        pts += 5

    # Quantified achievements: numbers / percentages / currency (7 pts)
    metrics_pattern = re.compile(r"\d+%|\$\d+|€\d+|£\d+|\d+x\b|\d+ million|\d+m\b|\d+k\b|\d+ team|\d+ countries", re.IGNORECASE)
    has_metrics = bool(metrics_pattern.search(cl_text))
    detail["has_metrics"] = has_metrics
    if has_metrics:
        pts += 7

    # "Why company" section (5 pts)
    why_titles = {"why", "company", "about", "passion", "fit"}
    has_why_section = False
    for section in sections:
        title = str(section.get("title", "")).lower()
        if any(w in title for w in why_titles):
            body = str(section.get("body", ""))
            if len(body.split()) >= 30:
                has_why_section = True
                break
    detail["why_company_section"] = has_why_section
    if has_why_section:
        pts += 5

    # Closing ask: interview/meeting request (3 pts)
    closing = str(cl_data.get("closing_paragraph", "")).lower()
    ask_patterns = [r"\binterview\b", r"\bdiscuss\b", r"\bconnect\b", r"\bmeet\b", r"\bcall\b", r"\bconversation\b"]
    has_closing_ask = any(re.search(p, closing) for p in ask_patterns)
    detail["closing_ask"] = has_closing_ask
    if has_closing_ask:
        pts += 3

    return {"pts": min(pts, 20), "max": 20, "detail": detail}


def score_tone_match(cl_text: str, job_text: str) -> dict:
    """Score tone alignment with job description (0–15 pts)."""
    cl_formality = formality_score(cl_text)
    job_formality = formality_score(job_text)
    delta = abs(cl_formality - job_formality)

    if delta <= 10:
        pts = 15
    elif delta <= 20:
        pts = 10
    elif delta <= 30:
        pts = 5
    else:
        pts = 0

    return {
        "pts": pts,
        "max": 15,
        "cl_formality": cl_formality,
        "job_formality": job_formality,
        "delta": round(delta, 1),
    }


def main():
    parser = argparse.ArgumentParser(
        prog="cl-score.py",
        description=(
            "Cover Letter Scorer — Score cover letter quality against job description.\n\n"
            "Scoring: Keyword Coverage (40 pts), Personalization (25 pts), "
            "Structure (20 pts), Tone Match (15 pts). No API key required."
        ),
    )
    parser.add_argument(
        "app_dir",
        metavar="application-dir",
        help="Path to the application directory (must contain coverletter.yml and job.txt)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Output results as JSON (exits 1 if score < 60)",
    )
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    json_mode = args.json_mode

    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    # Load cover letter
    cl_path = app_dir / "coverletter.yml"
    if not cl_path.exists():
        print(f"❌ No coverletter.yml found in {app_dir}/")
        print("   Run: make tailor NAME=... to generate one")
        sys.exit(1)

    try:
        with open(cl_path, encoding="utf-8") as f:
            cl_data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"❌ Could not parse coverletter.yml: {e}")
        sys.exit(1)

    # Load job description
    job_path = app_dir / "job.txt"
    if not job_path.exists():
        print(f"❌ No job.txt found in {app_dir}/")
        print("   Run: make fetch NAME=... to download the job description")
        sys.exit(1)

    with open(job_path, encoding="utf-8") as f:
        job_text = f.read()

    # Load meta for company name
    meta_path = app_dir / "meta.yml"
    company_name = ""
    if meta_path.exists():
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
            company_name = meta.get("company", "")
        except Exception:
            pass
    if not company_name:
        # Fallback: try recipient in CL
        company_name = cl_data.get("recipient", {}).get("company", "")

    cl_text = extract_cl_text(cl_data)
    if not cl_text.strip():
        print(f"❌ Cover letter appears empty (no text extracted from coverletter.yml)")
        sys.exit(1)

    # ── Score each component ──────────────────────────────────────────
    kw = score_keyword_coverage(cl_text, job_text)
    pers = score_personalization(cl_text, company_name, job_text, cl_data)
    struct = score_structure(cl_text, cl_data)
    tone = score_tone_match(cl_text, job_text)

    total = kw["pts"] + pers["pts"] + struct["pts"] + tone["pts"]

    # ── Tips ──────────────────────────────────────────────────────────
    tips = []
    if kw["missing"]:
        req_missing = [m["keyword"] for m in kw["missing"] if m.get("required")][:5]
        if req_missing:
            tips.append(f"Add required keywords: {', '.join(req_missing)}")
        elif kw["missing"]:
            tips.append(f"Consider adding: {', '.join(m['keyword'] for m in kw['missing'][:4])}")
    if pers["detail"]["company_mentions"] == 0 and company_name:
        tips.append(f"Mention company name \"{company_name}\" at least once")
    if not pers["detail"]["role_title_found"] and pers["detail"]["role_title"]:
        tips.append(f"Mention the position title: \"{pers['detail']['role_title']}\"")
    if not struct["detail"]["specific_opener"]:
        tips.append("Replace generic opener with a specific hook or achievement")
    if not struct["detail"]["has_metrics"]:
        tips.append("Add quantified achievements (%, €/$, multiples like 2x)")
    if not struct["detail"]["why_company_section"]:
        tips.append("Add a 'Why [Company]?' section (30+ words about their specific products/mission)")
    if not struct["detail"]["closing_ask"]:
        tips.append("End with an explicit call to action (\"I'd love to discuss...\" / \"I look forward to speaking\")")
    if tone["delta"] > 20:
        tips.append(f"Align tone with job description (CL formality {tone['cl_formality']} vs job {tone['job_formality']})")

    # ── JSON output ───────────────────────────────────────────────────
    if json_mode:
        result = {
            "score": total,
            "keyword_coverage": kw["pts"],
            "personalization": pers["pts"],
            "structure": struct["pts"],
            "tone_match": tone["pts"],
            "missing_keywords": kw["missing"],
            "found_keywords": kw["found"],
            "personalization_detail": pers["detail"],
            "structure_detail": struct["detail"],
            "tone_detail": {
                "cl_formality": tone["cl_formality"],
                "job_formality": tone["job_formality"],
                "delta": tone["delta"],
            },
            "tips": tips,
        }
        print(json.dumps(result, indent=2))
        return 0 if total >= 60 else 1

    # ── Terminal output ───────────────────────────────────────────────
    if total >= 80:
        label = "🟢 Excellent"
    elif total >= 60:
        label = "🟡 Good — consider improvements"
    elif total >= 40:
        label = "🟠 Fair — significant improvements needed"
    else:
        label = "🔴 Weak — substantial revision required"

    print(f"📨 Cover Letter Score: {total}/100  {label}")
    print(f"   (Keywords: {kw['pts']}/40 · Personalization: {pers['pts']}/25 · Structure: {struct['pts']}/20 · Tone: {tone['pts']}/15)")
    print()

    # Keyword coverage
    print(f"📋 Keyword Coverage ({kw['pts']}/40)  [{bar(kw['pts'] / 40 * 100)}]")
    if kw["found"]:
        found_str = ", ".join(kw["found"][:10])
        if len(kw["found"]) > 10:
            found_str += f" +{len(kw['found']) - 10} more"
        print(f"   ✅ Found ({len(kw['found'])}): {found_str}")
    if kw["missing"]:
        missing_items = kw["missing"][:8]
        parts = []
        for m in missing_items:
            marker = " ⭐" if m.get("required") else ""
            parts.append(f"{m['keyword']}{marker}")
        print(f"   ❌ Missing ({len(kw['missing'])}): {', '.join(parts)}")
        if any(m.get("required") for m in kw["missing"]):
            print("   ⭐ = required / high-weight keyword")
    print()

    # Personalization
    d = pers["detail"]
    print(f"🎯 Personalization ({pers['pts']}/25)  [{bar(pers['pts'] / 25 * 100)}]")
    co_icon = "✅" if d["company_mentions"] >= 2 else ("⚠️ " if d["company_mentions"] == 1 else "❌")
    print(f"   {co_icon} Company \"{company_name or 'N/A'}\" mentioned {d['company_mentions']} time(s)")
    tech_icon = "✅" if d["tech_mentions"] >= 3 else ("⚠️ " if d["tech_mentions"] >= 1 else "❌")
    print(f"   {tech_icon} Specific tech/terms mentioned: {d['tech_mentions']}")
    role_icon = "✅" if d["role_title_found"] else "⚠️ "
    if d.get("role_title"):
        print(f"   {role_icon} Role title \"{d['role_title'][:40]}\" {'found' if d['role_title_found'] else 'not found'}")
    print()

    # Structure
    sd = struct["detail"]
    print(f"📐 Structure ({struct['pts']}/20)  [{bar(struct['pts'] / 20 * 100)}]")
    print(f"   {'✅' if sd['specific_opener'] else '⚠️ '} Specific opening hook")
    print(f"   {'✅' if sd['has_metrics'] else '⚠️ '} Quantified achievements (numbers/% / €)")
    print(f"   {'✅' if sd['why_company_section'] else '⚠️ '} \"Why [Company]?\" section present")
    print(f"   {'✅' if sd['closing_ask'] else '⚠️ '} Explicit closing ask (interview/discussion)")
    print()

    # Tone
    tone_icon = "✅" if tone["delta"] <= 15 else ("⚠️ " if tone["delta"] <= 25 else "❌")
    print(f"🎵 Tone Match ({tone['pts']}/15)  [{bar(tone['pts'] / 15 * 100)}]")
    print(f"   {tone_icon} CL formality: {tone['cl_formality']} · Job formality: {tone['job_formality']} · Δ={tone['delta']}")
    print()

    if tips:
        print("💡 Tips:")
        for tip in tips[:6]:
            print(f"   • {tip}")
        print()

    app_name = app_dir.name
    print(f"   👉 Next: make review NAME={app_name}")

    return 0 if total >= 60 else 1


if __name__ == "__main__":
    sys.exit(main())
