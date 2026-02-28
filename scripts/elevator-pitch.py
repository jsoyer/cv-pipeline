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

CONTEXT_LABEL = {
    "recruiter":  "Recruiter / Phone Screen",
    "networking": "Networking Event / Conference",
    "interview":  "Job Interview Opening",
    "cold-call":  "Cold Outreach / LinkedIn DM",
}


def call_gemini(prompt, api_key, retries=6):
    for model in (GEMINI_MODEL, GEMINI_FALLBACK):
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={api_key}")
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                               "generationConfig": {"temperature": 0.6, "maxOutputTokens": 3000}}).encode()
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
                               "max_tokens": 3000, "temperature": 0.6}).encode()
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
            app_dir = _REPO_ROOT / "applications" / Path(args.app_dir).name
        app_name = app_dir.name if app_dir and app_dir.is_dir() else ""

    cv_src = (app_dir / "cv-tailored.yml" if app_dir and (app_dir / "cv-tailored.yml").exists()
              else _REPO_ROOT / "data" / "cv.yml")
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

    raw = call_ai(prompt, args.ai, api_key)

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
        out_path = _REPO_ROOT / "data" / "elevator-pitch.md"

    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print()
    print(raw.strip())
    print(f"\n✅ Saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
