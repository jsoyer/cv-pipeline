#!/usr/bin/env python3
"""
Notion two-way sync — pull status changes from Notion DB back to local meta.yml.

Direction:
  push  (default): local meta.yml → Notion (create/update all applications)
  pull           : Notion → local meta.yml (update outcome from Notion Status field)
  diff           : show what would change in either direction without writing

Usage:
    scripts/notion-twoway.py [pull|push|diff] [--dry-run]
    make notion-pull
    make notion-push
    make notion-diff
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ requests required: pip install requests")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT, load_meta

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Notion Status → local outcome mapping
NOTION_TO_LOCAL: dict[str, str] = {
    "Draft": "applied",
    "Applied": "applied",
    "Phone Screen": "phone_screen",
    "Interview": "interview",
    "Technical": "technical",
    "Final Round": "final_round",
    "Offer": "offer",
    "Accepted": "accepted",
    "Rejected": "rejected",
    "Ghosted": "ghosted",
    "Withdrawn": "withdrawn",
}

LOCAL_TO_NOTION: dict[str, str] = {
    "applied": "Applied",
    "phone_screen": "Phone Screen",
    "screen": "Phone Screen",
    "interview": "Interview",
    "technical": "Technical",
    "final_round": "Final Round",
    "final": "Final Round",
    "offer": "Offer",
    "accepted": "Accepted",
    "rejected": "Rejected",
    "ghosted": "Ghosted",
    "withdrawn": "Withdrawn",
}


class NotionClient:
    def __init__(self, token: str, db_id: str):
        self.token = token
        self.db_id = db_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    def query_db(self, filter_: dict | None = None) -> list[dict]:
        """Return all pages in the database (handles pagination)."""
        pages = []
        cursor = None
        while True:
            body: dict = {"page_size": 100}
            if filter_:
                body["filter"] = filter_
            if cursor:
                body["start_cursor"] = cursor
            resp = requests.post(
                f"{NOTION_API}/databases/{self.db_id}/query",
                headers=self.headers,
                json=body,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            pages.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return pages

    def update_page(self, page_id: str, properties: dict) -> dict:
        resp = requests.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=self.headers,
            json={"properties": properties},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def create_page(self, properties: dict) -> dict:
        resp = requests.post(
            f"{NOTION_API}/pages",
            headers=self.headers,
            json={"parent": {"database_id": self.db_id}, "properties": properties},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_text(prop: dict) -> str:
    """Extract plain text from a Notion property."""
    ptype = prop.get("type", "")
    if ptype == "title":
        items = prop.get("title", [])
    elif ptype == "rich_text":
        items = prop.get("rich_text", [])
    elif ptype == "select":
        return prop.get("select", {}).get("name", "") if prop.get("select") else ""
    elif ptype == "url":
        return prop.get("url", "") or ""
    elif ptype == "date":
        d = prop.get("date")
        return d.get("start", "") if d else ""
    else:
        return ""
    return "".join(t.get("plain_text", "") for t in items)


def _load_apps(apps_dir: Path) -> dict[str, dict]:
    """Load all applications keyed by app-dir name."""
    apps = {}
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.yml"
        if not meta_path.exists():
            continue
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            apps[d.name] = {"path": d, "meta": meta}
        except Exception:
            continue
    return apps


def _save_meta(app_dir: Path, meta: dict) -> None:
    with open(app_dir / "meta.yml", "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, sort_keys=False)


def _notion_page_to_app(page: dict) -> dict:
    """Extract fields from a Notion page properties dict."""
    props = page.get("properties", {})
    return {
        "page_id": page["id"],
        "company": _get_text(props.get("Company", {})),
        "position": _get_text(props.get("Position", {})),
        "branch": _get_text(props.get("Branch", {})),
        "status": _get_text(props.get("Status", {})),
        "pr_url": _get_text(props.get("PR", {})),
    }


# ---------------------------------------------------------------------------
# Sync operations
# ---------------------------------------------------------------------------


def do_pull(client: NotionClient, apps: dict, dry_run: bool) -> int:
    """Pull Notion status → local meta.yml."""
    print("⬇️  Pulling from Notion...\n")
    pages = client.query_db()
    print(f"   Found {len(pages)} Notion pages\n")

    updated = 0
    skipped = 0
    not_found = 0

    for page in pages:
        np = _notion_page_to_app(page)
        company = np["company"]
        branch = np["branch"]
        notion_status = np["status"]

        # Try to match by branch name (most reliable)
        app_name = branch.replace("apply/", "") if branch else ""

        # Fallback: match by company name
        if app_name not in apps:
            matches = [k for k, v in apps.items() if v["meta"].get("company", "").lower() == company.lower()]
            app_name = matches[0] if len(matches) == 1 else ""

        if not app_name or app_name not in apps:
            not_found += 1
            if company:
                print(f"   ⚠️  Not found locally: {company!r} (branch={branch!r})")
            continue

        app = apps[app_name]
        local_outcome = app["meta"].get("outcome", "applied")
        local_expected = NOTION_TO_LOCAL.get(notion_status, "")

        if not local_expected:
            print(f"   ⚠️  Unknown Notion status: {notion_status!r} for {company}")
            skipped += 1
            continue

        if local_outcome == local_expected:
            skipped += 1
            continue

        print(f"   📝 {app_name}")
        print(f"      Notion: {notion_status!r} → local: {local_outcome!r} ✗")
        print(f"      Would update: outcome={local_outcome!r} → {local_expected!r}")

        if not dry_run:
            app["meta"]["outcome"] = local_expected
            _save_meta(app["path"], app["meta"])
            print(f"      ✅ Updated meta.yml")

        updated += 1

    print(
        f"\n{'[DRY RUN] ' if dry_run else ''}Summary: {updated} updated, {skipped} in sync, {not_found} not found locally"
    )
    return 0


def do_push(client: NotionClient, apps: dict, dry_run: bool) -> int:
    """Push local meta.yml → Notion (upsert by company name)."""
    print("⬆️  Pushing to Notion...\n")
    pages = client.query_db()

    # Build index: company.lower() → page
    notion_index: dict[str, dict] = {}
    for page in pages:
        np = _notion_page_to_app(page)
        if np["company"]:
            notion_index[np["company"].lower()] = np

    created = updated = skipped = 0

    for app_name, app in sorted(apps.items()):
        meta = app["meta"]
        company = meta.get("company", "")
        position = meta.get("position", "")
        outcome = meta.get("outcome", "applied")
        notion_status = LOCAL_TO_NOTION.get(outcome, "Applied")

        if not company:
            continue

        existing = notion_index.get(company.lower())

        if existing:
            current_notion = existing["status"]
            if current_notion == notion_status:
                skipped += 1
                continue
            print(f"   📝 {company}: {current_notion!r} → {notion_status!r}")
            if not dry_run:
                client.update_page(
                    existing["page_id"],
                    {"Status": {"select": {"name": notion_status}}},
                )
                print(f"      ✅ Updated")
            updated += 1
        else:
            print(f"   ➕ {company} — {position}: create as {notion_status!r}")
            if not dry_run:
                props = {
                    "Company": {"title": [{"text": {"content": company}}]},
                    "Position": {"rich_text": [{"text": {"content": position}}]},
                    "Status": {"select": {"name": notion_status}},
                    "Branch": {"rich_text": [{"text": {"content": f"apply/{app_name}"}}]},
                }
                client.create_page(props)
                print(f"      ✅ Created")
            created += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary: {created} created, {updated} updated, {skipped} in sync")
    return 0


def do_diff(client: NotionClient, apps: dict) -> int:
    """Show differences without writing anything."""
    print("🔍 Notion ↔ Local diff\n")
    do_pull(client, apps, dry_run=True)
    print()
    do_push(client, apps, dry_run=True)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Notion two-way sync")
    parser.add_argument(
        "direction", nargs="?", choices=["pull", "push", "diff"], default="diff", help="Sync direction (default: diff)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    # Load credentials
    token = os.environ.get("NOTION_TOKEN", "")
    db_id = os.environ.get("NOTION_DB_ID", "") or os.environ.get("NOTION_DATABASE_ID", "")

    if not token or not db_id:
        print("❌ NOTION_TOKEN and NOTION_DB_ID (or NOTION_DATABASE_ID) must be set")
        print("   Add them to .env or export them in your shell")
        return 1

    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.is_dir():
        print("❌ applications/ directory not found")
        return 1

    client = NotionClient(token, db_id)
    apps = _load_apps(apps_dir)
    print(f"📁 Loaded {len(apps)} local applications\n")

    try:
        if args.direction == "pull":
            return do_pull(client, apps, args.dry_run)
        elif args.direction == "push":
            return do_push(client, apps, args.dry_run)
        else:
            return do_diff(client, apps)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
