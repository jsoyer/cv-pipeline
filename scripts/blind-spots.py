#!/usr/bin/env python3
"""
AI-powered blind spot analysis for a job application.

Identifies gaps, negative assumptions, and surprises that the candidate
is unlikely to think of themselves — things that will cost them the offer
if left unaddressed.

Unlike prep.md (what to say) or cover-critique.py (CL quality),
blind-spots.py focuses on what the hiring panel WORRIES about
that the candidate hasn't proactively addressed.

Reads: meta.yml, job.txt, cv-tailored.yml (fallback data/cv.yml),
       company-research.md, milestones.yml
Output: applications/NAME/blind-spots.md

Usage:
    scripts/blind-spots.py <app-dir> [--ai PROVIDER]

AI providers: gemini (default) | claude | openai | mistral | ollama
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
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


def _strip_bold(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


def _extract_cv_highlights(cv_data: dict) -> str:
    """Flatten key CV sections for context."""
    parts = []
    profile = cv_data.get("profile", "")
    if profile:
        parts.append(f"Profile: {_strip_bold(str(profile))[:400]}")

    for exp in cv_data.get("experience", [])[:2]:
        if isinstance(exp, dict):
            parts.append(
                f"Role: {exp.get('position','')} at {exp.get('company','')} "
                f"({exp.get('dates','')})"
            )

    wins = cv_data.get("key_wins", [])
    win_lines = []
    for w in wins[:4]:
        if isinstance(w, dict):
            win_lines.append(f"• {_strip_bold(w.get('title',''))}: {_strip_bold(w.get('text',''))}")
    if win_lines:
        parts.append("Key wins:\n" + "\n".join(win_lines))

    return "\n\n".join(parts)


def _detect_current_stage(app_dir: Path) -> str:
    ms_path = app_dir / "milestones.yml"
    if not ms_path.exists():
        return "applied"
    with open(ms_path, encoding="utf-8") as f:
        ms = yaml.safe_load(f) or {}
    milestones = ms.get("milestones", [])
    return milestones[-1].get("stage", "applied") if milestones else "applied"


PROMPT_TEMPLATE = """\
You are a brutally honest senior hiring manager reviewing a VP-level candidate.
Your job is to surface every concern, gap, and assumption that the candidate
is unlikely to think of themselves — the things that will lose them the offer
if left unaddressed.

Do NOT be encouraging. Do NOT soften feedback with "however, you also show great strength in...".
Be specific: reference exact phrases from the job description that map poorly to the CV.
Every point must be actionable — tell the candidate what to say or do, not just what's wrong.

## Candidate
Jérôme Soyer — {position} applicant at {company}.
Current stage: {stage}

## CV Highlights
{cv_highlights}

## Job Description
{job_excerpt}

## Company Context
{research_excerpt}

---

Write a blind spot analysis using this exact format:

## 🚧 Requirements You Haven't Addressed

For each requirement in the job description that the CV does NOT clearly cover:
- **Requirement:** [exact phrase from JD]
- **The gap:** [why your background doesn't obviously map to it]
- **What to say:** [1–2 sentences to proactively address it in an interview or cover letter]

List 4–6 items, ordered by severity.

---

## 🧠 Negative Assumptions the Panel Will Make

Things the hiring team will assume or worry about based on your background,
even if they never say it out loud. These are the silent objections.

For each:
- **Assumption:** [what they'll think]
- **Trigger:** [what in your CV causes it]
- **Counter:** [how to pre-empt it in 1 sentence]

List 3–5 items.

---

## ❓ Questions You'll Be Surprised By

Questions the interviewer WILL ask that you haven't prepared for —
because they target a specific gap or test an assumption about you.

For each:
- **Question:** "..."
- **Why they'll ask it:** [what concern it probes]
- **Preparation note:** [what your answer must demonstrate]

List 3–5 questions.

---

## 🏢 Culture & Fit Red Flags

Based on the company context and job description, list any signals that
your background or style might clash with their culture or expectations.
Include: pace mismatch, org size mismatch, leadership style assumptions,
industry background gaps.

2–4 bullets.

---

## 🎯 Top 3 Things to Fix Before the Next Interview

Ranked by likelihood of killing your candidacy:
1. [Most critical]
2. [Second]
3. [Third]

---
"""


def main():
    parser = argparse.ArgumentParser(description="AI blind spot analysis for a job application")
    parser.add_argument("app_dir", help="Application directory")
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
    stage    = _detect_current_stage(app_dir)

    cv_src = app_dir / "cv-tailored.yml"
    if not cv_src.exists():
        cv_src = _REPO_ROOT / "data" / "cv.yml"
    cv_data = {}
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}

    cv_highlights   = _extract_cv_highlights(cv_data)
    job_excerpt     = _read(app_dir / "job.txt", 2000) or "(no job.txt — analysis will be generic)"
    research_excerpt = _read(app_dir / "company-research.md", 1000) or "(no company-research.md)"

    print(f"🔍 Analysing blind spots — {company} ({position})")
    print(f"   Stage: {stage} | AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        company=company,
        position=position,
        stage=stage,
        cv_highlights=cv_highlights,
        job_excerpt=job_excerpt,
        research_excerpt=research_excerpt,
    )

    raw = call_ai(prompt, args.ai, api_key)

    from datetime import date
    today = date.today().isoformat()

    lines = [
        f"# Blind Spot Analysis — {company}",
        f"*{position} · Stage: {stage} · {today} · AI: {args.ai}*",
        "",
        "> This document is intentionally harsh. Use it to prepare, not to discourage.",
        "",
        raw.strip(),
        "",
    ]
    out = app_dir / "blind-spots.md"
    out.write_text("\n".join(lines), encoding="utf-8")

    print()
    print(raw.strip())
    print(f"\n✅ Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
