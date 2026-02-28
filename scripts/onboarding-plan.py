#!/usr/bin/env python3
"""
Generate a 30/60/90-day onboarding plan using AI.

Once you've accepted an offer, this helps you plan your first 90 days:
quick wins, stakeholder mapping, team assessment, key milestones.

Reads: meta.yml, job.txt, cv-tailored.yml (fallback data/cv.yml), company-research.md
Output: applications/NAME/onboarding-plan.md

Usage:
    scripts/onboarding-plan.py <app-dir> [--ai PROVIDER]

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
                               "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4000}}).encode()
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
        payload = json.dumps({"model": model, "max_tokens": 4000,
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
                               "max_tokens": 4000, "temperature": 0.4}).encode()
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


PROMPT_TEMPLATE = """\
You are an executive coach helping a newly hired senior technology sales leader plan their \
first 90 days. Be specific, practical, and role-aware. Base every recommendation on \
the job description and company context provided.

## Candidate
Jérôme Soyer — incoming {position} at {company}.
Background: 15+ years in technology sales and SE leadership, cybersecurity/data/SaaS.
Previously scaled SE organisations to 50+ HC. Expert in ARR growth, M&A integration.

## Job Description
{job_excerpt}

## Company Context
{research_excerpt}

## Task

Write a structured 30/60/90-day onboarding plan using this exact format:

---

## Week 1 — Quick Wins Checklist
A practical day-by-day checklist for the first week. Focus on:
- People to meet immediately (categories: direct reports, peers, key stakeholders, sponsor)
- Systems and tools to get access to
- Documents to read (strategy, pipeline reports, team structure)
- One visible early action that signals your leadership style

---

## Days 1–30: Listen & Learn
**Theme:** Build credibility through curiosity, not action.

### Goals
3 bullet points — what success looks like at 30 days

### Key Actions
5–7 specific actions (who to meet, what to assess, what to avoid)

### Success Metrics
How will you and your manager know you're on track?

### Watch Out For
2–3 common onboarding traps for senior hires at this level

---

## Days 31–60: Contribute & Build
**Theme:** Start shaping the agenda with informed opinions.

### Goals
### Key Actions
### Success Metrics

---

## Days 61–90: Drive & Deliver
**Theme:** Execute on your first initiative and establish your cadence.

### Goals
### Key Actions
### Success Metrics

---

## Stakeholder Map Template
A table of key relationships to build:

| Name/Role | Relationship Type | Priority | Goal |
|-----------|------------------|----------|------|
| [Direct reports] | Manage | High | Individual assessment |
| [Peers: VP Sales, VP Marketing, etc.] | Peer | High | Alignment |
| [Skip-level: CRO / CPO] | Upward | Medium | Visibility |
| [Key customers] | External | Medium | Credibility |

Fill in with role-specific names/titles from the job description context.

---

## 90-Day Milestone Summary

| Day | Milestone |
|-----|-----------|
| 7   | |
| 30  | |
| 60  | |
| 90  | |

---
"""


def main():
    parser = argparse.ArgumentParser(description="Generate 30/60/90-day onboarding plan")
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

    job_excerpt     = _read(app_dir / "job.txt", 2000) or "(no job.txt)"
    research_excerpt = _read(app_dir / "company-research.md", 1500) or "(no company-research.md)"

    print(f"🗓️  Generating 30/60/90-day onboarding plan — {company}")
    print(f"   Position: {position} | AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        company=company,
        position=position,
        job_excerpt=job_excerpt,
        research_excerpt=research_excerpt,
    )

    raw = call_ai(prompt, args.ai, api_key)

    from datetime import date
    today = date.today().isoformat()

    lines = [
        f"# 30/60/90-Day Onboarding Plan — {company}",
        f"*{position} · Generated: {today} · AI: {args.ai}*",
        "",
        "> **Note:** Adapt dates to your actual start date. Review with your manager at day 30.",
        "",
        raw.strip(),
        "",
    ]
    out = app_dir / "onboarding-plan.md"
    out.write_text("\n".join(lines), encoding="utf-8")

    print(raw.strip())
    print(f"\n✅ Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
