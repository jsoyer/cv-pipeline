#!/usr/bin/env python3
"""
Generate a LinkedIn post using AI.

Types:
  open-to-work    — Announce you're looking for new opportunities (default)
  transition      — Announce a new role / career move
  achievement     — Celebrate a milestone or win
  insight         — Thought leadership post from domain expertise

LinkedIn best practices built in:
  - Hook line ≤ 200 chars (critical for "see more" threshold)
  - Total ≤ 1 300 chars (optimal engagement range)
  - Short paragraphs (1-3 sentences)
  - 3-5 relevant hashtags
  - No emojis spam

Reads: data/cv.yml (or cv-tailored.yml if app-dir provided), meta.yml

Output: data/linkedin-post.md (or applications/NAME/linkedin-post.md)

Usage:
    scripts/linkedin-post.py [<app-dir>] [--type TYPE] [--topic "..."] [--ai PROVIDER]

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

POST_TYPE_LABEL = {
    "open-to-work": "Open to Opportunities",
    "transition":   "Career Transition / New Role",
    "achievement":  "Milestone / Achievement",
    "insight":      "Thought Leadership / Insight",
}



PROMPT_TEMPLATE = """\
You are a personal branding specialist writing a LinkedIn post for a senior technology \
sales leader. Write in a direct, human, first-person voice — not corporate, not humble-braggy.

## Author
Jérôme Soyer — Regional VP of Sales Engineering at Varonis, Paris.
15+ years in technology sales, SE leadership, cybersecurity/data/SaaS.
Scaled SE organisations to 50+ HC. Drives ARR growth. French native, fluent English.

## Post Type
{post_type_label}

## Additional Context / Topic
{topic_section}

## CV Profile (for reference)
{profile_excerpt}

## Recent Achievements (for reference)
{achievements_excerpt}

## LinkedIn Post Rules
- **Hook (line 1):** ≤ 140 chars — bold claim, surprising stat, or direct question
  This is the ONLY line visible before "see more" — make it impossible to skip
- **Body:** 150-800 chars — short paragraphs (2-3 sentences max each), line breaks between
- **Total post:** ≤ 1 300 chars including hashtags
- **Tone:** Direct, confident, authentic — no "I'm excited to share", no "humbled", \
  no "thrilled", no "passionate"
- **No** bullet point walls — prose with occasional line breaks only
- **CTA:** One clear action at the end (reply, connect, message, share)
- **Hashtags:** 3-5 relevant, lowercase, at the very end on their own line
- **No emojis** unless a single one genuinely adds value

## Post-type specific guidance
{type_guidance}

## Output Format

Return ONLY the post text — no intro, no commentary, no "Here is your post:".
Start directly with the hook line.

---POST---
[post text + hashtags]
---CHAR COUNT: N---
"""

TYPE_GUIDANCE = {
    "open-to-work": """\
- Mention you're exploring new opportunities without sounding desperate
- Specify: what level of role, what domain, what geography
- Mention what you bring (the value, not just the title)
- Avoid "open to work" banner clichés — be specific about what you want""",

    "transition": """\
- Announce the move with genuine energy, not corporate boilerplate
- One sentence on what attracted you to the new role/company
- One insight about what you learned in the previous role
- Tag the new company if appropriate (use @CompanyName)""",

    "achievement": """\
- Lead with the outcome/number, not the process
- Give just enough context for non-insiders to understand
- Credit the team if relevant (briefly)
- End with a lesson or insight""",

    "insight": """\
- Strong POV — take a real stance, don't hedge
- Back it up with one specific example or data point
- Acknowledge the counterargument briefly
- End with a question to drive comments""",
}


def main():
    parser = argparse.ArgumentParser(description="Generate a LinkedIn post using AI")
    parser.add_argument("app_dir", nargs="?", default="",
                        help="Application directory (optional)")
    parser.add_argument("--type", dest="post_type",
                        choices=list(POST_TYPE_LABEL), default="open-to-work",
                        help="Post type (default: open-to-work)")
    parser.add_argument("--topic", default="",
                        help="Additional context or specific topic/achievement to cover")
    parser.add_argument("--ai", default="gemini", choices=sorted(VALID_PROVIDERS))
    args = parser.parse_args()

    load_env()

    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set")
        sys.exit(1)

    # Load CV
    app_dir  = None
    app_name = ""
    if args.app_dir:
        app_dir = Path(args.app_dir)
        if not app_dir.is_dir():
            app_dir = REPO_ROOT / "applications" / Path(args.app_dir).name
        app_name = app_dir.name if app_dir.is_dir() else ""

    cv_src = (app_dir / "cv-tailored.yml" if app_dir and (app_dir / "cv-tailored.yml").exists()
              else REPO_ROOT / "data" / "cv.yml")
    cv_data = {}
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}

    profile = cv_data.get("profile", "")
    profile_excerpt = re.sub(r"\*\*(.+?)\*\*", r"\1",
                              profile if isinstance(profile, str) else "")[:500]

    wins = cv_data.get("key_wins", [])
    ach_lines = []
    for w in wins[:4]:
        if isinstance(w, dict):
            title = re.sub(r"\*\*(.+?)\*\*", r"\1", w.get("title", ""))
            text  = re.sub(r"\*\*(.+?)\*\*", r"\1", w.get("text", ""))
            ach_lines.append(f"• {title}: {text}")
    achievements_excerpt = "\n".join(ach_lines) or "(no key_wins found)"

    topic_section = f"**Specific topic:** {args.topic}" if args.topic else "(none specified — use CV context)"

    type_label   = POST_TYPE_LABEL[args.post_type]
    type_guidance = TYPE_GUIDANCE.get(args.post_type, "")

    print(f"📢 Generating LinkedIn post — {type_label}")
    if app_name:
        print(f"   Context: {app_name}")
    print(f"   AI: {args.ai}...")

    prompt = PROMPT_TEMPLATE.format(
        post_type_label=type_label,
        topic_section=topic_section,
        profile_excerpt=profile_excerpt,
        achievements_excerpt=achievements_excerpt,
        type_guidance=type_guidance,
    )

    raw = call_ai(prompt, args.ai, api_key, temperature=0.6, max_tokens=2048)

    # Extract just the post text
    post_text = raw.strip()
    m = re.search(r"---POST---\s*\n(.*?)(?:---CHAR COUNT.*)?$", post_text, re.DOTALL)
    if m:
        post_text = m.group(1).strip()
        post_text = re.sub(r"---CHAR COUNT.*$", "", post_text, flags=re.MULTILINE).strip()

    char_count = len(post_text)
    if char_count > 1300:
        print(f"⚠️  Post is {char_count} chars (LinkedIn optimal ≤ 1 300) — consider trimming")

    from datetime import date
    today = date.today().isoformat()
    out_lines = [
        f"# LinkedIn Post — {type_label}",
        f"*Generated: {today} · AI: {args.ai}*",
        "",
        f"> {char_count} characters",
        "",
        "---",
        "",
        post_text,
        "",
        "---",
        "## Tips",
        "",
        "- Post Tuesday–Thursday, 8–10am your timezone",
        "- First comment from your own account boosts reach",
        "- Reply to every comment within the first hour",
        "- Pin if it's an open-to-work or transition announcement",
        "",
    ]

    if app_dir and app_dir.is_dir():
        out_path = app_dir / "linkedin-post.md"
    else:
        out_path = REPO_ROOT / "data" / "linkedin-post.md"

    out_path.write_text("\n".join(out_lines), encoding="utf-8")

    print()
    print(post_text)
    print(f"\n✅ Saved to {out_path}  ({char_count} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
