#!/usr/bin/env python3
"""
Personal fit score — how well a job posting matches YOUR preferences.

Complements ATS score (CV → job) with the YOU → job direction:
salary signals, remote policy, location, company size, industry, deal-breakers.

Reads:  data/preferences.yml (your preferences)
        applications/NAME/job.txt (job posting)
        applications/NAME/meta.yml (company/position label)

Output: terminal breakdown + applications/NAME/job-fit.md

Usage:
    scripts/job-fit.py <app-dir> [--json]
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT

# ---------------------------------------------------------------------------
# Signals — keywords to look for in the job posting
# ---------------------------------------------------------------------------

REMOTE_SIGNALS = {
    "fully remote": 25, "100% remote": 25, "remote first": 25, "remote-first": 25,
    "work from anywhere": 25,
    "remote": 18, "hybrid": 16, "flexible working": 15, "work from home": 15,
    "flexible location": 14, "distributed team": 14,
    "in-office": 4, "on-site": 4, "onsite": 4,
    "full time on-site": 0, "full-time on site": 0, "fully on-site": 0,
    "on site only": 0, "100% onsite": 0, "must be based": 2,
}

SIZE_SIGNALS = {
    "startup":       {"startup", "early stage", "seed", "series a", "series b", "series c",
                      "pre-ipo", "50 employees", "100 employees"},
    "mid":           {"scale-up", "scaleup", "series d", "series e", "growth stage",
                      "500 employees", "1000 employees", "1,000 employees"},
    "enterprise":    {"fortune 500", "fortune500", "global company", "listed company",
                      "10,000 employees", "nasdaq", "nyse", "enterprise", "multinational",
                      "publicly traded", "publicly listed"},
}

CULTURE_SIGNALS = [
    "equity", "rsu", "stock options", "esop",
    "unlimited pto", "unlimited vacation", "flexible hours",
    "learning budget", "education budget", "conference budget",
    "parental leave", "mental health",
    "collaborative", "diverse", "inclusion",
]


def _load_preferences() -> dict:
    prefs_path = REPO_ROOT / "data" / "preferences.yml"
    if not prefs_path.exists():
        return {}
    with open(prefs_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_meta(app_dir: Path) -> dict:
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return {}
    with open(meta_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Scoring dimensions
# ---------------------------------------------------------------------------

def _score_remote(job_text: str, prefs: dict) -> tuple:
    """Score remote policy (0-25)."""
    preferred = prefs.get("remote", {}).get("preferred", "hybrid")
    acceptable = set(prefs.get("remote", {}).get("acceptable", ["remote", "hybrid"]))

    job_lower = job_text.lower()

    best_score = 10  # unknown default
    best_signal = "not specified"

    for signal, raw_score in sorted(REMOTE_SIGNALS.items(), key=lambda x: -x[1]):
        if signal in job_lower:
            best_score = raw_score
            best_signal = signal
            break

    # Adjust based on preference match
    if best_score >= 18 and "remote" in acceptable:
        pass  # full match
    elif best_score in range(14, 18) and "hybrid" in acceptable:
        pass  # full match
    elif best_score < 5 and "onsite" not in acceptable:
        pass  # low score is correct — mismatch

    return min(25, best_score), best_signal


def _score_location(job_text: str, prefs: dict) -> tuple:
    """Score location match (0-20)."""
    preferred = [l.lower() for l in prefs.get("location", {}).get("preferred", [])]
    acceptable = [l.lower() for l in prefs.get("location", {}).get("acceptable", [])]
    job_lower = job_text.lower()

    for loc in preferred:
        if loc in job_lower:
            return 20, f"preferred location: {loc}"

    for loc in acceptable:
        if loc in job_lower:
            return 13, f"acceptable location: {loc}"

    if "remote" in job_lower or "anywhere" in job_lower:
        return 16, "remote (any location)"

    return 8, "location not clearly specified"


def _score_company_size(job_text: str, prefs: dict) -> tuple:
    """Score company size signals (0-20)."""
    preferred = prefs.get("company_size", {}).get("preferred", [])
    acceptable = prefs.get("company_size", {}).get("acceptable", ["startup", "mid", "enterprise"])
    job_lower = job_text.lower()

    for size, signals in SIZE_SIGNALS.items():
        for signal in signals:
            if signal in job_lower:
                if size in preferred:
                    return 20, f"{size} ({signal})"
                elif size in acceptable:
                    return 12, f"{size} ({signal}) — acceptable"
                else:
                    return 5, f"{size} — not preferred"

    return 10, "company size not specified"


def _score_industry(job_text: str, prefs: dict) -> tuple:
    """Score industry match (0-20)."""
    preferred = [i.lower() for i in prefs.get("industry", {}).get("preferred", [])]
    avoid = [i.lower() for i in prefs.get("industry", {}).get("avoid", [])]
    job_lower = job_text.lower()

    for kw in avoid:
        if kw in job_lower:
            return 0, f"avoid keyword: {kw}"

    matches = [kw for kw in preferred if kw in job_lower]
    if len(matches) >= 3:
        return 20, f"strong industry match: {', '.join(matches[:3])}"
    elif len(matches) == 2:
        return 17, f"good industry match: {', '.join(matches)}"
    elif len(matches) == 1:
        return 12, f"partial match: {matches[0]}"
    return 8, "industry not clearly specified"


def _score_culture(job_text: str) -> tuple:
    """Score culture & benefits signals (0-15)."""
    job_lower = job_text.lower()
    found = [s for s in CULTURE_SIGNALS if s in job_lower]
    if len(found) >= 4:
        return 15, f"{', '.join(found[:4])}"
    elif len(found) >= 2:
        return 10, f"{', '.join(found[:2])}"
    elif len(found) == 1:
        return 6, found[0]
    return 3, "few culture/benefit signals found"


def _check_deal_breakers(job_text: str, prefs: dict) -> list:
    """Return list of deal-breaker phrases found in job."""
    deal_breakers = prefs.get("deal_breakers", [])
    job_lower = job_text.lower()
    return [db for db in deal_breakers if db.lower() in job_lower]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _grade(score: int) -> str:
    if score >= 80:
        return "🟢 Excellent fit"
    elif score >= 65:
        return "🟡 Good fit"
    elif score >= 50:
        return "🟠 Partial fit — check details"
    else:
        return "🔴 Poor fit — significant gaps"


def score_job(app_dir: Path) -> dict:
    prefs = _load_preferences()
    if not prefs:
        return {"error": "data/preferences.yml not found — run from repo root"}

    job_path = app_dir / "job.txt"
    if not job_path.exists():
        return {"error": f"job.txt not found in {app_dir}"}

    job_text = job_path.read_text(encoding="utf-8")

    remote_score,   remote_detail   = _score_remote(job_text, prefs)
    location_score, location_detail = _score_location(job_text, prefs)
    size_score,     size_detail     = _score_company_size(job_text, prefs)
    industry_score, industry_detail = _score_industry(job_text, prefs)
    culture_score,  culture_detail  = _score_culture(job_text)
    deal_breakers_found             = _check_deal_breakers(job_text, prefs)

    raw_total = remote_score + location_score + size_score + industry_score + culture_score
    penalty = len(deal_breakers_found) * 20
    total = max(0, raw_total - penalty)

    return {
        "total": total,
        "dimensions": {
            "remote":   {"score": remote_score,   "max": 25, "detail": remote_detail},
            "location": {"score": location_score, "max": 20, "detail": location_detail},
            "size":     {"score": size_score,     "max": 20, "detail": size_detail},
            "industry": {"score": industry_score, "max": 20, "detail": industry_detail},
            "culture":  {"score": culture_score,  "max": 15, "detail": culture_detail},
        },
        "deal_breakers": deal_breakers_found,
        "penalty": penalty,
        "grade": _grade(total),
    }


def save_report(app_dir: Path, meta: dict, result: dict) -> Path:
    from datetime import date
    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    today    = date.today().isoformat()
    total    = result["total"]

    lines = [
        f"# Job Fit — {company}",
        f"*{position} · Scored: {today}*",
        "",
        f"## Overall: {total}/100 — {result['grade']}",
        "",
        "| Dimension | Score | Max | Detail |",
        "|:----------|:------|:----|:-------|",
    ]
    dim_labels = {
        "remote":   "🏠 Remote policy",
        "location": "📍 Location",
        "size":     "🏢 Company size",
        "industry": "🏭 Industry",
        "culture":  "🌟 Culture/benefits",
    }
    for key, label in dim_labels.items():
        d = result["dimensions"][key]
        bar = "█" * int(d["score"] / d["max"] * 10)
        lines.append(f"| {label} | {d['score']}/{d['max']} | {d['max']} | {d['detail']} |")

    if result["deal_breakers"]:
        lines += [
            "",
            "## ⚠️ Deal Breakers Found",
            "",
        ]
        for db in result["deal_breakers"]:
            lines.append(f'- ❌ "{db}"')
        lines.append(f"\n*Penalty: -{result['penalty']} points*")

    prefs = _load_preferences()
    lines += [
        "",
        "## Your Preferences (data/preferences.yml)",
        "",
        f"- Remote: **{prefs.get('remote', {}).get('preferred', '?')}** preferred",
        f"- Location: {', '.join(prefs.get('location', {}).get('preferred', []))}",
        f"- Industries: {', '.join(prefs.get('industry', {}).get('preferred', []))}",
        "",
    ]

    out_path = app_dir / "job-fit.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Score job fit vs your personal preferences"
    )
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    if not (app_dir / "job.txt").exists():
        print(f"❌ No job.txt in {app_dir} — run: make fetch NAME={app_dir.name}")
        sys.exit(1)

    meta   = _load_meta(app_dir)
    result = score_job(app_dir)

    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    total    = result["total"]

    print(f"\n🎯 Job Fit — {company} ({position})")
    print("─" * 55)
    print(f"   Overall: {total}/100  {result['grade']}\n")

    dim_labels = {
        "remote":   ("🏠", "Remote policy"),
        "location": ("📍", "Location"),
        "size":     ("🏢", "Company size"),
        "industry": ("🏭", "Industry"),
        "culture":  ("🌟", "Culture/benefits"),
    }
    for key, (icon, label) in dim_labels.items():
        d = result["dimensions"][key]
        bar = "█" * int(d["score"] / d["max"] * 10)
        pct = int(d["score"] / d["max"] * 100)
        print(f"   {icon} {label:<18} {d['score']:>2}/{d['max']} ({pct:>3}%)  {d['detail']}")

    if result["deal_breakers"]:
        print(f"\n   ⚠️  Deal breakers found (-{result['penalty']} pts):")
        for db in result["deal_breakers"]:
            print(f'      ❌ "{db}"')

    out_path = save_report(app_dir, meta, result)
    print(f"\n✅ Report saved to {out_path}")

    return 0 if total >= 65 else 1


if __name__ == "__main__":
    sys.exit(main())
