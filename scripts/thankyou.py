#!/usr/bin/env python3
"""
Generate a thank-you email after a job interview using AI.

Usage:
    scripts/thankyou.py <app-dir> [--stage interview|offer] [--ai PROVIDER]

Providers:
    gemini   — Google Gemini (default, GEMINI_API_KEY)
    claude   — Anthropic Claude (ANTHROPIC_API_KEY)
    openai   — OpenAI GPT (OPENAI_API_KEY)
    mistral  — Mistral AI (MISTRAL_API_KEY)
    ollama   — Local Ollama server (no key, OLLAMA_HOST, OLLAMA_MODEL)

Output saved to: <app-dir>/thankyou.md
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
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

VALID_PROVIDERS = {"gemini", "claude", "openai", "mistral", "ollama"}

KEY_ENV = {
    "gemini":  "GEMINI_API_KEY",
    "claude":  "ANTHROPIC_API_KEY",
    "openai":  "OPENAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "ollama":  None,
}

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


# ---------------------------------------------------------------------------
# Provider call functions — mirrors ai-tailor.py exactly
# ---------------------------------------------------------------------------

def call_gemini(prompt, api_key, retries=6):
    for model in (GEMINI_MODEL, GEMINI_FALLBACK):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read())
                if model != GEMINI_MODEL:
                    print(f"   ✓ Used fallback model: {model}", flush=True)
                return result["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    wait = min(2 ** (attempt + 2), 120)
                    print(f"   ⏳ Rate limited (429) on {model}, retrying in {wait}s...", flush=True)
                    time.sleep(wait)
                elif e.code == 429 and model != GEMINI_FALLBACK:
                    print(f"   ⚠️  {model} still rate-limited, switching to {GEMINI_FALLBACK}...", flush=True)
                    break
                else:
                    raise
    raise RuntimeError(f"Gemini API rate-limited on both models. Try again later.")


def call_claude(prompt, api_key, retries=6):
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    for model in (CLAUDE_MODEL, CLAUDE_FALLBACK):
        payload = json.dumps({
            "model": model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read())
                if model != CLAUDE_MODEL:
                    print(f"   ✓ Used fallback model: {model}", flush=True)
                return result["content"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    wait = min(2 ** (attempt + 2), 120)
                    print(f"   ⏳ Rate limited (429) on {model}, retrying in {wait}s...", flush=True)
                    time.sleep(wait)
                elif e.code == 429 and model != CLAUDE_FALLBACK:
                    print(f"   ⚠️  {model} rate-limited, switching to {CLAUDE_FALLBACK}...", flush=True)
                    break
                else:
                    raise
    raise RuntimeError("Claude API rate-limited on both models. Try again later.")


def call_openai_compat(prompt, endpoint, api_key, models, retries=6):
    primary, fallback = models
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    for model in (primary, fallback):
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.7,
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(endpoint, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read())
                if model != primary:
                    print(f"   ✓ Used fallback model: {model}", flush=True)
                return result["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    wait = min(2 ** (attempt + 2), 120)
                    print(f"   ⏳ Rate limited (429) on {model}, retrying in {wait}s...", flush=True)
                    time.sleep(wait)
                elif e.code == 429 and model != fallback:
                    print(f"   ⚠️  {model} rate-limited, switching to {fallback}...", flush=True)
                    break
                else:
                    raise
    raise RuntimeError(f"API rate-limited on both models. Try again later.")


def call_ollama(prompt, retries=3):
    host  = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3")
    url   = f"{host}/api/chat"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=payload, headers={"content-type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())
            return result["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError(
                    f"Model '{model}' not found. Pull it first: ollama pull {model}"
                ) from e
            raise
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"   ⏳ Ollama unreachable, retrying in {wait}s...", flush=True)
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Cannot connect to Ollama at {host}. Is it running? Try: ollama serve"
                ) from e


def call_ai(prompt, provider, api_key):
    if provider == "gemini":
        return call_gemini(prompt, api_key)
    if provider == "claude":
        return call_claude(prompt, api_key)
    if provider == "openai":
        return call_openai_compat(prompt, OPENAI_ENDPOINT, api_key, (OPENAI_MODEL, OPENAI_FALLBACK))
    if provider == "mistral":
        return call_openai_compat(prompt, MISTRAL_ENDPOINT, api_key, (MISTRAL_MODEL, MISTRAL_FALLBACK))
    if provider == "ollama":
        return call_ollama(prompt)
    raise ValueError(f"Unknown provider: '{provider}'")


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def load_meta(app_dir):
    meta_path = os.path.join(app_dir, "meta.yml")
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_text(path, max_chars=None):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text[:max_chars] if max_chars else text
    except Exception:
        return ""


def extract_top_key_wins(cv_yml_path, n=3):
    """Extract top N key_wins from cv-tailored.yml for prompt context."""
    if not os.path.exists(cv_yml_path):
        return ""
    try:
        with open(cv_yml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        wins = (data or {}).get("key_wins", [])
        items = []
        for w in wins[:n]:
            title = str(w.get("title", "")).replace("**", "")
            text  = str(w.get("text",  "")).replace("**", "")[:150]
            items.append(f"  - {title}: {text}")
        return "\n".join(items)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def build_prompt(app_dir, stage):
    meta      = load_meta(app_dir)
    company   = meta.get("company",   "the company")
    position  = meta.get("position",  "the position")
    recipient = meta.get("recipient", "")

    job_text  = load_text(os.path.join(app_dir, "job.txt"), max_chars=300)
    key_wins  = extract_top_key_wins(os.path.join(app_dir, "cv-tailored.yml"), n=3)
    prep_text = load_text(os.path.join(app_dir, "prep.md"), max_chars=600)
    research  = load_text(os.path.join(app_dir, "company-research.md"), max_chars=400)

    context_lines = []
    if recipient:
        context_lines.append(f"- Recipient name: {recipient}")
    if key_wins:
        context_lines.append(f"- Key candidate strengths (from CV):\n{key_wins}")
    else:
        context_lines.append("- Key candidate strengths: (not available)")
    if job_text:
        context_lines.append(f"- Job description highlights: {job_text}")
    if prep_text:
        context_lines.append(f"- Interview topics to reference: {prep_text}")
    if research:
        context_lines.append(f"- Company context: {research}")

    context_block = "\n".join(context_lines)

    return f"""You are a professional career coach helping write a thank-you email after a job interview.

