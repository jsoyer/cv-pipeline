#!/usr/bin/env python3
"""
Weekly pipeline digest — markdown summary + optional Slack/Discord.

Sections:
  1. Header (date, totals)
  2. Pipeline Funnel (counts by outcome/stage)
  3. Recent Activity (last 7 days)
  4. Stale Applications (>N days, no terminal outcome)
  5. Upcoming Deadlines (next 14 days)
  6. ATS Score Summary (avg, best, worst)
  7. Action Items

Output: digest.md in repo root + Slack/Discord if webhooks configured.

Usage:
    scripts/digest.py [--no-send] [--days N] [--json]

Options:
    --no-send    Generate digest.md only, skip Slack/Discord
    --days N     Stale threshold in days (default: 14)
    --json       Dump digest data as JSON
"""

import argparse
import json
import os
import re
import subprocess
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

OUTCOME_EMOJI = {
    "applied":   "📤",
    "interview": "🗣️",
    "offer":     "🎉",
    "rejected":  "❌",
    "ghosted":   "👻",
    "":          "📝",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    try:
        with open(meta_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


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


def _get_ats_score(app_dir: Path) -> float | None:
    if not (app_dir / "job.txt").exists():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "ats-score.py"), str(app_dir), "--json"],
            capture_output=True, text=True, timeout=30, cwd=_REPO_ROOT,
        )
        data = json.loads(result.stdout)
        return data.get("score")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_apps() -> list:
    apps_dir = _REPO_ROOT / "applications"
    if not apps_dir.exists():
        return []
    apps = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        meta = load_meta(d)
        meta_path = d / "meta.yml"
        apps.append({
            "name": d.name,
            "company": meta.get("company", d.name),
            "position": meta.get("position", ""),
            "outcome": meta.get("outcome", ""),
            "deadline": _parse_date(meta.get("deadline", "")),
            "created": _app_created_date(d, meta),
            "meta_mtime": datetime.fromtimestamp(meta_path.stat().st_mtime)
                          if meta_path.exists() else None,
            "has_job_txt": (d / "job.txt").exists(),
        })
    return apps


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _pipeline_funnel(apps: list) -> tuple:
    counts = {}
    for a in apps:
        outcome = a["outcome"] or ""
        counts[outcome] = counts.get(outcome, 0) + 1

    total = len(apps)
    order = ["", "applied", "interview", "offer", "rejected", "ghosted"]
    rows = []
    data = {"total": total, "by_outcome": {}}
    for outcome in order:
        n = counts.get(outcome, 0)
        if n == 0:
            continue
        emoji = OUTCOME_EMOJI.get(outcome, "📝")
        label = outcome.title() if outcome else "Pending"
        bar = "█" * n
        rows.append(f"| {emoji} {label:<12} | {n:>3} | {bar} |")
        data["by_outcome"][outcome or "pending"] = n

    section = (
        "## Pipeline Funnel\n\n"
        f"*Total: {total} application{'s' if total != 1 else ''}*\n\n"
        "| Stage        | N   | Bar |\n"
        "|:-------------|:----|:----|\n"
        + "\n".join(rows) + "\n"
    )
    return section, data


def _recent_activity(apps: list, days: int = 7) -> tuple:
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for a in apps:
        mtime = a.get("meta_mtime") or a.get("created")
        if mtime and mtime >= cutoff:
            recent.append(a)

    lines = [f"## Recent Activity (last {days} days)\n"]
    if not recent:
        lines.append("*No activity in the last 7 days.*\n")
    else:
        lines.append("| Application | Company | Status |")
        lines.append("|:------------|:--------|:-------|")
        for a in recent:
            emoji = OUTCOME_EMOJI.get(a["outcome"], "📝")
            status = f"{emoji} {a['outcome'].title()}" if a["outcome"] else "📝 Pending"
            lines.append(f"| `{a['name']}` | {a['company']} | {status} |")
        lines.append("")
    return "\n".join(lines) + "\n", [a["name"] for a in recent]


