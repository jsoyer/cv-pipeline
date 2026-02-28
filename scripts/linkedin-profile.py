#!/usr/bin/env python3
"""
Generate an optimised LinkedIn profile from CV data using AI.

Produces:
  1. Headline        — ≤ 220 characters (LinkedIn limit)
  2. About section   — ≤ 2 600 characters (LinkedIn limit)
  3. Featured banner — 1-sentence positioning blurb for banner/pinned post
  4. Current role summary — formatted for a LinkedIn Experience entry

Reads: data/cv.yml (or cv-tailored.yml if app-dir provided), meta.yml

Output:
  Without app-dir  → data/linkedin-profile.md  (general / master profile)
  With app-dir     → applications/NAME/linkedin-profile.md  (role-targeted)

Usage:
    scripts/linkedin-profile.py [<app-dir>] [--ai PROVIDER] [--lang fr]

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
_REPO_ROOT = _SCRIPT_DIR.parent

# --- AI models ---
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


# ---------------------------------------------------------------------------
# AI provider calls
# ---------------------------------------------------------------------------

def call_gemini(prompt, api_key, retries=6):
    for model in (GEMINI_MODEL, GEMINI_FALLBACK):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.5, "maxOutputTokens": 4096},
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
            "model": model, "max_tokens": 4096,
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
            "max_tokens": 4096, "temperature": 0.5,
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
# Context helpers
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


def _flatten_items(items: list) -> list[str]:
    """Flatten experience items (str or {label, text}) to plain strings."""
    out = []
    for item in items or []:
        if isinstance(item, str):
            out.append(re.sub(r"\*\*(.+?)\*\*", r"\1", item))
        elif isinstance(item, dict):
            label = item.get("label", "")
            text  = item.get("text", "")
            out.append(re.sub(r"\*\*(.+?)\*\*", r"\1",
                               f"{label}: {text}" if label else text))
    return out


def extract_cv_context(cv_data: dict) -> dict:
    """Pull the key fields needed for the prompt."""
    personal = cv_data.get("personal", {})
    profile  = cv_data.get("profile", "")

    # Current role
    exp = cv_data.get("experience", [])
    current = exp[0] if exp else {}

    # Key wins
    wins = cv_data.get("key_wins", [])

    # Skills
    skills_raw = cv_data.get("skills", [])
    skills_flat = []
    for s in skills_raw:
        if isinstance(s, dict):
            items = s.get("items", "")
            if isinstance(items, str):
                skills_flat.extend([i.strip() for i in items.split(",")])
            elif isinstance(items, list):
                skills_flat.extend(items)

    # Languages
    languages = cv_data.get("languages", [])

    return {
        "name":     personal.get("name", ""),
        "position": personal.get("position", ""),
        "location": personal.get("address", ""),
        "email":    personal.get("email", ""),
        "linkedin": personal.get("linkedin", ""),
        "profile":  re.sub(r"\*\*(.+?)\*\*", r"\1", profile) if isinstance(profile, str) else "",
        "current_title":   current.get("position", ""),
        "current_company": current.get("company", ""),
        "current_dates":   current.get("dates", ""),
        "current_items":   _flatten_items(current.get("items", [])),
        "key_wins":        [
            f"{w.get('title','')}: {re.sub(r'\\*\\*(.+?)\\*\\*', r'\\1', w.get('text',''))}"
            for w in wins if isinstance(w, dict)
        ],
        "top_skills": skills_flat[:20],
        "languages":  [l.get("idiom", "") for l in languages if isinstance(l, dict)],
    }


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are a LinkedIn profile specialist and personal branding expert for senior \
technology sales leaders. Write in a confident, human, first-person tone — \
no buzzwords, no clichés, no "passionate about".

## Candidate Profile

**Name:** {name}
**Current title:** {current_title} at {current_company}
**Location:** {location}
**Languages:** {languages}

**Profile summary from CV:**
{profile}

**Current role responsibilities (selected):**
{current_items}

**Key achievements:**
{key_wins}

**Top skills:** {top_skills}
{target_section}

## LinkedIn Character Limits
- Headline: ≤ 220 characters (including spaces)
- About: ≤ 2 600 characters (including spaces)
- Banner blurb: ≤ 160 characters

## Task

Write the following LinkedIn profile components. Respect character limits strictly.
{language_instruction}

### 1. Headline (≤ 220 chars)
Rules:
- Include current title + company (or "Open to opportunities" if job-seeking)
- One strong differentiator (team scale, ARR impact, domain)
- Use "|" as separator between elements
- No emojis unless they add genuine clarity

### 2. About section (≤ 2 600 chars)
Structure:
- Hook (1 sentence — what you do and for whom)
- Value proposition (2-3 sentences — what makes you different)
- 3 key achievements with numbers (bullet format, each ≤ 80 chars)
- Domain expertise (1 sentence — cybersecurity / data / SaaS / SE leadership)
- Current focus / what you are looking for (1 sentence)
- Call to action (connect / message / view work)

### 3. Banner blurb (≤ 160 chars)
One punchy positioning line for a LinkedIn banner image or pinned post. \
No emojis. Think conference speaker bio style.

### 4. Current experience entry
Write the LinkedIn "Description" field for the current role at {current_company}:
- 3-5 bullet points, each ≤ 100 chars
- Quantified where possible
- Past tense for completed items, present tense for ongoing

## Output format

Return ONLY the four sections in this exact format — no intro, no commentary:

---HEADLINE (N chars)---
[text]

---ABOUT (N chars)---
[text]

---BANNER (N chars)---
[text]

---EXPERIENCE---
[bullet points]
"""


