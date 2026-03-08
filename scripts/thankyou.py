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
import os
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)

from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS
from lib.common import load_env, load_meta, REPO_ROOT


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

    cv_src = os.path.join(app_dir, "cv-tailored.yml")
    if not os.path.exists(cv_src):
        cv_src = os.path.join(REPO_ROOT, "data", "cv.yml")
    candidate_name = "Candidate"
    if os.path.exists(cv_src):
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}
        personal = cv_data.get("personal", {})
        name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        if name:
            candidate_name = name

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
- Sign off as: {candidate_name}

Output ONLY:
Subject: [subject line]

[email body]"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    load_env()

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
        email_text = call_ai(prompt, provider, api_key, temperature=0.7, max_tokens=2000)
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