Context:
- Company: {company}
- Position: {position}
- Interview stage: {stage}
{context_block}

Write a professional, personalized thank-you email. Requirements:
- Subject line first, then body
- 150-200 words maximum
- Open with a specific reference to the conversation (not generic "I enjoyed our conversation")
- Mention one specific aspect of the role/company that genuinely interests you
- Reinforce one key strength that directly maps to the role
- End with a clear next step
- Warm but professional tone
- No placeholder brackets — write as if sending today
- Sign off as: Jérôme Soyer

Output ONLY:
Subject: [subject line]

[email body]"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Load .env if present
    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

    parser = argparse.ArgumentParser(
        description="Generate a thank-you email after a job interview using AI"
    )
    parser.add_argument(
        "app_dir",
        help="Application directory (e.g. applications/2026-02-databricks)",
    )
    parser.add_argument(
        "--stage",
        default="interview",
        choices=["interview", "offer"],
        help="Interview stage (default: interview)",
    )
    parser.add_argument(
        "--ai",
        dest="provider",
        default=os.environ.get("AI_PROVIDER", "gemini"),
        choices=sorted(VALID_PROVIDERS),
        help="AI provider (default: gemini)",
    )
    args = parser.parse_args()

    provider = args.provider
    app_dir  = args.app_dir

    if not os.path.isdir(app_dir):
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    key_var = KEY_ENV[provider]
    api_key = os.environ.get(key_var) if key_var else None
    if key_var and not api_key:
        print(f"❌ {provider} API key not set. Add {key_var} to .env")
        sys.exit(1)

    app_name = os.path.basename(app_dir.rstrip("/"))
    meta = load_meta(app_dir)
    company = meta.get("company", app_name)

    print(f"✉️  Thank-You Email Generator")
    print(f"   Application: {app_name}")
    print(f"   Company:     {company}")
    print(f"   Stage:       {args.stage}")
    print(f"   Provider:    {provider}")
    if provider == "ollama":
        host  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        model = os.environ.get("OLLAMA_MODEL", "llama3")
        print(f"   Host:        {host}  Model: {model}")
    print("   Generating...", flush=True)
    print()

    try:
        prompt     = build_prompt(app_dir, args.stage)
        email_text = call_ai(prompt, provider, api_key)
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        sys.exit(1)

    print(email_text)
    print()

    output_path = os.path.join(app_dir, "thankyou.md")
    header = (
        f"---\n"
        f"generated: {date.today().isoformat()}\n"
        f"stage: {args.stage}\n"
        f"provider: {provider}\n"
        f"company: {meta.get('company', '')}\n"
        f"position: {meta.get('position', '')}\n"
        f"---\n\n"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + email_text + "\n")

    print(f"✅ Saved to {output_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
