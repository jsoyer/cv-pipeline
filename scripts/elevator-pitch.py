#!/usr/bin/env python3
"""
Generate elevator pitches (30s / 60s / 90s) using AI.

Produces three timed versions of your personal pitch, each with a delivery
coach note and context-specific variant.

Reads: data/cv.yml (or cv-tailored.yml if app-dir provided), meta.yml
Output: data/elevator-pitch.md (or applications/NAME/elevator-pitch.md)

Usage:
    scripts/elevator-pitch.py [<app-dir>] [--context recruiter|networking|interview|cold-call] [--ai PROVIDER]

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

CONTEXT_LABEL = {
    "recruiter":  "Recruiter / Phone Screen",
    "networking": "Networking Event / Conference",
    "interview":  "Job Interview Opening",
    "cold-call":  "Cold Outreach / LinkedIn DM",
}


def _strip_bold(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


PROMPT_TEMPLATE = """\
You are an executive coach writing elevator pitches for a senior technology sales leader.
Write in first person, direct and confident — no "I'm passionate about", no "leveraging", no buzzwords.

## About
Jérôme Soyer — Regional VP of Sales Engineering at Varonis, Paris.
15+ years in technology sales and SE leadership. Scaled SE teams to 50+ people.
Expert in cybersecurity, data security, SaaS enterprise sales. Drives ARR growth.
French native, fluent English. Based in Paris.

## CV Profile
{profile}

## Key Achievements
{achievements}

## Target Context
{context_label}
{role_context}

## Task

Write THREE elevator pitches:

---30---
**30-Second Pitch** (~75 words spoken at natural pace)
- Opens with a value statement, not a job title
- States who you help and how
- Includes ONE specific quantified result
- Ends with a natural transition or question
[pitch text]
**Coach note:** [1 sentence on delivery or tone for this context]

---60---
**60-Second Pitch** (~150 words)
- Stronger opener — bold claim or surprising fact
- 2 achievements with numbers
- What you're looking for / why now
- Clear call to action
[pitch text]
**Coach note:** [1 sentence on delivery or tone for this context]

---90---
**90-Second Pitch** (~225 words)
- Full narrative arc: where you've been → what you built → where you're going
- 3 specific wins with metrics
- Differentiator (what makes you different from other VP SE candidates)
- Concrete ask or CTA
[pitch text]
**Coach note:** [1 sentence on delivery or tone for this context]

Rules:
- Never start with "I'm a..." — start with a value proposition or insight
- No "I'm excited to...", no "passionate", no "thrilled"
- Use present tense for current role, past tense for achievements
- Each pitch should be deliverable verbatim — natural spoken English
"""


def main():
    parser = argparse.ArgumentParser(description="Generate elevator pitches using AI")
    parser.add_argument("app_dir", nargs="?", default="",
                        help="Application directory (optional)")
    parser.add_argument("--context", default="networking",
                        choices=list(CONTEXT_LABEL),
                        help="Delivery context (default: networking)")
    parser.add_argument("--ai", default="gemini", choices=sorted(VALID_PROVIDERS))
    args = parser.parse_args()

    load_env()

    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set")
        sys.exit(1)

    app_dir = None
    app_name = ""
    if args.app_dir:
        app_dir = Path(args.app_dir)
        if not app_dir.is_dir():
            app_dir = REPO_ROOT / "applications" / Path(args.app_dir).name
        app_name = app_dir.name if app_dir and app_dir.is_dir() else ""

    cv_src = (app_dir / "cv-tailored.yml" if app_dir and (app_dir / "cv-tailored.yml").exists()
              else REPO_ROOT / "data" / "cv.yml")
    cv_data = {}
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}

    profile = _strip_bold(cv_data.get("profile", ""))[:600]

    wins = cv_data.get("key_wins", [])
    ach_lines = []
    for w in wins[:5]:
        if isinstance(w, dict):
            ach_lines.append(f"• {_strip_bold(w.get('title',''))}: {_strip_bold(w.get('text',''))}")
    achievements = "\n".join(ach_lines) or "(no key_wins found)"

    role_context = ""
    if app_dir and app_dir.is_dir() and (app_dir / "meta.yml").exists():
        with open(app_dir / "meta.yml", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        company  = meta.get("company", "")
        position = meta.get("position", "")
        if company or position:
            role_context = f"Targeting: {position} at {company}"

    context_label = CONTEXT_LABEL[args.context]
    print(f"🎤 Generating elevator pitches — {context_label}")
    if app_name:
        print(f"   Context: {app_name}")
    print(f"   AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        profile=profile,
        achievements=achievements,
        context_label=context_label,
        role_context=role_context,
    )

    raw = call_ai(prompt, args.ai, api_key, temperature=0.6, max_tokens=3000)

    from datetime import date
    today = date.today().isoformat()

    out_lines = [
        f"# Elevator Pitches — {context_label}",
        f"*Generated: {today} · AI: {args.ai}{' · ' + app_name if app_name else ''}*",
        "",
        raw.strip(),
        "",
        "---",
        "## Delivery Tips",
        "",
        "- Practice aloud until it sounds natural, not rehearsed",
        "- Record yourself once — check pace, filler words, energy",
        "- Have a 1-sentence teaser ready if interrupted: *'I run SE teams for enterprise cybersecurity companies.'*",
        "- End every version with a question to keep the conversation going",
        "",
    ]

    if app_dir and app_dir.is_dir():
        out_path = app_dir / "elevator-pitch.md"
    else:
        out_path = REPO_ROOT / "data" / "elevator-pitch.md"

    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print()
    print(raw.strip())
    print(f"\n✅ Saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
