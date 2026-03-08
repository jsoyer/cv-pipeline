#!/usr/bin/env python3
"""
Generate a negotiation script and counter-offer email using AI.

Usage:
    scripts/negotiate.py <app-dir> [--offer AMOUNT] [--ai PROVIDER]

Options:
    --offer AMOUNT   Current offer amount/package (e.g. "€120k + 10% bonus")
    --ai PROVIDER    AI provider: gemini (default), claude, openai, mistral, ollama

Output saved to: <app-dir>/negotiate.md
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


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def load_text(path, max_chars=None):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text[:max_chars] if max_chars else text
    except Exception:
        return ""


def extract_key_wins(cv_yml_path, n=3):
    """Extract top N key_wins for prompt context."""
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

def build_prompt(app_dir, offer_amount):
    meta     = load_meta(app_dir)
    company  = meta.get("company",  "the company")
    position = meta.get("position", "the position")
    notes    = meta.get("notes", "")

    cv_src = os.path.join(app_dir, "cv-tailored.yml")
    if not os.path.exists(cv_src):
        cv_src = os.path.join(REPO_ROOT, "data", "cv.yml")
    candidate_name = "Candidate"
    if os.path.exists(cv_src):
        with open(cv_src, encoding="utf-8") as f:
            _cv = yaml.safe_load(f) or {}
        personal = _cv.get("personal", {})
        name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        if name:
            candidate_name = name

    # Extract offer from notes if not passed explicitly
    if not offer_amount and notes:
        offer_amount = notes

    job_text  = load_text(os.path.join(app_dir, "job.txt"), max_chars=400)
    key_wins  = extract_key_wins(os.path.join(app_dir, "cv-tailored.yml"), n=3)
    research  = load_text(os.path.join(app_dir, "company-research.md"), max_chars=400)

    context_lines = []
    if offer_amount:
        context_lines.append(f"- Current offer: {offer_amount}")
    if key_wins:
        context_lines.append(f"- Key strengths / achievements (from CV):\n{key_wins}")
    if job_text:
        context_lines.append(f"- Job description highlights: {job_text}")
    if research:
        context_lines.append(f"- Company context: {research}")

    context_block = "\n".join(context_lines) if context_lines else "  (no additional context available)"

    return f"""You are an expert career coach specializing in compensation negotiation for senior tech sales and pre-sales professionals.

Context:
- Company: {company}
- Position: {position}
{context_block}

Generate a complete negotiation package with THREE sections:

## 1. Counter-Offer Email (150-200 words)
Professional email to respond to the offer. Requirements:
- Express genuine enthusiasm for the role and company
- Briefly anchor with market data or unique value
- Make a specific counter-proposal (if offer provided, suggest 15-20% higher base)
- Keep a collaborative, not adversarial tone
- Sign off as: {candidate_name}

## 2. Negotiation Call Talking Points
5-7 bullet points for a live negotiation conversation:
- Opening frame (gratitude + enthusiasm)
- Market positioning (SE/presales benchmarks in Europe)
- Value anchors (specific wins / revenue impact)
- Counter-ask for each component: base, bonus, equity, benefits
- BATNA signal (without revealing actual BATNA)
- Closing / next steps

## 3. Package Components Checklist
Table of items to negotiate beyond base salary:
| Component | Current | Target | Priority |
Format: base salary, bonus %, equity/RSU, signing bonus, remote flexibility,
equipment budget, L&D budget, vacation days, start date flexibility

Keep the tone confident, data-driven, and collaborative throughout."""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    load_env()

    parser = argparse.ArgumentParser(
        description="Generate a negotiation script and counter-offer email using AI"
    )
    parser.add_argument(
        "app_dir",
        help="Application directory (e.g. applications/2026-02-databricks)",
    )
    parser.add_argument(
        "--offer",
        default="",
        metavar="AMOUNT",
        help='Current offer amount/package (e.g. "€120k + 10%% bonus")',
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

    print(f"💰 Negotiation Script Generator")
    print(f"   Application: {app_name}")
    print(f"   Company:     {company}")
    print(f"   Provider:    {provider}")
    if args.offer:
        print(f"   Offer:       {args.offer}")
    if provider == "ollama":
        host  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        model = os.environ.get("OLLAMA_MODEL", "llama3")
        print(f"   Host:        {host}  Model: {model}")
    print("   Generating...", flush=True)
    print()

    try:
        prompt = build_prompt(app_dir, args.offer)
        script = call_ai(prompt, provider, api_key, temperature=0.7, max_tokens=3000)
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        sys.exit(1)

    print(script)
    print()

    output_path = os.path.join(app_dir, "negotiate.md")
    header = (
        f"---\n"
        f"generated: {date.today().isoformat()}\n"
        f"provider: {provider}\n"
        f"company: {meta.get('company', '')}\n"
        f"position: {meta.get('position', '')}\n"
        f"offer: {args.offer or meta.get('notes', '')}\n"
        f"---\n\n"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + script + "\n")

    print(f"✅ Saved to {output_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
