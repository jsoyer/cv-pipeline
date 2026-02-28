#!/usr/bin/env python3
"""
Cron-friendly deadline and stale-application alert.

Checks:
  1. Applications with deadline within --days days (default: 3)
  2. Applications stale > --stale days with no terminal outcome (default: 14)

Sends condensed alert to Slack and/or Discord if webhooks are configured.
Designed for cron: silent if nothing to report, non-zero exit if alerts sent.

Usage:
    scripts/deadline-alert.py [--days N] [--stale N] [--dry-run] [--quiet]

Cron example (every 6 hours):
    0 */6 * * * cd /path/to/CV && python3 scripts/deadline-alert.py --quiet

Exit codes:
    0 = nothing to report
    1 = alerts were sent (or would be sent with --dry-run)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

TERMINAL_OUTCOMES = {"offer", "rejected", "ghosted"}


def load_env():
    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def load_meta(app_dir: Path) -> dict:
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return {}
    with open(meta_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_date(date_str) -> datetime | None:
    if not date_str:
        return None
    s = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _app_created_date(app_dir: Path, meta: dict) -> datetime | None:
    dt = _parse_date(meta.get("created", ""))
    if dt:
        return dt
    m = re.match(r"(\d{4}-\d{2})", app_dir.name)
    if m:
        return _parse_date(m.group(1))
    return None


def _send_slack(text: str, webhook: str, dry_run: bool) -> bool:
    if dry_run:
        print(f"   [DRY] Slack: {text[:80]}")
        return True
    if not HAS_REQUESTS:
        return False
    try:
        resp = requests.post(webhook, json={"text": text}, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def _send_discord(text: str, webhook: str, dry_run: bool) -> bool:
    if dry_run:
        print(f"   [DRY] Discord: {text[:80]}")
        return True
    if not HAS_REQUESTS:
        return False
    try:
        resp = requests.post(webhook, json={"content": text}, timeout=10)
        return resp.status_code in (200, 204)
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Cron-friendly deadline and stale-application alert"
    )
    parser.add_argument(
        "--days", type=int, default=3,
        help="Alert if deadline within N days (default: 3)"
    )
    parser.add_argument(
        "--stale", type=int, default=14,
        help="Alert if application stale > N days (default: 14)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print alerts without sending to webhooks"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress terminal output if no alerts (for cron)"
    )
    args = parser.parse_args()

    load_env()

    apps_dir = _REPO_ROOT / "applications"
    if not apps_dir.exists():
        return 0

    now = datetime.now()
    dl_cutoff    = now + timedelta(days=args.days)
    stale_cutoff = now - timedelta(days=args.stale)

    deadline_alerts = []
    stale_alerts    = []

    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        meta    = load_meta(d)
        company = meta.get("company", d.name)
        outcome = meta.get("outcome", "")

        # Deadline check (regardless of outcome)
        dl = _parse_date(meta.get("deadline", ""))
        if dl and now <= dl <= dl_cutoff:
            days_left = (dl - now).days
            deadline_alerts.append({
                "name":      d.name,
                "company":   company,
                "deadline":  dl.strftime("%Y-%m-%d"),
                "days_left": days_left,
            })

        # Stale check
        if outcome not in TERMINAL_OUTCOMES:
            created = _app_created_date(d, meta)
            if created and created <= stale_cutoff:
                days_elapsed = (now - created).days
                stale_alerts.append({
                    "name":         d.name,
                    "company":      company,
                    "days_elapsed": days_elapsed,
                    "outcome":      outcome,
                })

    if not deadline_alerts and not stale_alerts:
        if not args.quiet:
            print("✅ No deadline or stale alerts.")
        return 0

    # Build alert message
    lines = [f"🔔 *CV Alert — {now.strftime('%Y-%m-%d %H:%M')}*"]

    if deadline_alerts:
        lines.append(f"\n⚠️ *Deadlines in ≤{args.days} days:*")
        for a in deadline_alerts:
            urgency = "🔴" if a["days_left"] <= 1 else ("🟡" if a["days_left"] <= 2 else "🟠")
            lines.append(
                f"  {urgency} {a['company']} — deadline {a['deadline']} "
                f"({a['days_left']}d)  `make app NAME={a['name']}`"
            )

    if stale_alerts:
        lines.append(f"\n⏳ *Stale applications (>{args.stale}d, no response):*")
        for a in stale_alerts[:5]:
            lines.append(
                f"  • {a['company']} ({a['days_elapsed']}d)  "
                f"`make follow-up NAME={a['name']}`"
            )
        if len(stale_alerts) > 5:
            lines.append(f"  … and {len(stale_alerts) - 5} more")

    alert_text = "\n".join(lines)

    # Print to terminal
    if not args.quiet or args.dry_run:
        print(alert_text)
        print()
        if deadline_alerts:
            print(f"⚠️  {len(deadline_alerts)} deadline alert(s)")
        if stale_alerts:
            print(f"⏳ {len(stale_alerts)} stale application(s)")

    # Send to webhooks
    slack_webhook   = os.environ.get("SLACK_WEBHOOK_URL", "")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    sent = False

    if slack_webhook:
        ok = _send_slack(alert_text, slack_webhook, args.dry_run)
        if not args.quiet:
            print(f"   {'✅ Slack' if ok else '⚠️  Slack failed'}")
        sent = sent or ok

    if discord_webhook:
        ok = _send_discord(alert_text, discord_webhook, args.dry_run)
        if not args.quiet:
            print(f"   {'✅ Discord' if ok else '⚠️  Discord failed'}")
        sent = sent or ok

    if not slack_webhook and not discord_webhook and not args.quiet:
        print("ℹ️  No webhooks configured — set SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL in .env")

    # Non-zero exit = alerts were raised (useful for cron monitoring)
    return 1


if __name__ == "__main__":
    sys.exit(main())
