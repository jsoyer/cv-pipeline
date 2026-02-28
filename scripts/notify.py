#!/usr/bin/env python3
"""
Notify — Update application status across all tracking systems in one command.

Actions performed:
  1. Update meta.yml (outcome field) + git commit + push
  2. Post to Slack (SLACK_WEBHOOK_URL)
  3. Post to Discord (DISCORD_WEBHOOK_URL)
  4. Update Notion entry (NOTION_TOKEN + NOTION_DB_ID)
  5. Add GitHub PR label (status:interview / status:offer / status:rejected)

Usage:
    scripts/notify.py <app-dir> --status STATUS [--message MSG] [--dry-run]

    STATUS values: applied | interview | offer | rejected | ghosted

Examples:
    scripts/notify.py applications/2026-02-datadog --status interview
    scripts/notify.py applications/2026-02-datadog --status offer --message "€150k + equity"
    scripts/notify.py applications/2026-02-datadog --status rejected --dry-run
"""

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None  # Handled gracefully per action

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

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


def load_meta(app_dir: Path) -> dict:
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


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
            cwd=_REPO_ROOT, check=True, capture_output=True,
        )
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=_REPO_ROOT, capture_output=True,
        )
        if diff.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", f"notify: {app_dir.name} → {status}"],
                cwd=_REPO_ROOT, check=True, capture_output=True,
            )
            subprocess.run(
                ["git", "push"],
                cwd=_REPO_ROOT, check=True, capture_output=True,
            )
            print(f"   ✅ Committed and pushed")
        else:
            print(f"   ℹ️  No changes to commit (outcome was already '{old_outcome}')")
    except subprocess.CalledProcessError as e:
        print(f"   ⚠️  Git error: {e}")

    return True


def notify_slack(company: str, position: str, status: str, message: str,
                 app_name: str, dry_run: bool) -> bool:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        print("   ⚠️  Slack: SLACK_WEBHOOK_URL not set — skipping")
        return False
    if requests is None:
        print("   ⚠️  Slack: requests not installed — skipping")
        return False

    emoji = STATUS_EMOJI.get(status, "📋")
    text = f"{emoji} *{company}* — {position}\nStatus: *{status.upper()}*"
    if message:
        text += f"\n> {message}"
    text += f"\n_Application: {app_name}_"

    payload = {"text": text}

    if dry_run:
        print(f"   [DRY] Slack: {text[:80]}…")
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
    db_id = os.environ.get("NOTION_DB_ID", "")
    if not token or not db_id:
        print("   ⚠️  Notion: NOTION_TOKEN or NOTION_DB_ID not set — skipping")
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
            capture_output=True, text=True, timeout=15, cwd=_REPO_ROOT,
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
    args = sys.argv[1:]
    app_dir_str = None
    status = None
    message = ""
    dry_run = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif arg == "--status" and i + 1 < len(args):
            status = args[i + 1].lower()
            i += 1
        elif arg == "--message" and i + 1 < len(args):
            message = args[i + 1]
            i += 1
        elif arg == "--dry-run":
            dry_run = True
        elif not arg.startswith("-") and app_dir_str is None:
            app_dir_str = arg
        i += 1

    return app_dir_str, status, message, dry_run


def main():
    app_dir_str, status, message, dry_run = parse_args()

    if not app_dir_str:
        print("Usage: scripts/notify.py <app-dir> --status STATUS [--message MSG] [--dry-run]")
        print(f"STATUS: {' | '.join(sorted(VALID_STATUSES))}")
        sys.exit(1)

    if not status:
        print("❌ --status is required")
        print(f"   Values: {' | '.join(sorted(VALID_STATUSES))}")
        sys.exit(1)

    if status not in VALID_STATUSES:
        print(f"❌ Invalid status: '{status}'")
        print(f"   Valid values: {' | '.join(sorted(VALID_STATUSES))}")
        sys.exit(1)

    app_dir = Path(app_dir_str)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    meta = load_meta(app_dir)
    company = meta.get("company", app_dir.name)
    position = meta.get("position", "")
    app_name = app_dir.name
    emoji = STATUS_EMOJI.get(status, "📋")

    # Load .env if present
    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

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
