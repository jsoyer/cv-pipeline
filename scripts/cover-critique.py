#!/usr/bin/env python3
"""
AI-powered cover letter critique.

Scores and critiques your cover letter against the job description:
hook strength, tone, specificity, keyword alignment, structure, CTA.
Provides actionable rewrite suggestions for weak sections.

Reads: coverletter.yml, job.txt, meta.yml
Output: applications/NAME/cover-critique.md

Usage:
    scripts/cover-critique.py <app-dir> [--ai PROVIDER]

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


def _strip_bold(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


def _render_coverletter(cl_data: dict) -> str:
    """Flatten coverletter.yml to plain text for AI analysis."""
    parts = []
    salutation = cl_data.get("salutation", cl_data.get("recipient", ""))
    if salutation:
        parts.append(str(salutation))
        parts.append("")
    paragraphs = cl_data.get("paragraphs", cl_data.get("body", []))
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    for para in paragraphs:
        if isinstance(para, dict):
            text = para.get("text", para.get("content", ""))
        else:
            text = str(para)
        parts.append(_strip_bold(text))
        parts.append("")
    closing = cl_data.get("closing", cl_data.get("sign_off", ""))
    if closing:
        parts.append(str(closing))
    return "\n".join(parts).strip()


PROMPT_TEMPLATE = """\
You are a senior hiring manager and career coach critiquing a cover letter for a \
VP-level technology sales role. Be honest, specific, and constructive. \
Do not be encouraging for its own sake — flag real weaknesses.

## Candidate
Jérôme Soyer — applying for {position} at {company}.

## Cover Letter Text
{cover_text}

## Job Description
{job_excerpt}

## Task

Provide a structured critique using this exact format:

---

## 📊 Score Summary

| Dimension | Score | Notes |
|-----------|-------|-------|
| Hook strength (first sentence) | /20 | |
| Tone fit (formal/informal match) | /15 | |
| Specificity (company/role tailoring) | /20 | |
| Achievement evidence (numbers, results) | /20 | |
| Keyword alignment (job req coverage) | /15 | |
| Structure & CTA | /10 | |
| **Total** | **/100** | |

**Overall verdict:** [Strong / Solid / Needs Work / Rewrite Required]

---

## 🪝 Hook Analysis
Quote the opening sentence. Rate it and explain why it does or doesn't work.
If weak: provide a stronger replacement opening sentence.

---

## ✅ What Works
3 specific strengths. Be precise — reference actual sentences or phrases.

---

## ⚠️ What Needs Fixing
For each issue:
- **What:** [describe the problem]
- **Why it matters:** [impact on reader]
- **Fix:** [1-2 sentences showing the improved version]

List 3–5 issues, ordered by priority.

---

## 🔑 Keyword Gaps
List 3–5 keywords or phrases from the job description that are absent or underused
in the cover letter. For each, suggest where to naturally insert it.

---

## ✏️ Suggested Rewrite — Opening Paragraph
Rewrite the opening paragraph from scratch, applying all fixes.
Keep the candidate's voice — no "I am excited to" or "I am passionate about".

---
"""


def main():
    parser = argparse.ArgumentParser(description="AI cover letter critique vs job description")
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument("--ai", default="gemini", choices=sorted(VALID_PROVIDERS))
    args = parser.parse_args()

    load_env()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        app_dir = REPO_ROOT / "applications" / Path(args.app_dir).name
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {args.app_dir}")
        sys.exit(1)

    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set")
        sys.exit(1)

    # Load cover letter
    cl_path = app_dir / "coverletter.yml"
    if not cl_path.exists():
        print("❌ coverletter.yml not found in application directory")
        sys.exit(1)
    with open(cl_path, encoding="utf-8") as f:
        cl_data = yaml.safe_load(f) or {}
    cover_text = _render_coverletter(cl_data)
    if not cover_text.strip():
        print("❌ Cover letter appears empty")
        sys.exit(1)

    meta = {}
    if (app_dir / "meta.yml").exists():
        with open(app_dir / "meta.yml", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "the role")

    job_path = app_dir / "job.txt"
    job_excerpt = job_path.read_text(encoding="utf-8")[:2000] if job_path.exists() else "(no job.txt)"

    print(f"📝 Critiquing cover letter — {company} ({position})")
    print(f"   AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        company=company,
        position=position,
        cover_text=cover_text[:3000],
        job_excerpt=job_excerpt,
    )

    raw = call_ai(prompt, args.ai, api_key, temperature=0.3, max_tokens=3000)

    from datetime import date
    today = date.today().isoformat()

    lines = [
        f"# Cover Letter Critique — {company}",
        f"*{position} · {today} · AI: {args.ai}*",
        "",
        "## Cover Letter Analysed",
        "",
        "```",
        cover_text,
        "```",
        "",
        "---",
        "",
        raw.strip(),
        "",
    ]
    out = app_dir / "cover-critique.md"
    out.write_text("\n".join(lines), encoding="utf-8")

    print(raw.strip())
    print(f"\n✅ Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