def build_prompt(ctx: dict, target_role: str = "", lang: str = "en") -> str:
    target_section = ""
    if target_role:
        target_section = f"\n**Target role being applied for:** {target_role}\n"

    language_instruction = ""
    if lang == "fr":
        language_instruction = "\n**Language: Write everything in French** (professional register, tutoyez → vouvoyer).\n"

    current_items_str = "\n".join(f"- {i}" for i in ctx["current_items"][:6]) or "(none)"
    key_wins_str      = "\n".join(f"- {w}" for w in ctx["key_wins"][:5]) or "(none)"
    top_skills_str    = ", ".join(ctx["top_skills"][:15]) or "(none)"
    languages_str     = ", ".join(ctx["languages"]) or "French, English"

    return PROMPT_TEMPLATE.format(
        name=ctx["name"],
        current_title=ctx["current_title"],
        current_company=ctx["current_company"],
        location=ctx["location"],
        languages=languages_str,
        profile=ctx["profile"][:800] if ctx["profile"] else "(none)",
        current_items=current_items_str,
        key_wins=key_wins_str,
        top_skills=top_skills_str,
        target_section=target_section,
        language_instruction=language_instruction,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _count_chars(text: str) -> int:
    return len(text)


def _check_limits(raw: str) -> list[str]:
    """Return list of warning strings for sections exceeding LinkedIn limits."""
    warnings = []
    limits = {"HEADLINE": 220, "ABOUT": 2600, "BANNER": 160}

    for section, limit in limits.items():
        m = re.search(
            rf"---{section}.*?---\s*\n(.*?)(?=\n---|\Z)",
            raw, re.DOTALL | re.IGNORECASE
        )
        if m:
            text = m.group(1).strip()
            n = _count_chars(text)
            if n > limit:
                warnings.append(f"⚠️  {section}: {n} chars (limit {limit}) — trim needed")

    return warnings


def save_output(out_path: Path, raw: str, provider: str,
                app_name: str = "", lang: str = "en") -> Path:
    from datetime import date
    today  = date.today().isoformat()
    lang_label = " (FR)" if lang == "fr" else ""
    context_label = f" — {app_name}" if app_name else " — Master Profile"

    warnings = _check_limits(raw)

    lines = [
        f"# LinkedIn Profile{lang_label}{context_label}",
        f"*Generated: {today} · AI: {provider}*",
        "",
    ]

    if warnings:
        for w in warnings:
            lines.append(f"> {w}")
        lines.append("")

    lines += ["---", "", raw.strip(), ""]

    lines += [
        "---",
        "## Update Checklist",
        "",
        "- [ ] Copy Headline → LinkedIn profile > Edit intro",
        "- [ ] Copy About → LinkedIn profile > About",
        "- [ ] Copy Banner blurb → Canva/banner tool for profile banner image",
        "- [ ] Copy Experience → LinkedIn > Experience > current role description",
        "- [ ] Verify character counts before saving (LinkedIn truncates silently)",
        "- [ ] Add 3-5 relevant skills in LinkedIn Skills section after updating",
        "",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate optimised LinkedIn profile from CV data"
    )
    parser.add_argument(
        "app_dir", nargs="?", default="",
        help="Application directory (optional — uses cv-tailored.yml if present)"
    )
    parser.add_argument(
        "--ai", default="gemini",
        choices=sorted(VALID_PROVIDERS),
        help="AI provider (default: gemini)"
    )
    parser.add_argument(
        "--lang", default="en", choices=["en", "fr"],
        help="Output language: en (default) or fr"
    )
    args = parser.parse_args()

    load_env()

    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set — add it to .env or export it")
        sys.exit(1)

    # Locate CV source
    target_role = ""
    app_name    = ""
    app_dir     = None

    if args.app_dir:
        app_dir = Path(args.app_dir)
        if not app_dir.is_dir():
            app_dir = _REPO_ROOT / "applications" / Path(args.app_dir).name
        if not app_dir.is_dir():
            print(f"❌ Directory not found: {args.app_dir}")
            sys.exit(1)

        app_name = app_dir.name
        cv_src   = app_dir / "cv-tailored.yml"
        if not cv_src.exists():
            cv_src = _REPO_ROOT / "data" / "cv.yml"
            print(f"   ℹ️  No cv-tailored.yml — using data/cv.yml")

        meta_path = app_dir / "meta.yml"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
            target_role = f"{meta.get('position','')} at {meta.get('company','')}".strip(" at")

        out_path = app_dir / "linkedin-profile.md"
    else:
        cv_src   = _REPO_ROOT / "data" / "cv.yml"
        out_path = _REPO_ROOT / "data" / "linkedin-profile.md"

    if not cv_src.exists():
        print(f"❌ CV source not found: {cv_src}")
        sys.exit(1)

    with open(cv_src, encoding="utf-8") as f:
        cv_data = yaml.safe_load(f) or {}

    ctx = extract_cv_context(cv_data)

    lang_label = " (French)" if args.lang == "fr" else ""
    print(f"💼 Generating LinkedIn profile{lang_label}")
    if app_name:
        print(f"   Application: {app_name}")
        if target_role:
            print(f"   Target role: {target_role}")
    else:
        print(f"   Mode: master profile (data/cv.yml)")
    print(f"   AI: {args.ai}...")
    print()

    prompt     = build_prompt(ctx, target_role=target_role, lang=args.lang)
    raw_output = call_ai(prompt, args.ai, api_key)

    # Show character count warnings
    warnings = _check_limits(raw_output)
    if warnings:
        print("\n".join(warnings))
        print()

    saved = save_output(out_path, raw_output, args.ai,
                        app_name=app_name, lang=args.lang)

    print(raw_output.strip())
    print(f"\n✅ Saved to {saved}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
