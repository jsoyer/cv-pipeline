#!/usr/bin/env python3
"""
Generate structured STAR stories from CV achievements using AI.

Maps key_wins and top experience items to common behavioral interview questions,
producing 5-7 ready-to-use STAR stories with S/T/A/R breakdown.

Reads: cv-tailored.yml (fallback data/cv.yml), job.txt (for question mapping)
Output: applications/NAME/star-stories.md

Usage:
    scripts/prep-star.py <app-dir> [--count N] [--ai PROVIDER]

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
                               "generationConfig": {"temperature": 0.4, "maxOutputTokens": 5000}}).encode()
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
        payload = json.dumps({"model": model, "max_tokens": 5000,
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
                               "max_tokens": 5000, "temperature": 0.4}).encode()
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


def _strip_bold(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


def _flatten_items(items: list) -> list[str]:
    out = []
    for item in items or []:
        if isinstance(item, str):
            out.append(_strip_bold(item))
        elif isinstance(item, dict):
            label = item.get("label", "")
            text  = item.get("text", "")
            out.append(_strip_bold(f"{label}: {text}" if label else text))
    return out


def extract_achievements(cv_data: dict) -> str:
    lines = []
    for win in cv_data.get("key_wins", []):
        if isinstance(win, dict):
            lines.append(f"• {_strip_bold(win.get('title',''))}: {_strip_bold(win.get('text',''))}")

    for exp in cv_data.get("experience", [])[:2]:
        company = exp.get("company", "")
        role    = exp.get("position", "")
        for item in _flatten_items(exp.get("items", []))[:4]:
            lines.append(f"• [{role} @ {company}] {item}")

    return "\n".join(lines[:15])


PROMPT_TEMPLATE = """\
You are an executive coach preparing a senior technology sales leader for behavioral interviews. \
Turn the CV achievements below into structured STAR stories, each mapped to a specific \
behavioral question.

## Candidate
Jérôme Soyer — Regional VP of Sales Engineering at Varonis, Paris.
Expert in scaling SE organisations (50+ HC), driving ARR growth, M&A integration, \
cybersecurity/data/SaaS.

## CV Achievements
{achievements}

## Target Role Context
{job_excerpt}

## Task

Write {count} STAR stories. Each must:
1. Be grounded in the CV achievements above — no invented facts
2. Be mapped to a specific behavioral question
3. Have a quantified Result
4. Be deliverable in 2-3 minutes when spoken

Use this exact format for each story:

---

### Story N — [Story Title]

**Behavioral question:** "Tell me about a time when [...]"
**Also works for:** "[Alternative question]"

| | |
|---|---|
| **Situation** | [1-2 sentences: context, company, timing] |
| **Task** | [1 sentence: what was required of you specifically] |
| **Action** | [3-4 sentences: what YOU did — use "I", not "we"] |
| **Result** | [1-2 sentences: quantified outcome + business impact] |

**Key message:** [The one takeaway the interviewer should remember]

---

Cover these behavioral themes across the {count} stories (not all in one story):
- Leading & scaling a team
- Driving revenue / ARR growth
- Managing a difficult stakeholder or internal conflict
- Delivering under pressure / tight deadline
- Strategic decision with incomplete information
- Cross-functional or M&A integration
- Coaching / developing a team member

Only use themes for which there is clear evidence in the CV achievements.
"""


def main():
    parser = argparse.ArgumentParser(description="Generate STAR stories from CV achievements")
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument("--count", type=int, default=5, help="Number of stories (default: 5)")
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

    cv_src = app_dir / "cv-tailored.yml"
    if not cv_src.exists():
        cv_src = _REPO_ROOT / "data" / "cv.yml"
    with open(cv_src, encoding="utf-8") as f:
        cv_data = yaml.safe_load(f) or {}

    achievements = extract_achievements(cv_data)

    job_txt = app_dir / "job.txt"
    job_excerpt = job_txt.read_text(encoding="utf-8")[:1500] if job_txt.exists() else "(no job.txt)"

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")

    print(f"⭐ Generating {args.count} STAR stories — {company}")
    print(f"   Position: {position} | AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        achievements=achievements,
        job_excerpt=job_excerpt,
        count=args.count,
    )

    raw = call_ai(prompt, args.ai, api_key)

    from datetime import date
    lines = [
        f"# STAR Stories — {company}",
        f"*{position} · {args.count} stories · {date.today().isoformat()} · AI: {args.ai}*",
        "",
        "> Practice each story aloud — aim for 2 min each. Adjust numbers to match real data.",
        "", "---", "", raw.strip(), "",
        "---",
        "## Quick Reference",
        "",
        "| Story | Theme | Key metric |",
        "|-------|-------|------------|",
        "*(fill in after reviewing above)*",
        "",
    ]
    out = app_dir / "star-stories.md"
    out.write_text("\n".join(lines), encoding="utf-8")

    print(raw.strip())
    print(f"\n✅ Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
