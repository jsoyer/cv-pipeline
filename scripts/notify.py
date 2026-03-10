#!/usr/bin/env python3
"""
Notify — Update application status across all tracking systems in one command.

Actions performed:
  1. Update meta.yml (outcome field) + git commit + push
  2. Post to Slack (SLACK_WEBHOOK_URL)
  3. Post to Discord (DISCORD_WEBHOOK_URL)
  4. Update Notion entry (NOTION_TOKEN + NOTION_DATABASE_ID)
  5. Add GitHub PR label (status:interview / status:offer / status:rejected)

Usage:
    scripts/notify.py <app-dir> --status STATUS [--message MSG] [--dry-run]

    STATUS values: applied | interview | offer | rejected | ghosted

Examples:
    scripts/notify.py applications/2026-02-datadog --status interview
    scripts/notify.py applications/2026-02-datadog --status offer --message "€150k + equity"
    scripts/notify.py applications/2026-02-datadog --status rejected --dry-run
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # Handled gracefully per action

from lib.common import load_env, load_meta, REPO_ROOT, require_yaml

yaml = require_yaml()

VALID_STATUSES = {"applied", "interview", "offer", "rejected", "ghosted"}

# GitHub PR label mapping
PR_LABELS = {
    "interview": "status:interview",
    "offer": "status:offer",
    "rejected": "status:rejected",
    "ghosted": "status:rejected",
}

STATUS_EMOJI = {
    "applied": "📤",
    "interview": "🗣️",
    "offer": "🎉",
    "rejected": "❌",
    "ghosted": "👻",
}


def save_meta(app_dir: Path, meta: dict) -> None:
    meta_path = app_dir / "meta.yml"
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def update_meta_yml(app_dir: Path, status: str, message: str, dry_run: bool) -> bool:
    """Update outcome in meta.yml and git commit+push."""
    meta = load_meta(app_dir)
    company = meta.get("company", app_dir.name)
    position = meta.get("position", "")

    old_outcome = meta.get("outcome", "")
    meta["outcome"] = status
    if message:
        meta["notes"] = message

    if dry_run:
        print(f"   [DRY] meta.yml: outcome={status}" + (f", notes={message}" if message else ""))
        return True

    save_meta(app_dir, meta)
    print(f"   ✅ meta.yml updated: outcome={status}")

    # Git commit + push
    try:
        subprocess.run(
            ["git", "add", str(app_dir / "meta.yml")],
            cwd=REPO_ROOT, check=True, capture_output=True,
        )
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=REPO_ROOT, capture_output=True,
        )
        if diff.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", f"notify: {app_dir.name} → {status}"],
                cwd=REPO_ROOT, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "push"],
                cwd=REPO_ROOT, check=True, capture_output=True,
            )
            print(f"   ✅ Committed and pushed")
        else:
            print(f"   ℹ️  No changes to commit (outcome was already '{old_outcome}')")
    except subprocess.CalledProcessError as e:
        print(f"   ⚠️  Git error: {e}")

    return True


def _slack_blocks(company: str, position: str, status: str, message: str, app_name: str) -> dict:
    """Build a Slack Block Kit payload for rich notification formatting."""
    emoji = STATUS_EMOJI.get(status, "📋")
    color_map = {
        "applied":   "#3B82F6",
        "interview": "#EAB308",
        "offer":     "#22C55E",
        "rejected":  "#EF4444",
        "ghosted":   "#94A3B8",
    }
    color = color_map.get(status, "#94A3B8")

    header_text = f"{emoji} *{company}* — Status updated to *{status.upper()}*"
    fields = [
        {"type": "mrkdwn", "text": f"*Position*\n{position}"},
        {"type": "mrkdwn", "text": f"*Application*\n`{app_name}`"},
    ]
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header_text}},
        {"type": "section", "fields": fields},
    ]
    if message:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"💬 _{message}_"}})
    blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"CV Pipeline • {app_name}"}]})

    return {
        "text": f"{emoji} {company} → {status.upper()}",
        "attachments": [{"color": color, "blocks": blocks}],
    }


def notify_slack(company: str, position: str, status: str, message: str,
                 app_name: str, dry_run: bool) -> bool:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        print("   ⚠️  Slack: SLACK_WEBHOOK_URL not set — skipping")
        return False
    if requests is None:
        print("   ⚠️  Slack: requests not installed — skipping")
        return False

    payload = _slack_blocks(company, position, status, message, app_name)

    if dry_run:
        print(f"   [DRY] Slack: {payload['text'][:80]}…")
        return True

    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code == 200:
            print("   ✅ Slack notified")
            return True
        else:
            print(f"   ⚠️  Slack error: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ⚠️  Slack error: {e}")
        return False


def notify_discord(company: str, position: str, status: str, message: str,
                   app_name: str, dry_run: bool) -> bool:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook:
        print("   ⚠️  Discord: DISCORD_WEBHOOK_URL not set — skipping")
        return False
    if requests is None:
        print("   ⚠️  Discord: requests not installed — skipping")
        return False

    emoji = STATUS_EMOJI.get(status, "📋")
    color_map = {"applied": 0x3b82f6, "interview": 0xeab308, "offer": 0x22c55e,
                 "rejected": 0xef4444, "ghosted": 0x94a3b8}
    color = color_map.get(status, 0x94a3b8)

    embed = {
        "title": f"{emoji} {company} — {position}",
        "description": f"Status updated to **{status.upper()}**" + (f"\n> {message}" if message else ""),
        "color": color,
        "footer": {"text": app_name},
    }
    payload = {"embeds": [embed]}

    if dry_run:
        print(f"   [DRY] Discord: {company} → {status}")
        return True

    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            print("   ✅ Discord notified")
            return True
        else:
            print(f"   ⚠️  Discord error: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"   ⚠️  Discord error: {e}")
        return False


def update_notion(company: str, position: str, status: str,
                  app_name: str, dry_run: bool) -> bool:
    token = os.environ.get("NOTION_TOKEN", "")
    db_id = os.environ.get("NOTION_DATABASE_ID", "") or os.environ.get("NOTION_DB_ID", "")
    if not token or not db_id:
        print("   ⚠️  Notion: NOTION_TOKEN or NOTION_DATABASE_ID not set — skipping")
        return False
    if requests is None:
        print("   ⚠️  Notion: requests not installed — skipping")
        return False

    # Status mapping to Notion select values
    notion_status_map = {
        "applied": "Applied",
        "interview": "Interview",
        "offer": "Offer",
        "rejected": "Rejected",
        "ghosted": "Ghosted",
    }
    notion_status = notion_status_map.get(status, status.title())

    if dry_run:
        print(f"   [DRY] Notion: search {company} → update status to {notion_status}")
        return True

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    try:
        # Search for existing page by company name
        search_resp = requests.post(
            "https://api.notion.com/v1/databases/" + db_id + "/query",
            headers=headers,
            json={"filter": {"property": "Company", "title": {"contains": company}}},
            timeout=15,
        )
        if search_resp.status_code != 200:
            print(f"   ⚠️  Notion search error: HTTP {search_resp.status_code}")
            return False

        results = search_resp.json().get("results", [])
        if not results:
            print(f"   ⚠️  Notion: no entry found for '{company}' — skipping")
            return False

        page_id = results[0]["id"]
        update_resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={"properties": {"Status": {"select": {"name": notion_status}}}},
            timeout=15,
        )
        if update_resp.status_code == 200:
            print(f"   ✅ Notion updated: {company} → {notion_status}")
            return True
        else:
            print(f"   ⚠️  Notion update error: HTTP {update_resp.status_code}")
            return False
    except Exception as e:
        print(f"   ⚠️  Notion error: {e}")
        return False


def add_github_label(app_name: str, status: str, dry_run: bool) -> bool:
    label = PR_LABELS.get(status)
    if not label:
        print(f"   ℹ️  GitHub: no label mapping for status '{status}' — skipping")
        return True

    branch = f"apply/{app_name}"

    if dry_run:
        print(f"   [DRY] GitHub: gh pr edit {branch} --add-label '{label}'")
        return True

    try:
        result = subprocess.run(
            ["gh", "pr", "edit", branch, "--add-label", label],
            capture_output=True, text=True, timeout=15, cwd=REPO_ROOT,
        )
        if result.returncode == 0:
            print(f"   ✅ GitHub PR label added: {label}")
            return True
        else:
            # PR might not exist or branch is different
            err = result.stderr.strip()
            if "no pull requests found" in err.lower() or "could not find" in err.lower():
                print(f"   ℹ️  GitHub: no open PR found for branch {branch} — skipping")
            else:
                print(f"   ⚠️  GitHub error: {err[:100]}")
            return False
    except Exception as e:
        print(f"   ⚠️  GitHub error: {e}")
        return False


def parse_args():
    parser = argparse.ArgumentParser(
        description="Notify — Update application status across all tracking systems in one command. "
                    "Updates meta.yml, posts to Slack/Discord, updates Notion, and adds a GitHub PR label.",
        epilog=f"STATUS values: {' | '.join(sorted(VALID_STATUSES))}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "app_dir",
        metavar="app-dir",
        help="Path to the application directory (e.g. applications/2026-02-datadog)",
    )
    parser.add_argument(
        "--status",
        required=True,
        choices=sorted(VALID_STATUSES),
        help="New status to record",
    )
    parser.add_argument(
        "--message",
        metavar="MSG",
        default="",
        help="Optional note to store in meta.yml and include in notifications",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Preview all actions without making any changes",
    )
    args = parser.parse_args()
    return args.app_dir, args.status.lower(), args.message, args.dry_run


def main():
    app_dir_str, status, message, dry_run = parse_args()

    app_dir = Path(app_dir_str)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    meta = load_meta(app_dir)
    company = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    app_name = app_dir.name
    emoji = STATUS_EMOJI.get(status, "📋")

    load_env()

    mode = " [DRY RUN]" if dry_run else ""
    print(f"{emoji} Notifying: {company} — {status.upper()}{mode}")
    if position:
        print(f"   Position: {position}")
    if message:
        print(f"   Message:  {message}")
    print()

    # Run all actions
    print("📋 Updating meta.yml...")
    update_meta_yml(app_dir, status, message, dry_run)
    print()

    print("💬 Notifying channels...")
    notify_slack(company, position, status, message, app_name, dry_run)
    notify_discord(company, position, status, message, app_name, dry_run)
    update_notion(company, position, status, app_name, dry_run)
    add_github_label(app_name, status, dry_run)
    print()

    print(f"✅ Done: {app_name} → {status}")
    if message:
        print(f"   Note: {message}")
    print()
    print(f"💡 Next steps:")
    if status == "interview":
        print(f"   make prep NAME={app_name}")
        print(f"   make thankyou NAME={app_name}")
    elif status == "offer":
        print(f"   make negotiate NAME={app_name}")
    elif status == "rejected":
        print(f"   make effectiveness")

    return 0


if __name__ == "__main__":
    sys.exit(main())