def _stale_applications(apps: list, days_threshold: int = 14) -> tuple:
    cutoff = datetime.now() - timedelta(days=days_threshold)
    stale = []
    for a in apps:
        if a["outcome"] in TERMINAL_OUTCOMES:
            continue
        created = a.get("created")
        if created and created <= cutoff:
            days_elapsed = (datetime.now() - created).days
            stale.append((a, days_elapsed))

    stale.sort(key=lambda x: -x[1])  # oldest first

    lines = [f"## Stale Applications (>{days_threshold} days)\n"]
    if not stale:
        lines.append("*No stale applications — great job staying on top of things!*\n")
    else:
        lines.append("| Application | Company | Days | Action |")
        lines.append("|:------------|:--------|:-----|:-------|")
        for a, days in stale:
            action = f"`make follow-up NAME={a['name']}`"
            lines.append(f"| `{a['name']}` | {a['company']} | {days}d | {action} |")
        lines.append("")
    return "\n".join(lines) + "\n", [a["name"] for a, _ in stale]


def _upcoming_deadlines(apps: list, days: int = 14) -> tuple:
    now = datetime.now()
    cutoff = now + timedelta(days=days)
    upcoming = []
    for a in apps:
        dl = a.get("deadline")
        if dl and now <= dl <= cutoff:
            days_left = (dl - now).days
            upcoming.append((a, days_left))
    upcoming.sort(key=lambda x: x[1])

    lines = [f"## Upcoming Deadlines (next {days} days)\n"]
    if not upcoming:
        lines.append("*No upcoming deadlines in the next 14 days.*\n")
    else:
        lines.append("| Application | Company | Deadline | Days Left |")
        lines.append("|:------------|:--------|:---------|:----------|")
        for a, days_left in upcoming:
            dl_str = a["deadline"].strftime("%Y-%m-%d")
            urgency = "🔴" if days_left <= 3 else ("🟡" if days_left <= 7 else "🟢")
            lines.append(f"| `{a['name']}` | {a['company']} | {dl_str} | {urgency} {days_left}d |")
        lines.append("")
    return "\n".join(lines) + "\n", [a["name"] for a, _ in upcoming]


def _ats_summary(apps: list) -> tuple:
    scoreable = [a for a in apps if a["has_job_txt"]]
    if not scoreable:
        return "## ATS Score Summary\n\n*No applications with job.txt found.*\n\n", {}

    print(f"\n📊 Computing ATS scores for {len(scoreable)} application(s)...")
    scores = []
    for a in scoreable:
        app_dir = _REPO_ROOT / "applications" / a["name"]
        score = _get_ats_score(app_dir)
        if score is not None:
            scores.append((a, score))
            print(f"   {a['name']}: {score:.1f}%")

    if not scores:
        return "## ATS Score Summary\n\n*Could not compute ATS scores.*\n\n", {}

    avg = sum(s for _, s in scores) / len(scores)
    best = max(scores, key=lambda x: x[1])
    worst = min(scores, key=lambda x: x[1])

    rows = []
    for a, score in sorted(scores, key=lambda x: -x[1]):
        grade = "🟢" if score >= 80 else ("🟡" if score >= 60 else ("🟠" if score >= 40 else "🔴"))
        rows.append(f"| `{a['name']}` | {a['company']} | {score:.1f}% | {grade} |")

    section = (
        "## ATS Score Summary\n\n"
        f"*{len(scores)} scored · Avg: {avg:.1f}% · Best: {best[1]:.1f}% · Worst: {worst[1]:.1f}%*\n\n"
        "| Application | Company | Score | Grade |\n"
        "|:------------|:--------|:------|:------|\n"
        + "\n".join(rows) + "\n"
    )
    data = {
        "avg": round(avg, 1),
        "best": {"name": best[0]["name"], "score": best[1]},
        "worst": {"name": worst[0]["name"], "score": worst[1]},
        "count": len(scores),
    }
    return section, data


def _action_items(stale_names: list, deadline_names: list, apps: list) -> str:
    lines = ["## Action Items\n"]
    items = []
    for name in stale_names[:5]:
        items.append(f"- [ ] Follow up on **{name}** — `make follow-up NAME={name}`")
    for name in deadline_names[:5]:
        items.append(f"- [ ] ⚠️ Deadline approaching — **{name}** — `make app NAME={name}`")
    for a in apps:
        if a["outcome"] == "interview":
            items.append(
                f"- [ ] Interview stage — **{a['name']}** — `make thankyou NAME={a['name']}`"
            )
    if not items:
        lines.append("*No pending action items. 🎉*\n")
    else:
        lines.extend(items)
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Webhook sending
# ---------------------------------------------------------------------------

