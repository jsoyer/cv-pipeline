#!/usr/bin/env python3
"""
Generate follow-up email templates for stale applications.

Usage:
    scripts/followup.py [--days N] [--name APP_NAME]

Options:
    --days N       Days threshold for stale applications (default: 14)
    --name NAME    Generate for a specific application only

Without --name: scans all applications, prints templates for those > N days old
  with no terminal outcome (not rejected/offer/ghosted), saves followup-templates.md

With --name: generates a single follow-up for the specified application,
  saves to applications/NAME/followup.md
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

TERMINAL_OUTCOMES = {"offer", "rejected", "ghosted"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_meta(app_dir: Path) -> dict:
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _pr_merged_date(app_name: str):
    """
    Get the PR merge date for apply/APP_NAME branch using gh CLI.
    Returns datetime or None.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "list",
             "--head", f"apply/{app_name}",
             "--state", "merged",
             "--json", "mergedAt",
             "--jq", ".[0].mergedAt"],
            capture_output=True, text=True, timeout=15, cwd=_REPO_ROOT,
        )
        merged_at = result.stdout.strip()
        if merged_at and merged_at != "null":
            # GitHub returns ISO 8601: 2026-02-10T14:30:00Z
            return datetime.fromisoformat(merged_at.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass
    return None


def _application_date(app_dir: Path, meta: dict) -> datetime | None:
    """
    Best-effort determination of when the application was submitted.
    Priority: PR merge date > meta.yml created > folder name prefix.
    """
    # 1. PR merge date
    dt = _pr_merged_date(app_dir.name)
    if dt:
        return dt

    # 2. meta.yml created field (YYYY-MM or YYYY-MM-DD)
    created = meta.get("created", "")
    if created:
        created_str = str(created)
        for fmt in ("%Y-%m-%d", "%Y-%m"):
            try:
                return datetime.strptime(created_str[:len(fmt)], fmt[:len(created_str)])
            except ValueError:
                continue

    # 3. Folder name prefix
    import re
    m = re.match(r"(\d{4}-\d{2})", app_dir.name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m")
        except ValueError:
            pass

    return None


def _is_stale(app_dir: Path, meta: dict, days_threshold: int) -> tuple:
    """
    Returns (is_stale, applied_date, days_elapsed).
    """
    outcome = meta.get("outcome", "")
    if outcome in TERMINAL_OUTCOMES:
        return False, None, 0

    applied_date = _application_date(app_dir, meta)
    if not applied_date:
        return False, None, 0

    days_elapsed = (datetime.now() - applied_date).days
    return days_elapsed >= days_threshold, applied_date, days_elapsed


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

def _generate_template(app_dir: Path, meta: dict, days_elapsed: int, applied_date: datetime) -> str:
    company  = meta.get("company",  app_dir.name)
    position = meta.get("position", "the position")
    outcome  = meta.get("outcome",  "")

    stage_note = ""
    if outcome == "interview":
        stage_note = f"\n> **Note**: This application is at the interview stage — adapt as a post-interview check-in."

    applied_str = applied_date.strftime("%B %d, %Y") if applied_date else "recently"

    return f"""## {company} — {position}
*Applied: {applied_str} ({days_elapsed} days ago){stage_note}*

**Subject:** Following up on my application for {position} at {company}

```
Dear [Hiring Manager / Recruiter name],

I wanted to follow up on my application for the {position} role at {company},
which I submitted on {applied_str}. I remain genuinely excited about the
opportunity to bring my experience in [key skill from job description] to
the team.

I'd love to learn more about the selection timeline and whether there's
any additional information I can provide. I'm happy to schedule a call
at your convenience.

Thank you for your time and consideration.

Best regards,
Jérôme Soyer
```

"""


def _generate_single(app_dir: Path) -> str:
    meta = load_meta(app_dir)
    company  = meta.get("company",  app_dir.name)
    position = meta.get("position", "the position")
    applied_date = _application_date(app_dir, meta)
    days_elapsed = (datetime.now() - applied_date).days if applied_date else 0
    applied_str = applied_date.strftime("%B %d, %Y") if applied_date else "recently"

    return f"""# Follow-Up Email — {company}

*Application: {app_dir.name}*
*Generated: {datetime.now().strftime("%Y-%m-%d")}*
*Applied: {applied_str} ({days_elapsed} days ago)*

---

**Subject:** Following up on my application for {position} at {company}

```
Dear [Hiring Manager / Recruiter name],

I wanted to follow up on my application for the {position} role at {company},
which I submitted on {applied_str}. I remain genuinely excited about the
opportunity to bring my experience in [key skill from job description] to
the team.

I'd love to learn more about the selection timeline and whether there's
any additional information I can provide. I'm happy to schedule a call
at your convenience.

Thank you for your time and consideration.

Best regards,
Jérôme Soyer
```

## Tips
- Personalize the [key skill] placeholder with something from job.txt
- If you have a contact name, use it instead of "Hiring Manager"
- Send Monday–Thursday, 9–11am recipient's timezone
- Maximum 2 follow-ups (this one + one more 10 days later)
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate follow-up email templates for stale applications"
    )
    parser.add_argument(
        "--days", type=int, default=14,
        help="Days threshold for stale applications (default: 14)"
    )
    parser.add_argument(
        "--name", type=str, default="",
        metavar="APP_NAME",
        help="Generate follow-up for a specific application only"
    )
    args = parser.parse_args()

    # ── Single application mode ────────────────────────────────────────────────
    if args.name:
        app_dir = _REPO_ROOT / "applications" / args.name
        if not app_dir.is_dir():
            print(f"❌ Directory not found: {app_dir}")
            sys.exit(1)

        content = _generate_single(app_dir)
        print(content)

        out_path = app_dir / "followup.md"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Saved to {out_path}")
        return 0

    # ── Bulk scan mode ─────────────────────────────────────────────────────────
    apps_dir = _REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ No applications/ directory found")
        sys.exit(1)

    stale = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        meta = load_meta(d)
        is_stale, applied_date, days_elapsed = _is_stale(d, meta, args.days)
        if is_stale:
            stale.append((d, meta, applied_date, days_elapsed))

    if not stale:
        print(f"✅ No applications older than {args.days} days without a terminal outcome.")
        return 0

    print(f"📬 Follow-Up Templates ({len(stale)} application{'s' if len(stale) != 1 else ''} > {args.days} days)\n")
    print("─" * 60)

    sections = ["# Follow-Up Email Templates\n"]
    sections.append(
        f"*Generated: {datetime.now().strftime('%Y-%m-%d')} "
        f"| Threshold: {args.days} days*\n\n"
        "## Instructions\n"
        "- Send 7–10 days after application if no response\n"
        "- Maximum 2 follow-ups per application\n"
        "- Personalize the [key skill] placeholder\n\n---\n\n"
    )

    for app_dir, meta, applied_date, days_elapsed in stale:
        company = meta.get("company", app_dir.name)
        position = meta.get("position", "")
        print(f"  • {app_dir.name}  ({days_elapsed}d)  {company} — {position}")
        sections.append(_generate_template(app_dir, meta, days_elapsed, applied_date))

    print()
    content = "\n".join(sections)

    out_path = _REPO_ROOT / "followup-templates.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Templates saved to {out_path}")
    print(f"\n💡 For a specific app:  make follow-up NAME=<app-name>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
