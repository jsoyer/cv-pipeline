#!/usr/bin/env python3
"""
AI-powered post-interview debrief.

Analyses what went well, what to improve, difficult questions, red flags raised,
and recommends next steps.

Reads: meta.yml, prep.md, job.txt, milestones.yml
Input: --notes "free-form notes from the interview" (required or prompted)

Output: applications/NAME/debrief-STAGE-DATE.md

Usage:
    scripts/interview-debrief.py <app-dir> [--stage STAGE] [--notes "..."] [--ai PROVIDER]

AI providers: gemini (default) | claude | openai | mistral | ollama
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS
from lib.common import load_env, REPO_ROOT


def _read(path: Path, max_chars: int = 2000) -> str:
    return path.read_text(encoding="utf-8")[:max_chars] if path.exists() else ""


PROMPT_TEMPLATE = """\
You are an executive coach debriefing a senior technology sales leader after a job interview. \
Be honest, constructive, and specific. Base your analysis on the interview notes provided.

## Candidate
{candidate_name} — {candidate_position}.

## Interview Context
**Company:** {company}
**Role:** {position}
**Stage:** {stage}
**Date:** {today}

## Interview Notes (candidate's raw recap)
{notes}

## Prep Context (what was planned)
{prep_excerpt}

## Job Requirements
{job_excerpt}

## Task

Write a structured debrief using this exact format:

---

## ✅ What Went Well
3-4 bullet points. Be specific — reference moments from the notes.

## 🔧 What to Improve
3-4 bullet points. Each includes:
- What happened
- Why it matters
- One concrete fix for next time

## ❓ Hard Questions — Better Answers
For each difficult question mentioned in the notes:
- **Question:** [as asked]
- **What you said:** [brief summary]
- **Stronger answer:** [2-3 sentences — what to say next time]

## 🚩 Red Flags Raised
Any signals from the interviewer (or your own responses) that may concern the hiring team. \
Be honest. Include if none detected.

## 📊 Overall Read
- **Your confidence:** [High / Medium / Low] — [1 sentence why]
- **Their interest signals:** [Warm / Neutral / Cold] — [evidence from notes]
- **Likelihood of advancing:** [Strong / Moderate / Uncertain] — [brief rationale]

## ➡️ Recommended Next Steps
1. [Immediate — within 24h]
2. [This week]
3. [If you advance to next stage]

---
"""


def main():
    parser = argparse.ArgumentParser(description="Post-interview AI debrief")
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument("--stage", default="", help="Interview stage")
    parser.add_argument("--notes", default="",
                        help='Your interview notes (or omit to type interactively)')
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

    meta = {}
    if (app_dir / "meta.yml").exists():
        with open(app_dir / "meta.yml", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "the role")

    # Detect stage from milestones
    stage = args.stage
    if not stage:
        ms_path = app_dir / "milestones.yml"
        if ms_path.exists():
            with open(ms_path, encoding="utf-8") as f:
                ms = yaml.safe_load(f) or {}
            milestones = ms.get("milestones", [])
            if milestones:
                stage = milestones[-1].get("stage", "interview")
        stage = stage or "interview"

    # Get interview notes
    notes = args.notes.strip()
    if not notes:
        print(f"\n📝 Enter your interview notes for {company} ({stage}).")
        print("   Describe: questions asked, your answers, interviewer reactions, any concerns.")
        print("   Press Enter twice (blank line) when done.\n")
        lines_in = []
        try:
            while True:
                line = input()
                if line == "" and lines_in and lines_in[-1] == "":
                    break
                lines_in.append(line)
        except EOFError:
            pass
        notes = "\n".join(lines_in).strip()

    if not notes:
        print("❌ No notes provided — debrief requires interview notes.")
        sys.exit(1)

    cv_src = app_dir / "cv-tailored.yml"
    if not cv_src.exists():
        cv_src = REPO_ROOT / "data" / "cv.yml"
    candidate_name = "Candidate"
    candidate_position = ""
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            _cv = yaml.safe_load(f) or {}
        personal = _cv.get("personal", {})
        name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        if name:
            candidate_name = name
        candidate_position = personal.get("position", "")

    print(f"\n🔍 Generating debrief — {company} ({stage}) | AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        candidate_name=candidate_name,
        candidate_position=candidate_position,
        company=company,
        position=position,
        stage=stage,
        today=date.today().isoformat(),
        notes=notes[:3000],
        prep_excerpt=_read(app_dir / "prep.md", 1000) or "(no prep.md)",
        job_excerpt=_read(app_dir / "job.txt", 1000) or "(no job.txt)",
    )

    raw = call_ai(prompt, args.ai, api_key, max_tokens=3000)

    today_str = date.today().isoformat()
    out_name  = f"debrief-{stage}-{today_str}.md"
    lines = [
        f"# Interview Debrief — {company}",
        f"*{position} · Stage: {stage} · {today_str} · AI: {args.ai}*",
        "",
        "## Raw Notes",
        "",
        notes,
        "",
        "---",
        "",
        raw.strip(),
        "",
    ]
    out = app_dir / out_name
    out.write_text("\n".join(lines), encoding="utf-8")

    print(raw.strip())
    print(f"\n✅ Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
