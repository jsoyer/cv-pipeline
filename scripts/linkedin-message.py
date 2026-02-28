#!/usr/bin/env python3
"""
Generate personalised LinkedIn outreach messages using AI.

Creates two formats:
  - Connection request note (≤ 300 chars — LinkedIn limit)
  - Follow-up InMail / message (≤ 600 chars)

Reads: meta.yml, job.txt (optional), contacts.md (optional),
       company-research.md (optional)

Output: applications/NAME/linkedin-message.md

Usage:
    scripts/linkedin-message.py <app-dir> [--type TYPE] [--contact NAME] [--ai PROVIDER]

Types:
    recruiter   — To a recruiter/talent team (default)
    hm          — To the hiring manager directly
    referral    — To a current employee requesting a referral

AI providers: gemini (default) | claude | openai | mistral | ollama
"""

import argparse
import json
import os
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
_REPO_ROOT = _SCRIPT_DIR.parent

# --- AI models (mirrors ai-tailor.py) ---
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

MESSAGE_TYPE_LABEL = {
    "recruiter": "Recruiter / Talent Team",
    "hm":        "Hiring Manager",
    "referral":  "Employee (Referral Request)",
}


# ---------------------------------------------------------------------------
# AI provider calls (identical pattern to ai-tailor.py)
# ---------------------------------------------------------------------------

