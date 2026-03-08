#!/usr/bin/env python3
"""
Generate a competitor landscape map for a target company using AI.

Identifies main competitors, market positioning, differentiators,
and "why this company over others" talking points for interviews.

Reads: meta.yml, job.txt, company-research.md (optional)
Output: applications/NAME/competitors.md

Usage:
    scripts/competitor-map.py <app-dir> [--ai PROVIDER]

AI providers: gemini (default) | claude | openai | mistral | ollama
"""

import argparse
import os
import sys
from pathlib import Path

from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS
from lib.common import load_env, REPO_ROOT, require_yaml

yaml = require_yaml()


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def _read_file(path: Path, max_chars: int = 3000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:max_chars]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are a competitive intelligence analyst helping a senior technology sales leader \
prepare for interviews and sales conversations.

## Context

**Target company:** {company}
**Role applied for:** {position}
**Candidate:** Jérôme Soyer — Regional VP of Sales Engineering at Varonis. \
Expert in cybersecurity, data security, SaaS, SE team leadership.

**Job posting excerpt:**
{job_excerpt}
{research_excerpt}

## Task

Produce a competitive landscape analysis for **{company}** in the context of the \
**{position}** role. Structure your response exactly as follows:

---

## Market Position
(2-3 sentences on where {company} sits in its market: category leader, challenger, niche, etc.)

## Main Competitors
For each competitor (list 4-6), provide:
- **Competitor name** — one sentence on what they do and why they're a threat/comparison
  - {company} advantage: [specific differentiator]
  - Weakness vs competitor: [honest gap, if any]

## Why {company}?
5 specific, factual reasons a senior leader would choose {company} over competitors. \
Reference products, culture, growth trajectory, mission, or market dynamics. \
Be concrete — no generic "innovative culture" statements.

## Interview Talking Points
3 bullet points Jérôme can use to demonstrate he understands {company}'s competitive \
position and has done his homework. Each should start with a specific fact or observation.

## Mermaid Diagram
A Mermaid graph showing {company} at centre with competitors around it, and \
one-word edge labels (e.g. "Data", "SIEM", "Cloud"):
```mermaid
graph TD
    ...
```

---

Keep the tone analytical and direct. No filler. Use your training data for company facts; \
note if information may be outdated.
"""


def build_prompt(meta: dict, job_text: str, research_text: str) -> str:
    company  = meta.get("company", "the company")
    position = meta.get("position", "the role")

    return PROMPT_TEMPLATE.format(
        company=company,
        position=position,
        job_excerpt=job_text[:2000] if job_text else "(no job.txt available)",
        research_excerpt=(
            f"\n**Company research:**\n{research_text[:1500]}\n"
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
        f"# Competitor Map — {company}",
        f"*{position} · Generated: {today} · AI: {provider}*",
        "",
        "> ⚠️ AI-generated analysis — verify facts against recent sources.",
        "",
        "---",
        "",
        raw_output.strip(),
        "",
    ]

    out_path = app_dir / "competitors.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate competitor landscape map for a target company"
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

    job_text      = _read_file(app_dir / "job.txt")
    research_text = _read_file(app_dir / "company-research.md")

    print(f"🗺️  Mapping competitors — {company}")
    print(f"   Position: {position}")
    print(f"   AI: {args.ai}...")
    print()

    prompt     = build_prompt(meta, job_text, research_text)
    raw_output = call_ai(prompt, args.ai, api_key)

    out_path = save_output(app_dir, meta, raw_output, args.ai)

    print(raw_output.strip())
    print(f"\n✅ Saved to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
