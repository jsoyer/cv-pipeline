#!/usr/bin/env python3
"""
Generate 3 cover letter variants with different persuasion angles using AI.

Angles:
  business   — Business impact: ARR, revenue, quota, ROI, scale
  technical  — Technical leadership: architecture, engineering, platform
  culture    — Culture & vision: values, team, mission, people

Each angle produces a complete coverletter-{angle}.yml in the application dir,
ready to render with: python3 scripts/render.py -d coverletter-business.yml ...

Output:
  applications/NAME/coverletter-business.yml
  applications/NAME/coverletter-technical.yml
  applications/NAME/coverletter-culture.yml
  applications/NAME/cover-angles.md  (side-by-side opening sentences)

Usage:
    scripts/cover-angles.py <app-dir> [--angles a,b,c] [--ai PROVIDER]

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

ANGLE_LABEL = {
    "business":  "Business Impact",
    "technical": "Technical Leadership",
    "culture":   "Culture & Vision",
}

ANGLE_FOCUS = {
    "business": (
        "Emphasise business impact first: ARR growth percentages, revenue figures, "
        "quota attainment, deal sizes, headcount scale, M&A value. "
        "The reader is a business leader (CRO, VP Sales). Lead with numbers and outcomes."
    ),
    "technical": (
        "Emphasise technical leadership and engineering depth: architecture decisions, "
        "platform strategy, SE methodology, PoV/PoC approach, technical enablement, "
        "integration of acquisitions. "
        "The reader is a CTO, VP Engineering, or technical hiring manager."
    ),
    "culture": (
        "Emphasise cultural fit, vision alignment, and people leadership: company mission, "
        "team culture, mentorship, talent development, why this company specifically, "
        "shared values. "
        "The reader is a people-focused CHRO or culture-driven hiring manager."
    ),
}

PROMPT_TEMPLATE = """\
You are an expert career coach and copywriter specialising in executive cover letters \
for Sales Engineering and technical leadership roles.

## Applicant
Jérôme Soyer — Regional VP of Sales Engineering, Varonis (Paris).
{cv_excerpt}

## Job posting
{job_excerpt}

## Company: {company}  |  Role: {position}

## Your task — write a cover letter with a "{angle_label}" angle

{angle_focus}

**Output format — YAML only, no markdown fences, exact structure:**

recipient:
  name: "Hiring Team"
  company: "{company}"
title: "Application for {position}"
opening: "Dear Hiring Team,"
closing: "Sincerely,"
sections:
  - title: "About Me"
    content: >-
      [2-3 sentences. {angle_label} angle. **bold** key phrases.]
  - title: "Why {company}?"
    content: >-
      [2-3 sentences specific to {company}. Research-informed. **bold** key phrases.]
  - title: "Why Me?"
    content: >-
      [3-4 sentences. Strongest match for THIS role. **bold** key phrases.]
closing_paragraph: >-
  [1-2 sentences. Professional close. Mention availability for interview.]

