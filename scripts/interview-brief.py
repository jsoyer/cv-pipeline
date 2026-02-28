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
                               "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096}}).encode()
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
        payload = json.dumps({"model": model, "max_tokens": 4096,
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
                               "max_tokens": 4096, "temperature": 0.3}).encode()
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
Jérôme Soyer — Regional VP of Sales Engineering at Varonis, Paris.
Expert in scaling SE organisations (50+ HC), driving ARR growth, M&A integration, \
cybersecurity/data/SaaS. French native, fluent English.

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
        app_dir = _REPO_ROOT / "applications" / Path(args.app_dir).name
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
        cv_src = _REPO_ROOT / "data" / "cv.yml"
    profile_excerpt = ""
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}
        profile = cv_data.get("profile", "")
        profile_excerpt = re.sub(r"\*\*(.+?)\*\*", r"\1",
                                  profile if isinstance(profile, str) else "")[:600]

    print(f"📋 Generating interview brief — {company}")
    print(f"   Stage: {stage} | AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        company=company,
        position=position,
        stage=stage,
        job_excerpt=_read(app_dir / "job.txt", 2000) or "(no job.txt)",
        research_excerpt=_read(app_dir / "company-research.md", 1500) or "(no research)",
        prep_excerpt=_read(app_dir / "prep.md", 1500) or "(no prep.md — run make prep first)",
        profile_excerpt=profile_excerpt or "(no CV loaded)",
    )

    raw = call_ai(prompt, args.ai, api_key)

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
