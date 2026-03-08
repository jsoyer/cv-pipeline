#!/usr/bin/env python3
"""
Batch Apply — Run the full apply → tailor → compile pipeline for multiple jobs.

Input: CSV file with columns: company, position, url

Usage:
    scripts/batch-apply.py <csv-file> [--dry-run] [--ai PROVIDER] [--continue-on-error] [--start-from N]
    python3 scripts/batch-apply.py batch.csv
    python3 scripts/batch-apply.py batch.csv --dry-run
    python3 scripts/batch-apply.py batch.csv --ai claude --continue-on-error
    python3 scripts/batch-apply.py batch.csv --start-from 3
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from lib.common import REPO_ROOT


def detect_name_from_git() -> str:
    """Detect the most recently created apply/* branch."""
    try:
        result = subprocess.run(
            ["git", "branch", "--sort=-committerdate"],
            capture_output=True, text=True, timeout=10, cwd=REPO_ROOT,
        )
        for line in result.stdout.splitlines():
            line = line.strip().lstrip("* ")
            if line.startswith("apply/"):
                return line[len("apply/"):]
    except Exception:
        pass
    return ""


def company_to_slug(company: str) -> str:
    """Convert company name to slug for fallback NAME detection."""
    from datetime import datetime
    date = datetime.now().strftime("%Y-%m")
    slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
    return f"{date}-{slug}"


def run_make(target: str, args: dict, dry_run: bool = False) -> tuple[bool, str]:
    """
    Run a make target with given arguments.
    Returns (success, error_message).
    """
    cmd = ["make", "--no-print-directory", target]
    for k, v in args.items():
        # Quote values with spaces
        if " " in str(v):
            cmd.append(f'{k}={v}')
        else:
            cmd.append(f"{k}={v}")

    cmd_str = " ".join(
        f'{k}="{v}"' if " " in str(v) else f"{k}={v}"
        for k, v in args.items()
    )
    label = f"make {target} {cmd_str}"

    if dry_run:
        print(f"   [DRY] {label}")
        return True, ""

    print(f"   ▶  {label}")
    try:
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, timeout=300,
            text=True, capture_output=False,
        )
        if result.returncode != 0:
            return False, f"exit code {result.returncode}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "timeout (5 minutes)"
    except Exception as e:
        return False, str(e)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch Apply — Run the full apply/tailor/compile pipeline for multiple jobs. "
                    "Input: CSV file with columns: company, position, url.",
        epilog="CSV format (header required):\n  company,position,url\n  Datadog,Senior Solutions Engineer EMEA,https://...",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "csv_file",
        metavar="csv-file",
        help="Path to CSV file with columns: company, position, url",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Preview without executing",
    )
    parser.add_argument(
        "--ai",
        metavar="PROVIDER",
        dest="ai_provider",
        default="gemini",
        help="AI provider: gemini | claude | openai | mistral (default: gemini)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        dest="continue_on_error",
        help="Continue after failures",
    )
    parser.add_argument(
        "--start-from",
        metavar="N",
        dest="start_from",
        type=int,
        default=1,
        help="Skip first N-1 rows, 1-indexed (default: 1)",
    )
    args = parser.parse_args()
    return args.csv_file, args.dry_run, args.ai_provider, args.continue_on_error, args.start_from


def main():
    csv_file, dry_run, ai_provider, continue_on_error, start_from = parse_args()

    csv_path = Path(csv_file)
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_file}")
        sys.exit(1)

    # Parse CSV
    rows = []
    try:
        with open(csv_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    except Exception as e:
        print(f"❌ Could not read CSV: {e}")
        sys.exit(1)

    if not rows:
        print("❌ CSV file is empty or has no data rows")
        sys.exit(1)

    # Validate columns
    required_cols = {"company", "position", "url"}
    missing_cols = required_cols - set(rows[0].keys())
    if missing_cols:
        print(f"❌ CSV missing required columns: {', '.join(sorted(missing_cols))}")
        print(f"   Found columns: {', '.join(rows[0].keys())}")
        print(f"   Expected: company,position,url")
        sys.exit(1)

    # Apply --start-from
    if start_from > 1:
        print(f"⏭  Skipping first {start_from - 1} row(s) (--start-from {start_from})")
        rows = rows[start_from - 1:]

    total = len(rows)
    original_total = len(rows) + start_from - 1

    if dry_run:
        print(f"🔍 Dry run — {total} job(s) to process (AI: {ai_provider})")
    else:
        print(f"📦 Batch Apply — {total} job(s) to process (AI: {ai_provider})")
    if start_from > 1:
        print(f"   Starting from row {start_from} of {original_total}")
    print()

    results = []

    for idx, row in enumerate(rows, start=start_from):
        company = row.get("company", "").strip()
        position = row.get("position", "").strip()
        url = row.get("url", "").strip()

        if not company or not position or not url:
            print(f"[{idx}/{original_total}] ⚠️  Skipping incomplete row: {row}")
            results.append({"row": idx, "company": company, "status": "skipped", "name": ""})
            continue

        print(f"[{idx}/{original_total}] {company} — {position}")

        # Step 1: make apply
        apply_args = {
            "URL": url,
            "COMPANY": company,
            "POSITION": position,
        }
        ok, err = run_make("apply", apply_args, dry_run)
        if not ok:
            msg = f"make apply failed: {err}"
            print(f"   ❌ {msg}")
            results.append({"row": idx, "company": company, "status": "failed", "error": msg, "name": ""})
            if not continue_on_error:
                print()
                print("❌ Stopping on error. Use --continue-on-error to proceed anyway.")
                break
            continue

        # Detect NAME
        name = ""
        if not dry_run:
            name = detect_name_from_git()
            if not name:
                # Fallback: construct from company slug
                name = company_to_slug(company)
                print(f"   ⚠️  Could not detect NAME from git, using: {name}")
            else:
                print(f"   ✅ Application: {name}")
        else:
            name = company_to_slug(company)
            print(f"   [DRY] NAME would be: {name}")

        # Step 2: make tailor
        tailor_args = {"NAME": name, "AI": ai_provider}
        ok, err = run_make("tailor", tailor_args, dry_run)
        if not ok:
            msg = f"make tailor failed: {err}"
            print(f"   ❌ {msg}")
            results.append({"row": idx, "company": company, "status": "failed", "error": msg, "name": name})
            if not continue_on_error:
                print()
                print("❌ Stopping on error. Use --continue-on-error to proceed anyway.")
                break
            continue

        # Step 3: make app
        ok, err = run_make("app", {"NAME": name}, dry_run)
        if not ok:
            msg = f"make app failed: {err}"
            print(f"   ❌ {msg}")
            results.append({"row": idx, "company": company, "status": "failed", "error": msg, "name": name})
            if not continue_on_error:
                print()
                print("❌ Stopping on error. Use --continue-on-error to proceed anyway.")
                break
            continue

        icon = "✅" if not dry_run else "🔍"
        status = "success" if not dry_run else "dry-run"
        print(f"   {icon} Done: {name}")
        results.append({"row": idx, "company": company, "status": status, "name": name})
        print()

    # ── Summary ───────────────────────────────────────────────────────
    print("═" * 52)
    print("📦 Batch Apply Summary")
    print("═" * 52)

    succeeded = [r for r in results if r["status"] in ("success", "dry-run")]
    failed = [r for r in results if r["status"] == "failed"]
    skipped = [r for r in results if r["status"] == "skipped"]

    for r in results:
        row_label = f"[{r['row']}/{original_total}]"
        if r["status"] in ("success", "dry-run"):
            icon = "✅" if r["status"] == "success" else "🔍"
            print(f"{icon} {row_label} {r['company']}: {r.get('name', '')}")
        elif r["status"] == "failed":
            print(f"❌ {row_label} {r['company']}: {r.get('error', 'unknown error')}")
        else:
            print(f"⚠️  {row_label} {r['company']}: skipped (incomplete row)")

    print("═" * 52)
    parts = []
    if succeeded:
        parts.append(f"{len(succeeded)} succeeded")
    if failed:
        parts.append(f"{len(failed)} failed")
    if skipped:
        parts.append(f"{len(skipped)} skipped")
    print(f"Results: {', '.join(parts)}")
    print()

    if succeeded and not dry_run:
        first = succeeded[0]
        print(f"💡 To review: make review NAME={first['name']}")
    if failed:
        fail_idx = failed[0]["row"]
        print(f"💡 Retry failed: make batch CSV={csv_file} --start-from {fail_idx} --continue-on-error")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