Rules:
- YAML only — no markdown fences, no ```yaml, no comments
- Use >- for all multiline strings
- **bold** for emphasis (not LaTeX)
- Must fit on one page when rendered — keep each section concise (2-4 sentences max)
- Reference the company by name at least once per section
- No generic phrases like "I am writing to apply" or "I believe I am a strong candidate"
"""


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def fix_yaml_bold(text: str) -> str:
    """Quote YAML values starting with ** to prevent parse errors."""
    lines = text.splitlines()
    fixed = []
    for line in lines:
        m = re.match(r"^(\s*\w[\w\s]*:\s+)(\*\*.+)", line)
        if m and not line.strip().startswith("#"):
            key_part = m.group(1)
            val_part = m.group(2)
            if not val_part.startswith('"'):
                line = f'{key_part}"{val_part}"'
        fixed.append(line)
    return "\n".join(fixed)


def extract_yaml_block(text: str) -> str:
    """Extract YAML from AI response (strip markdown fences if present)."""
    m = re.search(r"```(?:yaml)?\s*\n([\s\S]+?)\n```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip()


def parse_yaml_safe(text: str) -> dict:
    cleaned = extract_yaml_block(text)
    cleaned = fix_yaml_bold(cleaned)
    return yaml.safe_load(cleaned)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cv_excerpt(cv_data: dict) -> str:
    """Brief CV summary for the prompt."""
    personal = cv_data.get("personal", {})
    name     = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
    position = personal.get("position", "")
    profile  = cv_data.get("profile", "")[:400]
    wins = cv_data.get("key_wins", [])
    win_lines = [f"- {w.get('title', '')}" for w in wins[:3]]
    return (
        f"Position: {position}\n"
        f"Profile: {profile}\n"
        f"Key achievements:\n" + "\n".join(win_lines)
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate 3 cover letter variants with different angles"
    )
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument(
        "--angles", default="business,technical,culture",
        help="Comma-separated angles to generate (default: business,technical,culture)"
    )
    parser.add_argument(
        "--ai", default="gemini", choices=sorted(VALID_PROVIDERS),
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
        print(f"❌ {key_env} not set — add it to .env")
        sys.exit(1)

    angles = [a.strip() for a in args.angles.split(",") if a.strip() in ANGLE_LABEL]
    if not angles:
        print(f"❌ No valid angles. Choose from: {', '.join(ANGLE_LABEL)}")
        sys.exit(1)

    # Load context
    meta = {}
    meta_path = app_dir / "meta.yml"
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "the role")

    job_text = ""
    job_path = app_dir / "job.txt"
    if job_path.exists():
        job_text = job_path.read_text(encoding="utf-8")[:3000]
    else:
        print("⚠️  No job.txt — angle generation will be generic")

    cv_data_path = app_dir / "cv-tailored.yml"
    if not cv_data_path.exists():
        cv_data_path = REPO_ROOT / "data" / "cv.yml"
    with open(cv_data_path, encoding="utf-8") as f:
        cv_data = yaml.safe_load(f) or {}

    cv_ex = _cv_excerpt(cv_data)

    print(f"📐 Generating {len(angles)} cover letter angles — {company} ({position})")
    print(f"   AI: {args.ai}\n")

    generated = {}
    errors    = {}

    for angle in angles:
        label = ANGLE_LABEL[angle]
        print(f"   [{label}]...", end=" ", flush=True)

        prompt = PROMPT_TEMPLATE.format(
            company=company,
            position=position,
            angle_label=label,
            angle_focus=ANGLE_FOCUS[angle],
            cv_excerpt=cv_ex,
            job_excerpt=job_text if job_text else "(no job description provided)",
        )

        try:
            raw = call_ai(prompt, args.ai, api_key, temperature=0.5)
            cl_data = parse_yaml_safe(raw)

            # Validate structure
            if not isinstance(cl_data, dict) or "sections" not in cl_data:
                raise ValueError("Invalid YAML structure — 'sections' key missing")

            out_path = app_dir / f"coverletter-{angle}.yml"
            with open(out_path, "w", encoding="utf-8") as f:
                yaml.dump(cl_data, f, default_flow_style=False, allow_unicode=True,
                          sort_keys=False, width=120)

            generated[angle] = (cl_data, out_path)
            print("✅")

        except Exception as e:
            errors[angle] = str(e)
            print(f"❌ {str(e)[:60]}")

    # Write comparison summary
    if generated:
        from datetime import date
        today = date.today().isoformat()
        lines = [
            f"# Cover Letter Angles — {company}",
            f"*{position} · Generated: {today} · AI: {args.ai}*",
            "",
            "Compare opening sentences to choose your angle before applying.",
            "",
            "---",
            "",
        ]
        for angle in angles:
            if angle not in generated:
                continue
            cl_data, out_path = generated[angle]
            label = ANGLE_LABEL[angle]

            # Extract first section content
            sections = cl_data.get("sections", [])
            first_content = ""
            if sections and isinstance(sections[0], dict):
                first_content = sections[0].get("content", "")[:300]

            lines += [
                f"## {label} (`coverletter-{angle}.yml`)",
                "",
                f"*Opening:* {cl_data.get('opening', '')}",
                "",
                f"> {first_content}",
                "",
                f"**To use:** `make app NAME={app_dir.name}` after copying:",
                f"```",
                f"cp applications/{app_dir.name}/coverletter-{angle}.yml "
                f"applications/{app_dir.name}/coverletter.yml",
                f"```",
                "",
            ]

        if errors:
            lines += ["---", "## Generation Errors", ""]
            for angle, err in errors.items():
                lines.append(f"- ❌ {ANGLE_LABEL.get(angle, angle)}: {err}")
            lines.append("")

        summary_path = app_dir / "cover-angles.md"
        summary_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n✅ Comparison saved to {summary_path}")

    # Final summary
    print()
    for angle in angles:
        if angle in generated:
            _, out_path = generated[angle]
            print(f"   ✅ {ANGLE_LABEL[angle]}: {out_path.name}")
        elif angle in errors:
            print(f"   ❌ {ANGLE_LABEL[angle]}: {errors[angle][:60]}")

    if generated:
        print(f"\n💡 Choose an angle, copy it to coverletter.yml, then:")
        print(f"   make app NAME={app_dir.name}")

    return 0 if len(generated) == len(angles) else 1


if __name__ == "__main__":
    sys.exit(main())
