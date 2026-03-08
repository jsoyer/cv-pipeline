#!/usr/bin/env python3
"""
Keyword Trends — temporal analysis + gap analysis of job posting keywords.

Analyses all applications/ with job.txt to identify:
  - Rising keywords: increasingly frequent in recent postings
  - Declining keywords: less frequent recently
  - Stable keywords: consistently required
  - Gap analysis: keywords missing from your master CV

Usage:
    scripts/keyword-trends.py [--top N] [--since YYYY-MM] [--json] [--save]
"""

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent

from lib.common import REPO_ROOT

# ---------------------------------------------------------------------------
# Import helpers from ats-score.py (hyphen in filename → importlib)
# ---------------------------------------------------------------------------

def _import_ats():
    spec = importlib.util.spec_from_file_location(
        "ats_score", _SCRIPT_DIR / "ats-score.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_ats = _import_ats()
tokenize = _ats.tokenize
extract_bigrams = _ats.extract_bigrams


# ---------------------------------------------------------------------------
# Application loading
# ---------------------------------------------------------------------------

def _parse_month(s: str) -> str:
    """Validate YYYY-MM format, raise ValueError if invalid."""
    if not re.fullmatch(r"\d{4}-\d{2}", s):
        raise ValueError(f"Invalid month format '{s}' — expected YYYY-MM")
    return s


def _folder_month(d: Path):
    """Extract YYYY-MM from folder name like 2026-02-company → '2026-02'."""
    m = re.match(r"(\d{4}-\d{2})", d.name)
    return m.group(1) if m else None


def _load_applications(since=None) -> list:
    """
    Return sorted list of applications that have job.txt.
    Each item: {name, company, position, created, job_text}
    """
    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.exists():
        return []

    apps = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue

        meta_path = d / "meta.yml"
        created = None
        company = d.name
        position = ""

        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
            created = meta.get("created")
            if created:
                created = str(created)[:7]
            company = meta.get("company", d.name)
            position = meta.get("position", "")

        if not created or not re.fullmatch(r"\d{4}-\d{2}", str(created)):
            created = _folder_month(d)

        if not created:
            continue

        if since and str(created) < since:
            continue

        job_path = d / "job.txt"
        if not job_path.exists():
            continue

        with open(job_path, encoding="utf-8") as f:
            job_text = f.read().lower()

        apps.append({
            "name": d.name,
            "company": company,
            "position": position,
            "created": str(created),
            "job_text": job_text,
        })

    apps.sort(key=lambda a: a["created"])
    return apps


def _extract_keywords_from_job(job_text: str) -> set:
    """Return the set of keywords (unigrams + bigrams) present in a job posting."""
    tokens = tokenize(job_text)
    return set(tokens) | set(extract_bigrams(tokens))


def _build_keyword_presence(apps: list, min_jobs: int = 2) -> dict:
    """
    Build mapping of keyword -> [present_in_app_0, present_in_app_1, ...].
    Only keywords that appear in >= min_jobs applications are kept.
    """
    kw_sets = [_extract_keywords_from_job(a["job_text"]) for a in apps]

    all_kws: Counter = Counter()
    for ks in kw_sets:
        all_kws.update(ks)

    presence = {}
    for kw, total in all_kws.items():
        if total < min_jobs:
            continue
        presence[kw] = [kw in ks for ks in kw_sets]

    return presence


def _compute_trend(presence_vec: list):
    """
    Split vector into early half and recent half.
    Returns (overall_freq, early_freq, recent_freq).
    """
    n = len(presence_vec)
    mid = max(1, n // 2)
    early = presence_vec[:mid]
    recent = presence_vec[mid:] if n > 1 else presence_vec

    early_freq = sum(early) / len(early)
    recent_freq = sum(recent) / len(recent)
    overall_freq = sum(presence_vec) / n

    return overall_freq, early_freq, recent_freq


def _trend_label(early_freq: float, recent_freq: float):
    """Classify trend: rising (>+20%), declining (<-20%), or stable."""
    if early_freq == 0:
        return ("rising", 100.0) if recent_freq > 0 else ("stable", 0.0)

    pct = (recent_freq - early_freq) / early_freq * 100.0

    if pct > 20:
        return "rising", pct
    if pct < -20:
        return "declining", pct
    return "stable", pct


# ---------------------------------------------------------------------------
# CV text extraction for gap analysis
# ---------------------------------------------------------------------------

def _flatten_yaml_text(obj) -> str:
    """Recursively extract all string values from a YAML object."""
    if isinstance(obj, str):
        return obj + " "
    if isinstance(obj, list):
        return "".join(_flatten_yaml_text(i) for i in obj)
    if isinstance(obj, dict):
        return "".join(_flatten_yaml_text(v) for v in obj.values())
    return ""


def _load_cv_text() -> str:
    """Load data/cv.yml and return all text content lowercased."""
    cv_path = REPO_ROOT / "data" / "cv.yml"
    if not cv_path.exists():
        return ""
    with open(cv_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return _flatten_yaml_text(data).lower()


def _keyword_in_cv(kw: str, cv_text: str) -> bool:
    """Return True if the keyword (or its hyphenated variant) appears in the CV."""
    if re.search(r"\b" + re.escape(kw) + r"\b", cv_text):
        return True
    alt = kw.replace(" ", "-") if " " in kw else kw.replace("-", " ")
    return bool(re.search(r"\b" + re.escape(alt) + r"\b", cv_text))


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

BAR_FULL = "█"
BAR_EMPTY = "░"
BAR_WIDTH = 8


def _bar(freq: float) -> str:
    filled = round(freq * BAR_WIDTH)
    return BAR_FULL * filled + BAR_EMPTY * (BAR_WIDTH - filled)


def _trend_icon(label: str) -> str:
    return {"rising": "📈", "declining": "📉", "stable": "➡️ "}.get(label, "➡️ ")


def _cv_icon(in_cv: bool) -> str:
    return "✅ In CV" if in_cv else "❌ Missing"


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyse(top_n: int, since=None) -> dict:
    apps = _load_applications(since)
    if not apps:
        return {
            "error": "No applications with job.txt found.",
            "applications": [],
            "keywords": [],
        }

    cv_text = _load_cv_text()
    presence = _build_keyword_presence(apps, min_jobs=2)

    results = []
    n = len(apps)
    for kw, vec in presence.items():
        overall_freq, early_freq, recent_freq = _compute_trend(vec)
        trend, pct = _trend_label(early_freq, recent_freq)
        job_count = sum(vec)
        in_cv = _keyword_in_cv(kw, cv_text)

        results.append({
            "keyword": kw,
            "frequency": round(overall_freq, 4),
            "job_count": job_count,
            "trend": trend,
            "trend_pct": round(pct, 1),
            "in_cv": in_cv,
        })

    results.sort(key=lambda r: (-r["job_count"], -r["frequency"], r["keyword"]))
    top_results = results[:top_n]

    missing = [r["keyword"] for r in top_results if not r["in_cv"]]
    add_recs = [
        r["keyword"] for r in top_results
        if r["trend"] == "rising" and not r["in_cv"]
    ]
    remove_recs = [
        r["keyword"] for r in top_results
        if r["trend"] == "declining" and r["in_cv"]
    ]
    watch_recs = [r["keyword"] for r in top_results if r["job_count"] == n]

    recommendations = []
    if add_recs:
        recommendations.append(
            f"Add to your CV: {', '.join(add_recs[:5])} (trending + missing)"
        )
    if remove_recs:
        recommendations.append(
            f"Consider removing: {', '.join(remove_recs[:3])} (declining demand)"
        )
    if watch_recs:
        universal = [w for w in watch_recs if w not in add_recs and w not in remove_recs]
        if universal:
            recommendations.append(
                f"Watch: {', '.join(universal[:3])} (required across all applications)"
            )

    return {
        "period": {"from": apps[0]["created"], "to": apps[-1]["created"]},
        "total_applications": n,
        "keywords": top_results,
        "missing_from_cv": missing[:15],
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

def _print_terminal(data: dict) -> None:
    n = data["total_applications"]
    period = data["period"]
    keywords = data["keywords"]

    width = 68
    print(f"\n📊 Keyword Trends  ({n} application{'s' if n != 1 else ''} · {period['from']} → {period['to']})")
    print("═" * width)

    rising = [r for r in keywords if r["trend"] == "rising"]
    stable = [r for r in keywords if r["trend"] == "stable"]
    declining = [r for r in keywords if r["trend"] == "declining"]

    def _fmt_row(r: dict, show_pct: bool = True) -> str:
        bar = _bar(r["frequency"])
        count_str = f"({r['job_count']}/{n} jobs)"
        icon = _trend_icon(r["trend"])
        cv_str = _cv_icon(r["in_cv"])
        if show_pct and r["trend"] != "stable":
            pct_str = f"{r['trend_pct']:+.0f}%"
            return f"  {r['keyword']:<22} {bar}  {count_str:<13} {icon} {pct_str:>6}  {cv_str}"
        return f"  {r['keyword']:<22} {bar}  {count_str:<13} {icon}          {cv_str}"

    if rising:
        print("\n📈 Rising Keywords (seen in more recent postings):")
        for r in rising:
            print(_fmt_row(r, show_pct=True))

    if stable:
        print("\n➡️  Stable Keywords (consistent across all jobs):")
        for r in stable:
            print(_fmt_row(r, show_pct=False))

    if declining:
        print("\n📉 Declining Keywords:")
        for r in declining:
            print(_fmt_row(r, show_pct=True))

    print("\n" + "─" * width)

    missing = data["missing_from_cv"]
    if missing:
        print("❌ Top missing keywords (not in your CV):")
        print(f"  {', '.join(missing)}")

    recs = data["recommendations"]
    if recs:
        print("\n💡 Recommendations:")
        for rec in recs:
            print(f"  • {rec}")

    print()


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------

def _build_markdown(data: dict) -> str:
    n = data["total_applications"]
    period = data["period"]
    keywords = data["keywords"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# 📊 Keyword Trends",
        "",
        f"**{n} application{'s' if n != 1 else ''}** · Period: {period['from']} → {period['to']} · Generated: {now}",
        "",
    ]

    rising = [r for r in keywords if r["trend"] == "rising"]
    stable = [r for r in keywords if r["trend"] == "stable"]
    declining = [r for r in keywords if r["trend"] == "declining"]

    def _md_row(r: dict) -> str:
        icon = _trend_icon(r["trend"]).strip()
        cv_icon = "✅" if r["in_cv"] else "❌"
        pct = f"{r['trend_pct']:+.0f}%" if r["trend"] != "stable" else "—"
        freq_pct = f"{r['frequency']*100:.0f}%"
        return f"| {r['keyword']} | {freq_pct} | {r['job_count']}/{n} | {icon} | {pct} | {cv_icon} |"

    header = "| Keyword | Frequency | Jobs | Trend | Change | In CV |"
    divider = "|---------|-----------|------|-------|--------|-------|"

    if rising:
        lines += ["## 📈 Rising Keywords", "", header, divider]
        lines += [_md_row(r) for r in rising]
        lines.append("")

    if stable:
        lines += ["## ➡️ Stable Keywords", "", header, divider]
        lines += [_md_row(r) for r in stable]
        lines.append("")

    if declining:
        lines += ["## 📉 Declining Keywords", "", header, divider]
        lines += [_md_row(r) for r in declining]
        lines.append("")

    missing = data["missing_from_cv"]
    if missing:
        lines += [
            "## ❌ Top Missing Keywords",
            "",
            ", ".join(f"`{kw}`" for kw in missing),
            "",
        ]

    recs = data["recommendations"]
    if recs:
        lines += ["## 💡 Recommendations", ""]
        for rec in recs:
            lines.append(f"- {rec}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keyword Trends — temporal + gap analysis of job posting keywords."
    )
    parser.add_argument(
        "--top", type=int, default=20, metavar="N",
        help="Show top N keywords (default: 20)"
    )
    parser.add_argument(
        "--since", type=str, default=None, metavar="YYYY-MM",
        help="Only consider applications from this month onwards"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON"
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save report to keyword-trends.md in repo root"
    )
    args = parser.parse_args()

    if args.since:
        try:
            _parse_month(args.since)
        except ValueError as exc:
            print(f"❌ {exc}")
            sys.exit(1)

    data = analyse(top_n=args.top, since=args.since)

    if "error" in data:
        if args.json:
            print(json.dumps({"error": data["error"]}, indent=2))
        else:
            print(f"❌ {data['error']}")
        sys.exit(1)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        _print_terminal(data)

    if args.save:
        md = _build_markdown(data)
        out_path = REPO_ROOT / "keyword-trends.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        if not args.json:
            print(f"📊 Report saved to {out_path}")


if __name__ == "__main__":
    main()