def call_gemini(prompt, api_key, retries=6):
    for model in (GEMINI_MODEL, GEMINI_FALLBACK):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 2048},
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read())
                return result["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(min(2 ** (attempt + 2), 60))
                elif e.code == 429 and model != GEMINI_FALLBACK:
                    break
                else:
                    raise
    raise RuntimeError("Gemini rate-limited on both models")


def call_claude(prompt, api_key, retries=6):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    for model in (CLAUDE_MODEL, CLAUDE_FALLBACK):
        payload = json.dumps({
            "model": model, "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read())
                return result["content"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(min(2 ** (attempt + 2), 60))
                elif e.code == 429 and model != CLAUDE_FALLBACK:
                    break
                else:
                    raise
    raise RuntimeError("Claude rate-limited on both models")


def call_openai_compat(prompt, endpoint, api_key, models, retries=6):
    primary, fallback = models
    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    for model in (primary, fallback):
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048, "temperature": 0.5,
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(endpoint, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read())
                return result["choices"][0]["message"]["content"]
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
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{host}/api/chat", data=payload,
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())
            return result["message"]["content"]
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                raise RuntimeError(f"Cannot connect to Ollama at {host}")


def call_ai(prompt, provider, api_key):
    if provider == "gemini":
        return call_gemini(prompt, api_key)
    if provider == "claude":
        return call_claude(prompt, api_key)
    if provider == "openai":
        return call_openai_compat(prompt, OPENAI_ENDPOINT, api_key,
                                   (OPENAI_MODEL, OPENAI_FALLBACK))
    if provider == "mistral":
        return call_openai_compat(prompt, MISTRAL_ENDPOINT, api_key,
                                   (MISTRAL_MODEL, MISTRAL_FALLBACK))
    if provider == "ollama":
        return call_ollama(prompt)
    raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------

def load_env():
    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _read_file(path: Path, max_chars: int = 3000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:max_chars]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are a career coach helping a senior technology sales leader write personalised LinkedIn \
outreach messages. Write in a professional yet warm, human tone — no buzzwords, no generic \
templates.

## Context

**Applicant:** Jérôme Soyer — Regional VP of Sales Engineering at Varonis, Paris.
Expert in scaling SE organisations (50+ HC), driving ARR growth, M&A technical integration, \
cybersecurity/data/SaaS domain. French native, fluent English.

**Target company:** {company}
**Role applied for:** {position}
**Message type:** {msg_type_label}
{contact_section}
**Job posting excerpt:**
{job_excerpt}
{research_excerpt}
## Task

Write TWO LinkedIn messages for a **{msg_type_label}** outreach:

### 1. Connection Request Note (STRICT MAX 300 characters including spaces)
- Personalised, references the company or role
- Ends with a clear, soft call-to-action
- No emojis

### 2. Follow-Up InMail / Message (STRICT MAX 600 characters including spaces)
- Expands on the connection note
- Mentions one specific relevant achievement
- References something specific about the company/role
- Clear next step (call, coffee chat, etc.)
- No emojis

## Output format

Return ONLY the two messages in this exact format — no intro, no commentary:

---CONNECTION NOTE (N chars)---
[message text here]

---INMAIL (N chars)---
[message text here]
"""


def build_prompt(meta: dict, msg_type: str, contact_name: str,
                 job_text: str, research_text: str) -> str:
    company  = meta.get("company", "the company")
    position = meta.get("position", "the role")

    contact_section = ""
    if contact_name:
        contact_section = f"**Contact name:** {contact_name}\n"

    return PROMPT_TEMPLATE.format(
        company=company,
        position=position,
        msg_type_label=MESSAGE_TYPE_LABEL.get(msg_type, msg_type),
        contact_section=contact_section,
        job_excerpt=job_text[:2000] if job_text else "(no job.txt available)",
        research_excerpt=(
            f"\n**Company research:**\n{research_text[:1000]}\n"
            if research_text else ""
        ),
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_output(app_dir: Path, meta: dict, msg_type: str, contact_name: str,
                raw_output: str, provider: str) -> Path:
    from datetime import date
    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    today    = date.today().isoformat()
    type_label = MESSAGE_TYPE_LABEL.get(msg_type, msg_type)

    lines = [
        f"# LinkedIn Message — {company}",
        f"*{position} · Type: {type_label} · Generated: {today} · AI: {provider}*",
        "",
    ]
    if contact_name:
        lines += [f"**Contact:** {contact_name}", ""]

    lines += ["---", "", raw_output.strip(), ""]

    lines += [
        "---",
        "## Tips",
        "",
        "- Send the Connection Note first; InMail only if not connected",
        "- Personalise `[N chars]` placeholders if AI left them",
        "- Best time: Tuesday–Thursday, 9–11am recipient timezone",
        "- After 1 week with no reply: one polite follow-up maximum",
        "",
    ]

    out_path = app_dir / "linkedin-message.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate personalised LinkedIn outreach messages"
    )
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument(
        "--type", choices=["recruiter", "hm", "referral"], default="recruiter",
        help="Message type (default: recruiter)"
    )
    parser.add_argument(
        "--contact", default="",
        help="Contact name to address (from contacts.md)"
    )
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

    # Resolve API key
    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set — add it to .env or export it")
        sys.exit(1)

    # Load context
    meta_path = app_dir / "meta.yml"
    meta = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")

    job_text      = _read_file(app_dir / "job.txt")
    research_text = _read_file(app_dir / "company-research.md")

    # Try to extract contact name from contacts.md if not provided
    contact_name = args.contact
    if not contact_name:
        contacts_md = _read_file(app_dir / "contacts.md", 500)
        import re
        m = re.search(r"Primary contact:\s*(.+?)\s*<", contacts_md)
        if m:
            contact_name = m.group(1).strip()

    type_label = MESSAGE_TYPE_LABEL.get(args.type, args.type)
    print(f"✍️  Generating LinkedIn message — {company}")
    print(f"   Type: {type_label}")
    if contact_name:
        print(f"   Contact: {contact_name}")
    print(f"   AI: {args.ai}...")
    print()

    prompt     = build_prompt(meta, args.type, contact_name, job_text, research_text)
    raw_output = call_ai(prompt, args.ai, api_key)

    out_path = save_output(app_dir, meta, args.type, contact_name, raw_output, args.ai)

    print(raw_output.strip())
    print(f"\n✅ Saved to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
