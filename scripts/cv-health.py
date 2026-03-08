#!/usr/bin/env python3
"""
Advanced CV health check — quantification, action verbs, bullet balance,
profile length, repetition, section completeness.

Goes beyond lint/tone to give a scored audit of your CV content quality.

Usage:
    scripts/cv-health.py [-d data/cv.yml] [--name APP_NAME] [--json]

Options:
    -d FILE       YAML file to analyse (default: data/cv.yml)
    --name NAME   Analyse cv-tailored.yml for a specific application
    --json        Output JSON
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

from lib.common import REPO_ROOT, STOP_WORDS

STRONG_VERBS = frozenset({
    "accelerated", "achieved", "built", "championed", "closed", "coached",
    "delivered", "designed", "developed", "directed", "drove", "established",
    "exceeded", "expanded", "generated", "grew", "hired", "implemented",
    "increased", "launched", "led", "managed", "mentored", "negotiated",
    "optimized", "orchestrated", "oversaw", "partnered", "pioneered",
    "recruited", "reduced", "scaled", "secured", "spearheaded", "standardized",
    "streamlined", "transformed", "won",
    # Past tense variants of common strong verbs
    "directing", "scaling", "driving", "leading", "managing", "building",
    "delivering", "expanding", "growing", "establishing", "partnering",
    "overseeing", "orchestrating",
})

WEAK_VERBS = frozenset({
    "helped", "assisted", "worked", "supported", "contributed",
    "participated", "involved", "responsible", "handled", "did", "made",
    "was", "were", "utilized", "leveraged", "used",
})

# Number / metric patterns
METRIC_RE = re.compile(
    r"\b\d[\d,]*%|\$[\d,]+|\€[\d,]+|"
    r"\d+x\b|\d+\+?\s*(?:HC|employees|team|people|engineers|countries|"
    r"clients|accounts|deals|languages|years)|"
    r"\b(?:\d+|\d+\.\d+)\s*(?:M|B|K)\b|"
    r"(?:first|second|third|top)\s+\d+%|"
    r"\d+[\d,]*\s*(?:million|billion|thousand)|"
    r"(?:2x|3x|4x|5x|10x)",
    re.IGNORECASE,
)


def _strip_bold(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(text or ""))


def _flatten_items(items) -> list[str]:
    result = []
    if not items:
        return result
    for item in items:
        if isinstance(item, str):
            result.append(_strip_bold(item))
        elif isinstance(item, dict):
            text  = _strip_bold(item.get("text", ""))
            label = _strip_bold(item.get("label", ""))
            if text:
                result.append(f"{label}: {text}" if label else text)
    return result


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def _check_quantification(bullets: list) -> dict:
    """% of bullets that contain at least one metric."""
    if not bullets:
        return {"score": 0, "rate": 0.0, "total": 0, "with_metrics": 0}

    with_metrics = sum(1 for b in bullets if METRIC_RE.search(b))
    rate = with_metrics / len(bullets) * 100

    # Score: 100 if ≥ 70%, proportional below
    score = min(100, int(rate / 70 * 100))
    return {
        "score": score,
        "rate":  round(rate, 1),
        "total": len(bullets),
        "with_metrics": with_metrics,
        "detail": f"{with_metrics}/{len(bullets)} bullets contain numbers/metrics ({rate:.0f}%)",
    }


def _check_action_verbs(bullets: list) -> dict:
    """Quality of first words (action verbs)."""
    if not bullets:
        return {"score": 0, "strong": 0, "weak": 0, "neutral": 0}

    strong = weak = neutral = 0
    weak_examples = []
    for bullet in bullets:
        words = re.findall(r"[a-zA-Z]+", bullet.lower())
        if not words:
            continue
        first = words[0]
        if first in STRONG_VERBS:
            strong += 1
        elif first in WEAK_VERBS:
            weak += 1
            weak_examples.append(first)
        else:
            neutral += 1

    total = strong + weak + neutral
    if total == 0:
        return {"score": 0, "strong": 0, "weak": 0, "neutral": 0}

    strong_pct = strong / total * 100
    weak_pct   = weak   / total * 100
    score = max(0, min(100, int(strong_pct * 1.2 - weak_pct * 1.5)))

    return {
        "score":        score,
        "strong":       strong,
        "weak":         weak,
        "neutral":      neutral,
        "weak_examples": list(set(weak_examples))[:5],
        "detail": (
            f"{strong}/{total} strong verbs ({strong_pct:.0f}%), "
            f"{weak} weak ({weak_pct:.0f}%)"
            + (f" — replace: {', '.join(set(weak_examples)[:3])}" if weak_examples else "")
        ),
    }


def _check_bullet_length(bullets: list) -> dict:
    """Bullet length distribution — ideal 8-20 words."""
    if not bullets:
        return {"score": 0, "too_short": 0, "ideal": 0, "too_long": 0}

    too_short = too_long = ideal = 0
    for b in bullets:
        wc = len(b.split())
        if wc < 6:
            too_short += 1
        elif wc > 25:
            too_long += 1
        else:
            ideal += 1

    total = len(bullets)
    ideal_pct = ideal / total * 100
    score = max(0, int(ideal_pct - too_long * 5))

    return {
        "score":     min(100, score),
        "too_short": too_short,
        "ideal":     ideal,
        "too_long":  too_long,
        "detail": (
            f"{ideal}/{total} ideal length (6-25 words), "
            f"{too_short} too short, {too_long} too long"
        ),
    }


def _check_profile(profile: str) -> dict:
    """Profile/summary quality — length and keyword richness."""
    if not profile:
        return {"score": 0, "words": 0, "detail": "Profile section missing"}

    text = _strip_bold(profile)
    words = text.split()
    word_count = len(words)

    # Ideal: 40-80 words
    if 40 <= word_count <= 80:
        length_score = 100
    elif word_count < 40:
        length_score = int(word_count / 40 * 100)
    else:
        length_score = max(60, int(100 - (word_count - 80) * 2))

    # Contains numbers/metrics?
    has_metric = bool(METRIC_RE.search(text))
    score = min(100, length_score + (10 if has_metric else 0))

    status = "ideal" if 40 <= word_count <= 80 else ("too short" if word_count < 40 else "too long")
    return {
        "score":      min(100, score),
        "words":      word_count,
        "has_metric": has_metric,
        "detail":     f"{word_count} words ({status}), {'has' if has_metric else 'no'} metrics",
    }


def _check_repetition(bullets: list, profile: str) -> dict:
    """Detect overused words (after stop words)."""
    all_text = " ".join(bullets) + " " + (profile or "")
    words = re.findall(r"[a-z]{4,}", all_text.lower())
    filtered = [w for w in words if w not in STOP_WORDS]
    counts = Counter(filtered).most_common(10)

    overused = [(w, n) for w, n in counts if n >= 4]
    score = max(0, 100 - len(overused) * 15)

    return {
        "score":    score,
        "overused": overused[:5],
        "top_10":   counts,
        "detail": (
            f"{len(overused)} overused words: {', '.join(f'{w}×{n}' for w, n in overused[:5])}"
            if overused else "Good word variety"
        ),
    }


def _check_completeness(data: dict) -> dict:
    """Required sections present and non-empty."""
    required = [
        ("personal",       "Personal info"),
        ("profile",        "Profile/summary"),
        ("skills",         "Skills"),
        ("key_wins",       "Key achievements"),
        ("experience",     "Experience"),
        ("education",      "Education"),
        ("certifications", "Certifications"),
        ("languages",      "Languages"),
    ]
    present   = [(label, bool(data.get(key))) for key, label in required]
    n_present = sum(1 for _, ok in present if ok)
    score     = int(n_present / len(required) * 100)
    missing   = [label for label, ok in present if not ok]

    return {
        "score":   score,
        "present": n_present,
        "total":   len(required),
        "missing": missing,
        "detail":  (
            f"{n_present}/{len(required)} sections present"
            + (f" — missing: {', '.join(missing)}" if missing else "")
        ),
    }


# ---------------------------------------------------------------------------
# Main audit function
# ---------------------------------------------------------------------------

def audit(data: dict) -> dict:
    # Collect all experience bullets
    bullets = []
    for exp in data.get("experience", []) + data.get("early_career", []):
        bullets.extend(_flatten_items(exp.get("items", [])))

    profile = _strip_bold(data.get("profile", ""))

    quant   = _check_quantification(bullets)
    verbs   = _check_action_verbs(bullets)
    lengths = _check_bullet_length(bullets)
    prof    = _check_profile(profile)
    rept    = _check_repetition(bullets, profile)
    compl   = _check_completeness(data)

    # Weighted overall score
    weights = {
        "quantification": (quant["score"],   0.25),
        "action_verbs":   (verbs["score"],   0.20),
        "bullet_length":  (lengths["score"], 0.15),
        "profile":        (prof["score"],    0.15),
        "repetition":     (rept["score"],    0.15),
        "completeness":   (compl["score"],   0.10),
    }
    overall = int(sum(s * w for s, w in weights.values()))

    return {
        "overall": overall,
        "grade":   (
            "🟢 Excellent" if overall >= 80 else
            "🟡 Good"      if overall >= 65 else
            "🟠 Fair"      if overall >= 50 else
            "🔴 Needs work"
        ),
        "bullet_count":    len(bullets),
        "quantification":  quant,
        "action_verbs":    verbs,
        "bullet_length":   lengths,
        "profile":         prof,
        "repetition":      rept,
        "completeness":    compl,
    }


def main():
    parser = argparse.ArgumentParser(description="Advanced CV health check")
    parser.add_argument("-d", "--data",   default="data/cv.yml", help="YAML source file")
    parser.add_argument("--name",         default="",            help="Check cv-tailored.yml for app")
    parser.add_argument("--json",         action="store_true",   help="Output JSON")
    args = parser.parse_args()

    if args.name:
        data_path = REPO_ROOT / "applications" / args.name / "cv-tailored.yml"
        if not data_path.exists():
            print(f"⚠️  No cv-tailored.yml for {args.name} — falling back to data/cv.yml")
            data_path = REPO_ROOT / "data" / "cv.yml"
    else:
        data_path = REPO_ROOT / args.data

    if not data_path.exists():
        print(f"❌ File not found: {data_path}")
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    print(f"🩺 CV Health Check — {data_path.name}")
    result = audit(data)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    overall = result["overall"]
    print(f"\n   Overall: {overall}/100  {result['grade']}\n")
    print(f"   Analysed {result['bullet_count']} experience bullets\n")

    metrics = [
        ("quantification", "📊", "Quantification",  25),
        ("action_verbs",   "🚀", "Action verbs",    20),
        ("bullet_length",  "📏", "Bullet length",   15),
        ("profile",        "📝", "Profile",         15),
        ("repetition",     "🔁", "Word variety",    15),
        ("completeness",   "✅", "Completeness",    10),
    ]
    print(f"   {'Metric':<22}  {'Score':>7}  {'Weight':>7}  Detail")
    print("   " + "─" * 70)
    for key, icon, label, weight in metrics:
        d = result[key]
        score = d["score"]
        detail = d.get("detail", "")[:55]
        print(f"   {icon} {label:<20}  {score:>5}/100  ({weight:>2}%)   {detail}")

    # Actionable recommendations
    print("\n💡 Recommendations:")
    recs = []
    q = result["quantification"]
    if q["score"] < 70:
        n_missing = q["total"] - q["with_metrics"]
        recs.append(f"   • Add numbers to {n_missing} more bullets — use %, $, HC, YoY")
    v = result["action_verbs"]
    if v.get("weak_examples"):
        recs.append(f"   • Replace weak verbs: {', '.join(v['weak_examples'][:3])}")
    bl = result["bullet_length"]
    if bl["too_long"] > 0:
        recs.append(f"   • Shorten {bl['too_long']} bullet(s) > 25 words")
    if bl["too_short"] > 0:
        recs.append(f"   • Expand {bl['too_short']} bullet(s) < 6 words — add context")
    rep = result["repetition"]
    if rep["overused"]:
        recs.append(f"   • Diversify: {', '.join(f'{w}×{n}' for w, n in rep['overused'][:3])}")
    prof = result["profile"]
    if prof["words"] < 40:
        recs.append("   • Profile too short — aim for 40-80 words")
    elif prof["words"] > 80:
        recs.append("   • Profile too long — trim to 80 words max")
    comp = result["completeness"]
    if comp["missing"]:
        recs.append(f"   • Add missing sections: {', '.join(comp['missing'])}")

    if recs:
        for r in recs:
            print(r)
    else:
        print("   Nothing critical — your CV looks healthy! 🎉")

    print()
    return 0 if overall >= 65 else 1


if __name__ == "__main__":
    sys.exit(main())