def _send_slack(text: str, webhook: str) -> bool:
    if not HAS_REQUESTS:
        return False
    try:
        resp = requests.post(webhook, json={"text": text}, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def _send_discord(text: str, webhook: str) -> bool:
    if not HAS_REQUESTS:
        return False
    try:
        resp = requests.post(webhook, json={"content": text}, timeout=10)
        return resp.status_code in (200, 204)
    except Exception:
        return False


def _send_webhooks(apps: list, stale_names: list, deadline_names: list, no_send: bool):
    if no_send:
        return

    total = len(apps)
    interviews = sum(1 for a in apps if a["outcome"] == "interview")
    offers = sum(1 for a in apps if a["outcome"] == "offer")
    pending = sum(1 for a in apps if not a["outcome"])

    lines = [
        f"📬 *CV Pipeline Digest — {datetime.now().strftime('%Y-%m-%d')}*",
        f"📊 {total} applications · {pending} pending · {interviews} interviews · {offers} offers",
    ]
    if stale_names:
        extra = f" +{len(stale_names) - 3} more" if len(stale_names) > 3 else ""
        lines.append(f"⏳ {len(stale_names)} stale: {', '.join(stale_names[:3])}{extra}")
    if deadline_names:
        lines.append(f"⚠️ Deadlines: {', '.join(deadline_names[:3])}")
    lines.append("_Full digest: `cat digest.md`_")

    summary = "\n".join(lines)

    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")

    if slack_webhook:
        ok = _send_slack(summary, slack_webhook)
        print(f"   {'✅ Slack' if ok else '⚠️  Slack failed'}")
    if discord_webhook:
        ok = _send_discord(summary, discord_webhook)
        print(f"   {'✅ Discord' if ok else '⚠️  Discord failed'}")
    if not slack_webhook and not discord_webhook:
        print("   ℹ️  No webhooks configured (set SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL in .env)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate weekly pipeline digest")
    parser.add_argument("--no-send", action="store_true", help="Skip Slack/Discord sending")
    parser.add_argument(
        "--days", type=int, default=14,
        help="Stale threshold in days (default: 14)"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON data")
    args = parser.parse_args()

    load_env()

    apps = collect_apps()
    if not apps:
        print("⚠️  No applications found in applications/")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"📬 Generating digest — {len(apps)} application{'s' if len(apps) != 1 else ''}...")

    funnel_section, funnel_data   = _pipeline_funnel(apps)
    recent_section, recent_names  = _recent_activity(apps, days=7)
    stale_section, stale_names    = _stale_applications(apps, days_threshold=args.days)
    deadline_section, dl_names    = _upcoming_deadlines(apps, days=14)
    ats_section, ats_data         = _ats_summary(apps)
    action_section                = _action_items(stale_names, dl_names, apps)

    header = (
        f"# CV Pipeline Digest\n\n"
        f"*Generated: {today} · {len(apps)} applications · Stale threshold: {args.days} days*\n\n"
        f"---\n\n"
    )
    content = (
        header
        + funnel_section + "\n"
        + recent_section + "\n"
        + stale_section + "\n"
        + deadline_section + "\n"
        + ats_section + "\n"
        + action_section
    )

    out_path = _REPO_ROOT / "digest.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n✅ Digest saved to {out_path}")

    if args.json:
        data = {
            "date": today,
            "total": len(apps),
            "pipeline": funnel_data,
            "stale": stale_names,
            "deadlines": dl_names,
            "ats": ats_data,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    # Summary to terminal
    pending = sum(1 for a in apps if not a["outcome"])
    interviews = sum(1 for a in apps if a["outcome"] == "interview")
    print(f"\n📊 Summary: {len(apps)} total · {pending} pending · {interviews} interviews")
    if stale_names:
        print(f"⏳ {len(stale_names)} stale application{'s' if len(stale_names) != 1 else ''}")
    if dl_names:
        print(f"⚠️  {len(dl_names)} upcoming deadline{'s' if len(dl_names) != 1 else ''}")

    print("\n💬 Sending to webhooks...")
    _send_webhooks(apps, stale_names, dl_names, args.no_send)

    return 0


if __name__ == "__main__":
    sys.exit(main())
