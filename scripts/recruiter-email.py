#!/usr/bin/env python3
"""
Generate personalised cold recruiter outreach emails using AI.

Creates two formats:
  - Subject line
  - Email body (150-250 words, professional, direct)

Types:
  cold       — First cold contact to a recruiter/HM (default)
  follow-up  — Follow-up after applying with no response (2-3 weeks)
  post-apply — Confirm application was submitted + express interest

Reads: meta.yml, job.txt (optional), contacts.md (optional),
       company-research.md (optional)

Output: applications/NAME/recruiter-email.md

Usage:
    scripts/recruiter-email.py <app-dir> [--type TYPE] [--contact NAME] [--ai PROVIDER]

AI providers: gemini (default) | claude | openai | mistral | ollama
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS
from lib.common import load_env, REPO_ROOT

EMAIL_TYPE_LABEL = {
    "cold":       "Cold Outreach",
    "follow-up":  "Follow-Up (No Response)",
    "post-apply": "Post-Application Confirmation",
}


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------

def _read_file(path: Path, max_chars: int = 3000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:max_chars]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are a career coach helping a senior technology sales leader write a professional \
outreach email to a recruiter or hiring manager. Write in a confident, warm, \
direct tone — no buzzwords, no templates, no fluff.

## Context

**Applicant:** {candidate_name} — {candidate_position}.
{candidate_profile}

**Target company:** {company}
**Role applied for:** {position}
**Email type:** {email_type_label}
{contact_section}
**Job posting excerpt:**
{job_excerpt}
{research_excerpt}
## Task

Write a professional outreach email for a **{email_type_label}** scenario:

### Rules
- Subject line: punchy, specific, ≤ 60 characters
- Body: 150-250 words
- Salutation: use contact name if provided, else "Hi [Name],"
- Opening: reference the specific role or company immediately
- Middle: one concrete achievement with numbers; one reason this company specifically
- Closing: clear single call-to-action (15-min call, coffee chat, reply to confirm)
- Sign-off: "Best regards,\\n{candidate_name}"
- No emojis. No generic openers ("I hope this email finds you well").

## Output format

Return ONLY the email in this exact format — no intro, no commentary:

---SUBJECT---
[subject line]

---BODY---
[email body]
"""


def build_prompt(meta: dict, email_type: str, contact_name: str,
                 job_text: str, research_text: str,
                 cv_data: dict | None = None) -> str:
    company  = meta.get("company", "the company")
    position = meta.get("position", "the role")

    personal = (cv_data or {}).get("personal", {})
    candidate_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip() or "Candidate"
    candidate_position = personal.get("position", "")
    profile = (cv_data or {}).get("profile", "")
    candidate_profile = profile[:300] if profile else ""

    contact_section = ""
    if contact_name:
        contact_section = f"**Contact name:** {contact_name}\n"

    return PROMPT_TEMPLATE.format(
        candidate_name=candidate_name,
        candidate_position=candidate_position,
        candidate_profile=candidate_profile,
        company=company,
        position=position,
        email_type_label=EMAIL_TYPE_LABEL.get(email_type, email_type),
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

def save_output(app_dir: Path, meta: dict, email_type: str, contact_name: str,
                raw_output: str, provider: str) -> Path:
    from datetime import date
    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    today    = date.today().isoformat()
    type_label = EMAIL_TYPE_LABEL.get(email_type, email_type)

    lines = [
        f"# Recruiter Email — {company}",
        f"*{position} · Type: {type_label} · Generated: {today} · AI: {provider}*",
        "",
    ]
    if contact_name:
        lines += [f"**To:** {contact_name}", ""]

    lines += ["---", "", raw_output.strip(), ""]

    lines += [
        "---",
        "## Tips",
        "",
        "- Send from your personal email, not a generic one",
        "- Best time: Tuesday–Thursday, 8–10am recipient timezone",
        "- Attach CV as PDF (not link) for cold emails",
        "- Follow up once after 5 business days if no reply",
        "- BCC yourself for tracking",
        "",
    ]

    out_path = app_dir / "recruiter-email.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate personalised recruiter outreach emails"
    )
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument(
        "--type", choices=["cold", "follow-up", "post-apply"], default="cold",
        dest="email_type",
        help="Email type (default: cold)"
    )
    parser.add_argument(
        "--contact", default="",
        help="Contact name to address"
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

    cv_src = app_dir / "cv-tailored.yml"
    if not cv_src.exists():
        cv_src = REPO_ROOT / "data" / "cv.yml"
    cv_data = {}
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}

    job_text      = _read_file(app_dir / "job.txt")
    research_text = _read_file(app_dir / "company-research.md")

    contact_name = args.contact
    if not contact_name:
        import re
        contacts_md = _read_file(app_dir / "contacts.md", 500)
        m = re.search(r"Primary contact:\s*(.+?)\s*<", contacts_md)
        if m:
            contact_name = m.group(1).strip()

    type_label = EMAIL_TYPE_LABEL.get(args.email_type, args.email_type)
    print(f"✉️  Generating recruiter email — {company}")
    print(f"   Type: {type_label}")
    if contact_name:
        print(f"   To: {contact_name}")
    print(f"   AI: {args.ai}...")
    print()

    prompt     = build_prompt(meta, args.email_type, contact_name, job_text, research_text,
                             cv_data=cv_data)
    raw_output = call_ai(prompt, args.ai, api_key, temperature=0.5, max_tokens=2048)

    out_path = save_output(app_dir, meta, args.email_type, contact_name, raw_output, args.ai)

    print(raw_output.strip())
    print(f"\n✅ Saved to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
