#!/usr/bin/env python3
"""
Generate a concise interview-day brief from all available context.

A single-page cheat sheet to review the morning of the interview:
  - Company snapshot (key facts, recent news)
  - Role summary (what they're looking for)
  - Your top 3 talking points aligned to the JD
  - 3 STAR stories to have ready
  - Questions to ask (from prep.md if available)
  - Potential gaps to address proactively
  - Logistics reminder block

Reads: meta.yml, job.txt, company-research.md, prep.md, competitors.md,
       cv-tailored.yml (fallback data/cv.yml), milestones.yml

Output: applications/NAME/interview-brief.md

Usage:
    scripts/interview-brief.py <app-dir> [--stage STAGE] [--ai PROVIDER]

Stages: phone-screen | technical | panel | final (default: auto-detect from milestones)
AI providers: gemini (default) | claude | openai | mistral | ollama
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS
from lib.common import load_env, REPO_ROOT


def _read(path: Path, max_chars: int = 3000) -> str:
    return path.read_text(encoding="utf-8")[:max_chars] if path.exists() else ""


def _detect_stage(app_dir: Path) -> str:
    ms_path = app_dir / "milestones.yml"
    if not ms_path.exists():
        return "phone-screen"
    with open(ms_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    milestones = data.get("milestones", [])
    if not milestones:
        return "phone-screen"
    last = milestones[-1].get("stage", "phone-screen")
    stage_next = {
        "phone-screen":    "technical",
        "technical":       "panel",
        "panel":           "final",
        "final":           "final",
        "reference-check": "offer",
    }
    return stage_next.get(last, "technical")


PROMPT_TEMPLATE = """\
You are an executive coach preparing a senior technology sales leader for a job interview. \
Create a tight, scannable one-page brief to review in the 30 minutes before the interview.

## Candidate
{candidate_name} — {candidate_position}.
{profile_excerpt}

## Target
**Company:** {company}
**Role:** {position}
**Interview stage:** {stage}

## Available Context

**Job description:**
{job_excerpt}

**Company research:**
{research_excerpt}

**Prep notes:**
{prep_excerpt}

**CV profile:**
{profile_excerpt}

## Task

Write the interview brief in this exact structure. Be specific — no generic advice. \
Every point should reference {company} or the {position} role directly.

---

## 🏢 Company Snapshot
5 bullet points — key facts an interviewer would expect you to know:
- Founded / HQ / size / stage (public/private/PE-backed)
- Core product and primary buyer
- Recent news, funding, or strategic move
- Main competitors (1 line)
- Why they're hiring for this role right now

## 🎯 What They're Looking For
3 bullet points — the must-haves from the JD, framed as "They need someone who..."

## 💬 Your Top 3 Talking Points
For each: one sentence positioning + one supporting data point from your CV.
Directly tied to the role requirements.

## ⭐ 3 STAR Stories to Have Ready
For each story:
- **Trigger question:** "Tell me about a time when..."
- **S:** (1 sentence)
- **T:** (1 sentence)
- **A:** (2 sentences — what YOU specifically did)
- **R:** quantified outcome

## ❓ 3 Questions to Ask
Sharp, informed questions that show you've done your homework on {company}.
Not generic "what does success look like" — something specific to their context.

## ⚠️ Potential Gap to Address
One likely concern they may have about your profile — and your 1-sentence reframe.

## 📋 Logistics Checklist
- [ ] Interviewer name(s): ___
- [ ] Format: [ ] Video  [ ] Phone  [ ] On-site
- [ ] Time: ___
- [ ] Materials to have open: CV, this brief, LinkedIn of interviewers
- [ ] Send thank-you within 24h

---

Keep it tight. Each section should be scannable in under 60 seconds.
"""


def main():
    parser = argparse.ArgumentParser(description="Generate interview-day brief")
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument("--stage", default="", help="Interview stage (auto-detected if omitted)")
    parser.add_argument("--ai", default="gemini", choices=sorted(VALID_PROVIDERS))
    args = parser.parse_args()

    load_env()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        app_dir = REPO_ROOT / "applications" / Path(args.app_dir).name
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {args.app_dir}")
        sys.exit(1)

    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set")
        sys.exit(1)

    with open(app_dir / "meta.yml", encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {} if (app_dir / "meta.yml").exists() else {}
    meta = meta if (app_dir / "meta.yml").exists() else {}
    if (app_dir / "meta.yml").exists():
        with open(app_dir / "meta.yml", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "the role")
    stage    = args.stage or _detect_stage(app_dir)

    cv_src = app_dir / "cv-tailored.yml"
    if not cv_src.exists():
        cv_src = REPO_ROOT / "data" / "cv.yml"
    profile_excerpt = ""
    cv_data = {}
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}
        profile = cv_data.get("profile", "")
        profile_excerpt = re.sub(r"\*\*(.+?)\*\*", r"\1",
                                  profile if isinstance(profile, str) else "")[:600]

    personal = cv_data.get("personal", {})
    candidate_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip() or "Candidate"
    candidate_position = personal.get("position", "")

    print(f"📋 Generating interview brief — {company}")
    print(f"   Stage: {stage} | AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        candidate_name=candidate_name,
        candidate_position=candidate_position,
        company=company,
        position=position,
        stage=stage,
        job_excerpt=_read(app_dir / "job.txt", 2000) or "(no job.txt)",
        research_excerpt=_read(app_dir / "company-research.md", 1500) or "(no research)",
        prep_excerpt=_read(app_dir / "prep.md", 1500) or "(no prep.md — run make prep first)",
        profile_excerpt=profile_excerpt or "(no CV loaded)",
    )

    raw = call_ai(prompt, args.ai, api_key, temperature=0.3)

    from datetime import date
    lines = [
        f"# Interview Brief — {company}",
        f"*{position} · Stage: {stage} · {date.today().isoformat()} · AI: {args.ai}*",
        "", "---", "", raw.strip(), "",
    ]
    out = app_dir / "interview-brief.md"
    out.write_text("\n".join(lines), encoding="utf-8")

    print(raw.strip())
    print(f"\n✅ Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
