#!/usr/bin/env python3
"""
AI-translate and adapt a tailored CV + Cover Letter to French.

Takes cv-tailored.yml (fallback: data/cv.yml) and optionally coverletter.yml,
translates all text content to French while keeping the YAML structure intact,
and adapts phrasing for French professional market conventions.

Output:
  applications/NAME/cv-tailored-fr.yml
  applications/NAME/coverletter-fr.yml  (if coverletter.yml exists)

Then render with:
  python3 scripts/render.py applications/NAME/cv-tailored-fr.yml --lang fr

Usage:
    scripts/cv-fr-tailor.py <app-dir> [--no-cl] [--ai PROVIDER]

AI providers: gemini (default) | claude | openai | mistral | ollama
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS
from lib.common import load_env, REPO_ROOT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_yaml_block(text: str) -> str:
    """Strip markdown fences from AI output."""
    m = re.search(r"```(?:yaml)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def fix_yaml_bold(text: str) -> str:
    """Quote YAML values that start with ** to prevent parse errors."""
    return re.sub(
        r"^(\s*(?:- (?:text|label):|[^:]+:)\s)(\*\*.+)$",
        lambda m: m.group(1) + '"' + m.group(2).replace('"', '\\"') + '"',
        text,
        flags=re.MULTILINE,
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

CV_PROMPT_TEMPLATE = """\
You are a professional French translator and CV specialist. Translate the following \
CV YAML file from English to French, adapting it for the French professional market.

## Rules

1. **Translate only text content** — keep all YAML keys in English (they are code)
2. **Preserve YAML structure exactly** — indentation, list format, multiline markers (>-, |)
3. **Keep `**bold**` markers** intact around translated text
4. **Keep `--` for date ranges** (e.g. "jan. 2020 -- jan. 2022")
5. **Do NOT translate** proper nouns: company names, product names, tool names, \
   certifications, acronyms (ARR, SE, VP, etc.), city names
6. **Do NOT escape** LaTeX special chars — the renderer handles that
7. **French professional register** — use formal "vous" register in descriptions, \
   strong action verbs (Dirigé, Développé, Piloté, Structuré, Accéléré…)
8. **Month abbreviations** in French: jan., fév., mars, avr., mai, juin, \
   juil., août, sept., oct., nov., déc.
9. **Numbers**: keep € symbol, use space as thousands separator (ex: 50 000)
10. Output raw YAML only — no markdown fences, no commentary

## Input YAML

{cv_yaml}
"""

CL_PROMPT_TEMPLATE = """\
You are a professional French translator and cover letter specialist. Translate the \
following cover letter YAML file from English to French, adapting it for the French \
professional job application style (formal, structured, "Madame, Monsieur" register).

## Rules

1. **Translate only text content** — keep all YAML keys in English
2. **Preserve YAML structure exactly** — indentation, list format, multiline markers
3. **Keep `**bold**` markers** intact
4. **Do NOT translate** proper nouns: company names, product names, cities, acronyms
5. **French cover letter conventions**:
   - Salutation: "Madame, Monsieur," (or specific name if known)
   - Opening: reference the role and company directly
   - Tone: formal but not cold
   - Closing: standard formula ("Dans l'attente de vous rencontrer, \
je vous adresse mes cordiales salutations.")
6. Output raw YAML only — no markdown fences, no commentary

## Input YAML

{cl_yaml}
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AI-translate tailored CV and Cover Letter to French"
    )
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument(
        "--no-cl", action="store_true",
        help="Skip cover letter translation"
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

    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set — add it to .env or export it")
        sys.exit(1)

    meta_path = app_dir / "meta.yml"
    meta = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")

    # --- Locate source CV ---
    cv_src = app_dir / "cv-tailored.yml"
    if not cv_src.exists():
        cv_src = REPO_ROOT / "data" / "cv.yml"
        if not cv_src.exists():
            print("❌ No cv-tailored.yml or data/cv.yml found")
            sys.exit(1)
        print(f"   ℹ️  Using data/cv.yml (no cv-tailored.yml found)")

    # --- CV translation ---
    cv_yaml = cv_src.read_text(encoding="utf-8")
    print(f"🇫🇷 Translating CV to French — {company}")
    print(f"   Position: {position}")
    print(f"   Source: {cv_src.name}")
    print(f"   AI: {args.ai}...")

    cv_prompt  = CV_PROMPT_TEMPLATE.format(cv_yaml=cv_yaml)
    cv_raw     = call_ai(cv_prompt, args.ai, api_key)
    cv_cleaned = extract_yaml_block(cv_raw)
    cv_cleaned = fix_yaml_bold(cv_cleaned)

    # Validate
    try:
        yaml.safe_load(cv_cleaned)
    except yaml.YAMLError as e:
        print(f"⚠️  YAML parse warning for CV: {e}")
        print("   Saving raw output — manual fix may be needed.")

    cv_out = app_dir / "cv-tailored-fr.yml"
    cv_out.write_text(cv_cleaned, encoding="utf-8")
    print(f"   ✅ CV → {cv_out.name}")

    # --- Cover letter translation ---
    cl_src = app_dir / "coverletter.yml"
    if not args.no_cl and cl_src.exists():
        print(f"\n   Translating cover letter...")
        cl_yaml = cl_src.read_text(encoding="utf-8")
        cl_prompt  = CL_PROMPT_TEMPLATE.format(cl_yaml=cl_yaml)
        cl_raw     = call_ai(cl_prompt, args.ai, api_key)
        cl_cleaned = extract_yaml_block(cl_raw)
        cl_cleaned = fix_yaml_bold(cl_cleaned)

        try:
            yaml.safe_load(cl_cleaned)
        except yaml.YAMLError as e:
            print(f"   ⚠️  YAML parse warning for CL: {e}")

        cl_out = app_dir / "coverletter-fr.yml"
        cl_out.write_text(cl_cleaned, encoding="utf-8")
        print(f"   ✅ Cover letter → {cl_out.name}")
    elif not args.no_cl and not cl_src.exists():
        print(f"\n   ℹ️  No coverletter.yml found — skipping cover letter.")

    print(f"\n✅ Done. To render:")
    print(f"   python3 scripts/render.py {cv_out} --lang fr")
    if not args.no_cl and cl_src.exists():
        print(f"   python3 scripts/render.py {app_dir}/coverletter-fr.yml --lang fr")

    return 0


if __name__ == "__main__":
    sys.exit(main())
