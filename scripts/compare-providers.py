#!/usr/bin/env python3
"""
Compare AI provider outputs for the same CV tailoring job.

Runs the same prompt against all configured providers (those with API keys set)
concurrently, then shows a side-by-side comparison: ATS keyword overlap, profile
length, experience bullet count, and key skills mentioned.

Usage:
    scripts/compare-providers.py <app-dir> [--providers gemini,claude,openai]
    make compare-providers NAME=2026-02-acme
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.ai import call_ai, prompt_hash, KEY_ENV, VALID_PROVIDERS
from lib.common import REPO_ROOT, load_meta

# ---------------------------------------------------------------------------
# Prompt (mirrors ai-tailor.py tailor_cv prompt)
# ---------------------------------------------------------------------------

_CV_PROMPT = """\
You are an expert career advisor specializing in Sales Engineering, \
Pre-Sales, and Technical Leadership roles.

I need you to tailor my resume YAML data for a specific job application.

### Target Job Posting
Content extracted from {job_url}:

{job_text}

### My Master Resume (YAML format)

```yaml
{cv_yaml}
```

### Instructions

1. **Analyze** the job description and identify the top 5-7 key requirements/skills.
2. **Rewrite** ONLY these sections to better align with the target role:
   - `profile`: Rewrite the summary to mirror the job's language. 3-4 sentences max.
   - `skills`: Reorder categories and adjust items. Add relevant keywords from the job posting.
   - `key_wins`: Rewrite titles and text to emphasize relevant achievements.
   - `experience[0].items` (the RVP role ONLY): Rewrite bullet labels and text to emphasize \
