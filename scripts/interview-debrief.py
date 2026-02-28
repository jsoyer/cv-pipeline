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
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT   = _SCRIPT_DIR.parent

GEMINI_MODEL    = "gemini-2.5-flash"
GEMINI_FALLBACK = "gemini-2.0-flash-lite"
CLAUDE_MODEL    = "claude-sonnet-4-6"
CLAUDE_FALLBACK = "claude-haiku-4-5-20251001"
OPENAI_MODEL    = "gpt-4o"
OPENAI_FALLBACK = "gpt-4o-mini"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
MISTRAL_MODEL    = "mistral-large-latest"
MISTRAL_FALLBACK = "mistral-small-latest"
MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"

VALID_PROVIDERS = {"gemini", "claude", "openai", "mistral", "ollama"}
KEY_ENV = {
    "gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY", "mistral": "MISTRAL_API_KEY", "ollama": None,
}


def call_gemini(prompt, api_key, retries=6):
    for model in (GEMINI_MODEL, GEMINI_FALLBACK):
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={api_key}")
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                               "generationConfig": {"temperature": 0.4, "maxOutputTokens": 3000}}).encode()
        for attempt in range(retries):
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(min(2 ** (attempt + 2), 60))
                elif e.code == 429 and model != GEMINI_FALLBACK:
                    break
                else:
                    raise
    raise RuntimeError("Gemini rate-limited")


def call_claude(prompt, api_key, retries=6):
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    for model in (CLAUDE_MODEL, CLAUDE_FALLBACK):
        payload = json.dumps({"model": model, "max_tokens": 3000,
                               "messages": [{"role": "user", "content": prompt}]}).encode()
        for attempt in range(retries):
            req = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())["content"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(min(2 ** (attempt + 2), 60))
                elif e.code == 429 and model != CLAUDE_FALLBACK:
                    break
                else:
                    raise
    raise RuntimeError("Claude rate-limited")


def call_openai_compat(prompt, endpoint, api_key, models, retries=6):
    primary, fallback = models
    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    for model in (primary, fallback):
        payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                               "max_tokens": 3000, "temperature": 0.4}).encode()
        for attempt in range(retries):
            req = urllib.request.Request(endpoint, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(min(2 ** (attempt + 2), 60))
                elif e.code == 429 and model != fallback:
                    break
                else:
                    raise
    raise RuntimeError("API rate-limited")


def call_ollama(prompt, retries=3):
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3")
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                           "stream": False}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(f"{host}/api/chat", data=payload,
                                      headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())["message"]["content"]
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                raise RuntimeError(f"Cannot connect to Ollama at {host}")


def call_ai(prompt, provider, api_key):
    if provider == "gemini":  return call_gemini(prompt, api_key)
    if provider == "claude":  return call_claude(prompt, api_key)
    if provider == "openai":  return call_openai_compat(prompt, OPENAI_ENDPOINT, api_key, (OPENAI_MODEL, OPENAI_FALLBACK))
    if provider == "mistral": return call_openai_compat(prompt, MISTRAL_ENDPOINT, api_key, (MISTRAL_MODEL, MISTRAL_FALLBACK))
    if provider == "ollama":  return call_ollama(prompt)
    raise ValueError(f"Unknown provider: {provider}")


def load_env():
    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _read(path: Path, max_chars: int = 2000) -> str:
    return path.read_text(encoding="utf-8")[:max_chars] if path.exists() else ""


PROMPT_TEMPLATE = """\
You are an executive coach debriefing a senior technology sales leader after a job interview. \
Be honest, constructive, and specific. Base your analysis on the interview notes provided.

## Candidate
Jérôme Soyer — Regional VP Sales Engineering, Varonis, Paris.

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
        app_dir = _REPO_ROOT / "applications" / Path(args.app_dir).name
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

    print(f"\n🔍 Generating debrief — {company} ({stage}) | AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        company=company,
        position=position,
        stage=stage,
        today=date.today().isoformat(),
        notes=notes[:3000],
        prep_excerpt=_read(app_dir / "prep.md", 1000) or "(no prep.md)",
        job_excerpt=_read(app_dir / "job.txt", 1000) or "(no job.txt)",
    )

    raw = call_ai(prompt, args.ai, api_key)

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
