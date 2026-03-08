#!/usr/bin/env python3
"""
AI-powered salary benchmarking and negotiation strategy.

Estimates market salary range (P25/P50/P75) for the target role and location,
then generates a personalised negotiation strategy.

Reads: meta.yml, job.txt, data/preferences.yml (salary target)
Output: applications/NAME/salary-bench.md

Usage:
    scripts/salary-bench.py <app-dir> [--ai PROVIDER]

AI providers: gemini (default) | claude | openai | mistral | ollama

Note: AI salary data reflects training knowledge — cross-check with
      Glassdoor, LinkedIn Salary, Levels.fyi, and PayScale.
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS
from lib.common import load_env, REPO_ROOT


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def _read_file(path: Path, max_chars: int = 3000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:max_chars]


def _load_preferences() -> dict:
    prefs_path = REPO_ROOT / "data" / "preferences.yml"
    if not prefs_path.exists():
        return {}
    with open(prefs_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are a compensation expert and career strategist specialising in senior technology \
sales leadership roles in France and Europe.

## Candidate Profile
- **Name:** {candidate_name}
- **Current role:** {candidate_position}
- **Location:** {candidate_location}
{candidate_profile}

## Target Role
- **Company:** {company}
- **Position:** {position}
- **Location hint from job:** {job_location}
{salary_target_section}

## Job Posting Excerpt
{job_excerpt}
{research_excerpt}

## Task

Produce a structured salary benchmark and negotiation strategy. Use the format below exactly.

---

## Market Range Estimate
*(Annual gross, all-in base salary — EUR unless otherwise noted)*

| Percentile | Range |
|------------|-------|
| P25 (low)  | €X – €Y |
| P50 (median)| €X – €Y |
| P75 (high) | €X – €Y |

**Recommended ask:** €X (explain why — based on experience level, market, company stage)

*Sources to verify: Glassdoor, LinkedIn Salary, Welcome to the Jungle, Levels.fyi*

## Total Compensation Components
List the components beyond base salary that are typical for this role/company type:
- Variable / OTE (target % of base)
- Equity (RSUs, BSPCE, stock options — typical vesting schedule)
- Signing bonus
- Benefits (meal vouchers, transport, health, remote allowance)
- Notice period / garden leave implications

## Leverage Points
What strengthens the candidate's negotiating position specifically for this role? List 4-5 concrete points.

## Negotiation Strategy
Step-by-step approach:
1. When to raise compensation (which interview stage)
2. How to anchor the ask without anchoring too low
3. What to say if they push back
4. What to counter-offer if first offer is below target
5. What non-cash items to negotiate if cash is fixed

## French Market Specifics
Key considerations for negotiating in the French market:
- Timing (avoid August, end of year budget cycles)
- Legal / contractual points to watch (forfait jours, non-compete, BSPCE tax)
- Cultural norms (direct vs indirect ask, written vs verbal)

## Red Flags in the Offer
Signs that would warrant re-negotiation or walking away.

---

Be specific and practical. State clearly if any data is uncertain due to limited \
public information about this company's compensation.
"""


def _extract_location(job_text: str) -> str:
    """Try to extract location from job text."""
    import re
    for pattern in (
        r"Location[:\s]+([^\n]+)",
        r"Based in[:\s]+([^\n]+)",
        r"Office[:\s]+([^\n,]+)",
    ):
        m = re.search(pattern, job_text, re.I)
        if m:
            return m.group(1).strip()[:60]
    return "France / Europe (assumed)"


def build_prompt(meta: dict, prefs: dict, job_text: str, research_text: str,
                 cv_data: dict | None = None) -> str:
    company  = meta.get("company", "the company")
    position = meta.get("position", "the role")
    location = _extract_location(job_text)

    personal = (cv_data or {}).get("personal", {})
    candidate_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip() or "Candidate"
    candidate_position = personal.get("position", "")
    candidate_location = personal.get("address", "")
    profile = (cv_data or {}).get("profile", "")
    candidate_profile = f"- **Profile:** {profile[:300]}" if profile else ""

    salary_section = ""
    sal = prefs.get("salary", {})
    if sal.get("min"):
        currency = sal.get("currency", "EUR")
        salary_section = (
            f"- **Candidate salary target:** ≥ {sal['min']:,} {currency} base\n"
        )

    return PROMPT_TEMPLATE.format(
        candidate_name=candidate_name,
        candidate_position=candidate_position,
        candidate_location=candidate_location,
        candidate_profile=candidate_profile,
        company=company,
        position=position,
        job_location=location,
        salary_target_section=salary_section,
        job_excerpt=job_text[:2000] if job_text else "(no job.txt available)",
        research_excerpt=(
            f"\n## Company Research\n{research_text[:1000]}\n"
            if research_text else ""
        ),
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_output(app_dir: Path, meta: dict, raw_output: str, provider: str) -> Path:
    from datetime import date
    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    today    = date.today().isoformat()

    lines = [
        f"# Salary Benchmark — {company}",
        f"*{position} · Generated: {today} · AI: {provider}*",
        "",
        "> ⚠️ AI-generated estimates — always verify with Glassdoor, LinkedIn Salary, "
        "Welcome to the Jungle, and direct market sources.",
        "",
        "---",
        "",
        raw_output.strip(),
        "",
    ]

    out_path = app_dir / "salary-bench.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AI-powered salary benchmarking and negotiation strategy"
    )
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument(
        "--ai", default="gemini",
        choices=sorted(VALID_PROVIDERS),
        help="AI provider (default: gemini)"
    )
    args = parser.parse_args()

    load_env()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set — add it to .env or export it")
        sys.exit(1)

    meta_path = app_dir / "meta.yml"
    meta = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    prefs    = _load_preferences()

    cv_src = app_dir / "cv-tailored.yml"
    if not cv_src.exists():
        cv_src = REPO_ROOT / "data" / "cv.yml"
    cv_data = {}
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}

    job_text      = _read_file(app_dir / "job.txt")
    research_text = _read_file(app_dir / "company-research.md")

    print(f"💰 Salary benchmarking — {company}")
    print(f"   Position: {position}")
    print(f"   AI: {args.ai}...")
    print()

    prompt     = build_prompt(meta, prefs, job_text, research_text, cv_data=cv_data)
    raw_output = call_ai(prompt, args.ai, api_key)

    out_path = save_output(app_dir, meta, raw_output, args.ai)

    print(raw_output.strip())
    print(f"\n✅ Saved to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
