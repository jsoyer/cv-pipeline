#!/usr/bin/env python3
"""
Tone Consistency Checker — Analyze CV and Cover Letter for tone coherence.

Checks:
  - Formality score per section (vocabulary complexity, sentence length)
  - Action verb strength in bullet points
  - Passive voice rate
  - Filler word usage
  - CV vs Cover Letter tone consistency

No API key required. Pure local analysis.

Usage:
    scripts/tone-check.py <application-dir>
    scripts/tone-check.py <application-dir> --json
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT

# Strong past-tense action verbs
STRONG_ACTION_VERBS = {
    "accelerated", "achieved", "aligned", "architected", "automated",
    "awarded", "built", "championed", "closed", "coached", "consolidated",
    "coordinated", "created", "cut", "defined", "delivered", "deployed",
    "designed", "developed", "directed", "drove", "established", "exceeded",
    "executed", "expanded", "generated", "grew", "guided", "hired",
    "implemented", "improved", "increased", "initiated", "integrated",
    "introduced", "launched", "led", "managed", "mentored", "migrated",
    "negotiated", "onboarded", "optimized", "orchestrated", "oversaw",
    "partnered", "piloted", "pioneered", "pitched", "presented", "produced",
    "proposed", "raised", "recruited", "reduced", "redesigned", "reengineered",
    "restructured", "rolled", "saved", "scaled", "secured", "shaped",
    "spearheaded", "standardized", "streamlined", "trained", "transformed",
    "won",
}

# Weak starters that signal passive or vague writing
WEAK_STARTERS = {
    "assisted", "contributed", "helped", "involved", "participated",
    "responsible", "supported", "worked",
}

# Filler / buzzwords to flag
FILLER_WORDS = [
    "leveraged", "leveraging", "leverage",
    "passionate", "passionately",
    "dynamic",
    "synergy", "synergize", "synergistic",
    "utilize", "utilized", "utilizing", "utilization",
    "proactive", "proactively",
    "innovative", "innovatively",
    "hardworking", "driven",
    "results-driven", "result-driven",
    "team player",
    "fast-paced",
    "go-getter",
    "thought leader", "thought leadership",
    "ninja", "rockstar", "guru",
]


def count_syllables(word: str) -> int:
    """Heuristic syllable count based on vowel clusters."""
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 1
    count = len(re.findall(r"[aeiouy]+", word))
    # Silent trailing 'e' (rough heuristic)
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def formality_score(text: str) -> float:
    """
    Return a formality score 0–100.
    Higher = more formal/complex vocabulary and longer sentences.
    """
    words = re.findall(r"[a-zA-Z]+", text)
    if not words:
        return 50.0

    # Complexity ratio: words with >= 3 syllables
    complex_count = sum(1 for w in words if count_syllables(w) >= 3)
    complexity_ratio = complex_count / len(words)

    # Average sentence length (normalized: 10 words → 0, 30 words → 100)
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if sentences:
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
    else:
        avg_len = 15
    norm_len = min(100.0, max(0.0, (avg_len - 10) / 20 * 100))

    return round(complexity_ratio * 60 + norm_len * 0.4, 1)


def bar(score: float, width: int = 10) -> str:
    """ASCII progress bar for score 0–100."""
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def check_action_verbs(bullets: list) -> dict:
    """Analyze bullet points for strong action verb coverage."""
    results = []
    for bullet in bullets:
        clean = re.sub(r"\*\*(.+?)\*\*", r"\1", bullet).strip()
        words = clean.split()
        if not words:
            continue
        first_word = re.sub(r"[^a-zA-Z]", "", words[0]).lower()
        is_strong = first_word in STRONG_ACTION_VERBS
        is_weak = first_word in WEAK_STARTERS
        results.append({
            "bullet": clean[:70] + ("…" if len(clean) > 70 else ""),
            "first_word": first_word,
            "is_strong": is_strong,
            "is_weak": is_weak,
        })
    strong_count = sum(1 for r in results if r["is_strong"])
    weak_bullets = [r["bullet"] for r in results if r["is_weak"]]
    unclear_bullets = [r["bullet"] for r in results
                       if not r["is_strong"] and not r["is_weak"] and r["first_word"]]
    return {
        "strong": strong_count,
        "total": len(results),
        "weak_bullets": weak_bullets,
        "unclear_bullets": unclear_bullets,
    }


def check_passive_voice(text: str) -> dict:
    """Detect passive voice constructions."""
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    passive_pattern = re.compile(
        r"\b(was|were|is|are|am|been|has been|have been|had been)\s+\w+(?:ed|en)\b",
        re.IGNORECASE,
    )
    passive_sentences = [s for s in sentences if passive_pattern.search(s)]
    rate = (len(passive_sentences) / len(sentences) * 100) if sentences else 0
    examples = [s[:80] + ("…" if len(s) > 80 else "") for s in passive_sentences[:3]]
    return {
        "count": len(passive_sentences),
        "total_sentences": len(sentences),
        "rate_pct": round(rate, 1),
        "examples": examples,
    }


def check_filler_words(text: str) -> dict:
    """Find corporate filler/buzzwords in the text."""
    text_lower = text.lower()
    found = {}
    for filler in FILLER_WORDS:
        pattern = re.compile(r"\b" + re.escape(filler) + r"\b", re.IGNORECASE)
        matches = pattern.findall(text_lower)
        if matches:
            found[filler] = len(matches)
    total_count = sum(found.values())
    return {"found": found, "total_count": total_count}


def extract_cv_sections(cv_data: dict) -> dict:
    """Extract text blocks from cv.yml / cv-tailored.yml."""
    sections = {}

    # Profile
    if "profile" in cv_data:
        sections["profile"] = str(cv_data["profile"])

    # Key wins
    key_wins = cv_data.get("key_wins", [])
    if key_wins:
        sections["key_wins"] = "\n".join(str(k) for k in key_wins)

    # Experience bullets (all roles) — items can be str or {label, text} dict
    exp_bullets = []
    for exp in cv_data.get("experience", []):
        for item in exp.get("items", []):
            if isinstance(item, dict):
                exp_bullets.append(str(item.get("text", item.get("label", ""))))
            else:
                exp_bullets.append(str(item))
    if exp_bullets:
        sections["experience"] = "\n".join(exp_bullets)

    return sections


def extract_cl_text(cl_data: dict) -> str:
    """Extract all text from coverletter.yml."""
    parts = []
    if "opening" in cl_data:
        parts.append(str(cl_data["opening"]))
    for section in cl_data.get("sections", []):
        body = section.get("body", "")
        if body:
            parts.append(str(body))
    if "closing_paragraph" in cl_data:
        parts.append(str(cl_data["closing_paragraph"]))
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Tone Consistency Checker — Analyze CV and Cover Letter for tone coherence. "
                    "No API key required. Pure local analysis."
    )
    parser.add_argument(
        "app_dir",
        metavar="application-dir",
        help="Path to the application directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    json_mode = args.json_mode

    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    # Load CV YAML
    cv_path = app_dir / "cv-tailored.yml"
    if not cv_path.exists():
        cv_path = REPO_ROOT / "data" / "cv.yml"
    if not cv_path.exists():
        print(f"❌ No cv-tailored.yml or data/cv.yml found")
        sys.exit(1)

    try:
        with open(cv_path, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"❌ Could not parse CV YAML: {e}")
        sys.exit(1)

    # Load CL YAML (optional)
    cl_data = None
    cl_path = app_dir / "coverletter.yml"
    if cl_path.exists():
        try:
            with open(cl_path, encoding="utf-8") as f:
                cl_data = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Extract sections
    cv_sections = extract_cv_sections(cv_data)
    cl_text = extract_cl_text(cl_data) if cl_data else None

    # ── Section formality scores ──────────────────────────────────────
    section_scores = {}
    for name, text in cv_sections.items():
        section_scores[name] = formality_score(text)

    cv_overall = round(sum(section_scores.values()) / len(section_scores), 1) if section_scores else 50.0

    # Consistency: std dev across sections
    if len(section_scores) > 1:
        mean = sum(section_scores.values()) / len(section_scores)
        variance = sum((s - mean) ** 2 for s in section_scores.values()) / len(section_scores)
        std_dev = round(math.sqrt(variance), 1)
    else:
        std_dev = 0.0
    is_consistent = std_dev <= 15

    # CL formality
    cl_formality = formality_score(cl_text) if cl_text else None
    tone_match = None
    tone_delta = None
    if cl_formality is not None:
        tone_delta = abs(cv_overall - cl_formality)
        tone_match = tone_delta <= 15

    # ── Action verbs (experience bullets) ────────────────────────────
    all_bullets = []
    for exp in cv_data.get("experience", []):
        for item in exp.get("items", []):
            if isinstance(item, dict):
                all_bullets.append(str(item.get("text", item.get("label", ""))))
            else:
                all_bullets.append(str(item))
    all_bullets.extend(str(k) for k in cv_data.get("key_wins", []))
    verb_analysis = check_action_verbs(all_bullets)

    # ── Passive voice ─────────────────────────────────────────────────
    all_cv_text = " ".join(cv_sections.values())
    passive = check_passive_voice(all_cv_text)

    # ── Filler words ──────────────────────────────────────────────────
    check_text = all_cv_text + (" " + cl_text if cl_text else "")
    filler = check_filler_words(check_text)

    # ── Overall score ─────────────────────────────────────────────────
    overall_score = 100
    overall_score -= min(20, len(filler["found"]) * 5)
    if passive["rate_pct"] > 15:
        overall_score -= 15
    verb_rate = (verb_analysis["strong"] / max(1, verb_analysis["total"])) * 100
    if verb_rate < 70:
        overall_score -= 10
    if tone_match is False:
        overall_score -= 15
    if not is_consistent:
        overall_score -= 10
    overall_score = max(0, overall_score)

    # ── Warnings + tips ───────────────────────────────────────────────
    warnings = []
    tips = []

    if filler["found"]:
        words = list(filler["found"].keys())
        warnings.append(f"Filler words found: {', '.join(words)}")
        for w in list(filler["found"].keys())[:3]:
            replacements = {
                "leveraged": "used / applied",
                "utilize": "use",
                "passionate": "committed / focused",
                "dynamic": "(remove — too vague)",
                "synergy": "(remove — buzzword)",
                "proactive": "(remove — show, don't tell)",
            }
            tip = replacements.get(w, f"remove or replace '{w}'")
            tips.append(f"Replace \"{w}\" → {tip}")

    if passive["rate_pct"] > 15:
        warnings.append(f"High passive voice rate: {passive['rate_pct']:.0f}%")
        tips.append("Rewrite passive constructions in active voice (start with the subject who acted)")

    if verb_rate < 70 and verb_analysis["total"] > 0:
        warnings.append(f"Only {verb_analysis['strong']}/{verb_analysis['total']} bullets start with strong action verbs")
        if verb_analysis["weak_bullets"]:
            tips.append(f"Replace weak starter in: \"{verb_analysis['weak_bullets'][0][:60]}…\"")

    if not is_consistent:
        warnings.append(f"Tone inconsistency across sections (σ={std_dev})")
        tips.append("Review Profile section — formality varies significantly from Experience")

    if tone_match is False:
        warnings.append(f"CV/Cover Letter tone mismatch (Δ={tone_delta:.0f})")
        tips.append("Align cover letter formality with CV tone")

    avg_sentence_len = {}
    for name, text in cv_sections.items():
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        if sentences:
            avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
            avg_sentence_len[name] = round(avg_len, 1)
            if avg_len > 30:
                tips.append(f"Shorten sentences in {name} section (avg {avg_len:.0f} words — aim for <25)")

    # ── JSON output ───────────────────────────────────────────────────
    if json_mode:
        result = {
            "overall_score": overall_score,
            "cv_formality": cv_overall,
            "cl_formality": cl_formality,
            "tone_match": tone_match,
            "tone_delta": tone_delta,
            "sections": {
                name: {
                    "formality": score,
                    "avg_sentence_length": avg_sentence_len.get(name),
                }
                for name, score in section_scores.items()
            },
            "action_verbs": verb_analysis,
            "passive_voice": passive,
            "filler_words": filler,
            "consistency": {"std_dev": std_dev, "is_consistent": is_consistent},
            "warnings": warnings,
            "tips": tips,
        }
        print(json.dumps(result, indent=2))
        return 0

    # ── Terminal output ───────────────────────────────────────────────
    app_name = app_dir.name
    print(f"📊 Tone Analysis: {app_name}")
    print("═" * 52)
    print()

    print("📋 CV Sections:")
    for name, score in section_scores.items():
        label = name.replace("_", " ").title()
        print(f"  {label:<14} Formality {score:>5}/100  [{bar(score)}]")

    consistency_label = f"✅ Consistent (σ={std_dev})" if is_consistent else f"⚠️  Inconsistent (σ={std_dev})"
    print(f"  {'Overall CV':<14} Formality {cv_overall:>5}/100  {consistency_label}")
    print()

    if cl_formality is not None:
        match_label = f"✅ Good match with CV (Δ={tone_delta:.0f})" if tone_match else f"⚠️  Mismatch with CV (Δ={tone_delta:.0f})"
        print(f"📨 Cover Letter:  Formality {cl_formality:>5}/100  {match_label}")
        print()
    else:
        print("📨 Cover Letter:  Not found — skipping CL analysis")
        print()

    # Action verbs
    total_v = verb_analysis["total"]
    strong_v = verb_analysis["strong"]
    if total_v > 0:
        rate_pct = strong_v / total_v * 100
        verb_icon = "✅" if rate_pct >= 70 else "⚠️ "
        print(f"💪 Action Verbs:  {strong_v}/{total_v} bullets start with strong verbs {verb_icon}")
        if verb_analysis["weak_bullets"]:
            for b in verb_analysis["weak_bullets"][:3]:
                print(f"   ⚠️  Weak starter: \"{b}\"")
        if verb_analysis["unclear_bullets"] and rate_pct < 70:
            for b in verb_analysis["unclear_bullets"][:2]:
                print(f"   ❓ Unclear: \"{b}\"")
    print()

    # Passive voice
    pv = passive
    pv_icon = "✅" if pv["rate_pct"] <= 15 else "⚠️ "
    print(f"🚫 Passive Voice: {pv['count']}/{pv['total_sentences']} sentences ({pv['rate_pct']:.0f}%) {pv_icon}")
    if pv["rate_pct"] > 15 and pv["examples"]:
        for ex in pv["examples"][:2]:
            print(f"   ⚠️  Found: \"{ex}\"")
    print()

    # Filler words
    if filler["found"]:
        words_str = ", ".join(f"{w} (×{c})" for w, c in list(filler["found"].items())[:5])
        print(f"🗑️  Filler Words:  ⚠️  Found: {words_str}")
    else:
        print("🗑️  Filler Words:  ✅ None found")
    print()

    # Overall score
    if overall_score >= 85:
        score_label = "🟢 Excellent"
    elif overall_score >= 70:
        score_label = "🟡 Good — minor improvements possible"
    else:
        score_label = "🔴 Needs attention"
    print(f"🎯 Overall Score: {overall_score}/100  {score_label}")
    print()

    if tips:
        print("💡 Tips:")
        for tip in tips[:6]:
            print(f"   • {tip}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