relevant accomplishments.
3. **Do NOT change**: `personal`, `experience[1:]` (past roles), `early_career`, `education`, \
`certifications`, `awards`, `publications`, `languages`, `interests`.
4. **Output format**: Return ONLY valid YAML with the exact same structure and keys as the input. \
No markdown fences, no comments, no explanations — just raw YAML.
5. **YAML rules**:
   - Use `>-` for multiline text (profile, key_wins text)
   - Use `**bold**` for emphasis (render.py converts this to LaTeX bold)
   - Never use LaTeX commands — this is YAML, not LaTeX
   - Do NOT escape special characters (& % $ #) — render.py handles escaping
6. **Tone**: Professional, leadership-focused, results-driven. Strong action verbs and metrics.
7. **Length constraint**: Keep content concise — the final PDF must fit on 2 pages."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_yaml(text: str) -> str:
    """Strip markdown fences and return clean YAML."""
    import re

    text = re.sub(r"```(?:yaml)?\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


def _keyword_overlap(yaml_text: str, job_text: str) -> float:
    """Simple word-level ATS overlap score (0-100)."""
    import re

    job_words = set(re.findall(r"\b[a-z]{4,}\b", job_text.lower()))
    cv_words = set(re.findall(r"\b[a-z]{4,}\b", yaml_text.lower()))
    if not job_words:
        return 0.0
    return round(len(job_words & cv_words) / len(job_words) * 100, 1)


def _profile_words(data: dict) -> int:
    profile = data.get("profile", "")
    return len(str(profile).split())


def _bullet_count(data: dict) -> int:
    exp = data.get("experience", [])
    if not exp:
        return 0
    return len(exp[0].get("items", []))


def _skill_keywords(data: dict) -> list[str]:
    skills = data.get("skills", [])
    kws = []
    for s in skills:
        items = s.get("items", "")
        kws += [k.strip() for k in str(items).split(",") if k.strip()]
    return kws[:8]


def _call_provider(provider: str, api_key: str | None, prompt: str) -> dict:
    """Call one provider and return result dict."""
    t0 = time.time()
    try:
        raw = call_ai(prompt, provider, api_key)
        yaml_text = _extract_yaml(raw)
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict) or "personal" not in data:
            raise ValueError("Invalid CV YAML structure")
        elapsed = round(time.time() - t0, 1)
        return {"provider": provider, "ok": True, "data": data, "yaml": yaml_text, "elapsed": elapsed, "error": None}
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        return {"provider": provider, "ok": False, "data": None, "yaml": "", "elapsed": elapsed, "error": str(e)}


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------


def compare(app_dir: Path, providers: list[str]) -> tuple[list[dict], str, str]:
    """Run all providers concurrently and return list of result dicts."""
    # Load inputs
    cv_path = REPO_ROOT / "data" / "cv.yml"
    if not cv_path.exists():
        print(f"❌ cv.yml not found: {cv_path}")
        sys.exit(1)
    cv_yaml = cv_path.read_text(encoding="utf-8")

    job_txt = app_dir / "job.txt"
    if not job_txt.exists():
        print(f"❌ job.txt not found: {job_txt}")
        sys.exit(1)
    job_text = job_txt.read_text(encoding="utf-8")

    job_url = ""
    job_url_file = app_dir / "job.url"
    if job_url_file.exists():
        job_url = job_url_file.read_text(encoding="utf-8").strip()

    prompt = _CV_PROMPT.format(cv_yaml=cv_yaml, job_text=job_text[:4000], job_url=job_url or "job.txt")
    phash = prompt_hash(prompt)
    print(f"📋 Prompt hash: {phash}  ({len(prompt):,} chars)")
    print(f"🔍 Running {len(providers)} provider(s): {', '.join(providers)}\n")

    results = []
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        futures = {}
        for p in providers:
            key_var = KEY_ENV.get(p)
            api_key = os.environ.get(key_var, "") if key_var else None
            futures[pool.submit(_call_provider, p, api_key, prompt)] = p

        for fut in as_completed(futures):
            r = fut.result()
            if r["ok"]:
                print(f"   ✅ {r['provider']:10s}  {r['elapsed']}s")
            else:
                print(f"   ❌ {r['provider']:10s}  {r['elapsed']}s  — {r['error'][:60]}")
            results.append(r)

    results.sort(key=lambda x: x["provider"])
    return results, job_text, phash


def print_comparison(results: list[dict], job_text: str) -> None:
    ok = [r for r in results if r["ok"]]
    if not ok:
        print("\n❌ All providers failed — nothing to compare.")
        return

    print("\n" + "═" * 72)
    print("📊 PROVIDER COMPARISON")
    print("═" * 72)

    # Header
    col = 14
    header = f"{'Metric':<22}" + "".join(f"{r['provider']:>{col}}" for r in ok)
    print(header)
    print("─" * len(header))

    # ATS overlap
    scores = [_keyword_overlap(r["yaml"], job_text) for r in ok]
    row = f"{'ATS overlap %':<22}" + "".join(f"{s:>{col}.1f}" for s in scores)
    print(row)

    # Profile word count
    row = f"{'Profile words':<22}" + "".join(f"{_profile_words(r['data']):>{col}}" for r in ok)
    print(row)

    # Experience bullet count (role 0)
    row = f"{'Exp[0] bullets':<22}" + "".join(f"{_bullet_count(r['data']):>{col}}" for r in ok)
    print(row)

    # Response time
    row = f"{'Response time (s)':<22}" + "".join(f"{r['elapsed']:>{col}.1f}" for r in ok)
    print(row)

    print("─" * len(header))

    # Profile preview (first 90 chars)
    print("\n📝 Profile previews:")
    for r in ok:
        profile = str(r["data"].get("profile", "")).replace("\n", " ")[:90]
        print(f"  {r['provider']:10s}  {profile}…")

    # Skills comparison
    print("\n🛠️  Top skills:")
    for r in ok:
        kws = _skill_keywords(r["data"])
        print(f"  {r['provider']:10s}  {', '.join(kws)}")

    # Winner by ATS score
    if len(ok) > 1:
        best = ok[scores.index(max(scores))]
        print(f"\n🏆 Highest ATS overlap: {best['provider']} ({max(scores):.1f}%)")

    print()


def save_report(app_dir: Path, results: list[dict], job_text: str, phash: str) -> Path:
    """Save compare-providers.md to the application directory."""
    from datetime import date

    ok = [r for r in results if r["ok"]]
    lines = [
        f"# Provider Comparison",
        f"",
        f"**Application:** {app_dir.name}  ",
        f"**Generated:** {date.today().isoformat()}  ",
        f"**Prompt hash:** `{phash}`  ",
        f"**Providers:** {', '.join(r['provider'] for r in results)}",
        "",
        "## Results",
        "",
        "| Provider | ATS % | Profile words | Bullets | Time (s) | Status |",
        "|----------|-------|---------------|---------|----------|--------|",
    ]
    for r in results:
        if r["ok"]:
            ats = _keyword_overlap(r["yaml"], job_text)
            pw = _profile_words(r["data"])
            bc = _bullet_count(r["data"])
            lines.append(f"| {r['provider']} | {ats:.1f}% | {pw} | {bc} | {r['elapsed']}s | ✅ |")
        else:
            lines.append(f"| {r['provider']} | — | — | — | {r['elapsed']}s | ❌ {r['error'][:40]} |")

    lines += ["", "## Profile Previews", ""]
    for r in ok:
        profile = str(r["data"].get("profile", "")).replace("\n", " ")
        lines += [f"### {r['provider']}", "", profile, ""]

    lines += ["## Skills Comparison", ""]
    for r in ok:
        kws = _skill_keywords(r["data"])
        lines += [f"**{r['provider']}:** {', '.join(kws)}", ""]

    out = app_dir / "compare-providers.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare AI provider outputs for the same tailoring job")
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument(
        "--providers",
        default=None,
        help="Comma-separated providers to test (default: all with API keys set)",
    )
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        return 1

    # Determine which providers have API keys configured
    if args.providers:
        providers = [p.strip() for p in args.providers.split(",") if p.strip() in VALID_PROVIDERS]
    else:
        providers = []
        for p in ("gemini", "claude", "openai", "mistral", "ollama"):
            key_var = KEY_ENV.get(p)
            if key_var is None or os.environ.get(key_var):
                providers.append(p)

    if not providers:
        print("❌ No providers configured. Set at least one API key:")
        for p, k in KEY_ENV.items():
            if k:
                print(f"   export {k}=your-key")
        return 1

    results, job_text, phash = compare(app_dir, providers)
    print_comparison(results, job_text)
    out = save_report(app_dir, results, job_text, phash)
    print(f"📄 Report saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
