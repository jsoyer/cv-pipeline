#!/usr/bin/env python3
"""
Check if job posting URLs are still live.

Reads job.url from each application directory and reports status:
  LIVE       — HTTP 200, no closed-job keywords
  CLOSED     — HTTP 404/410, or page contains "position has been filled" etc.
  REDIRECTED — Final URL differs from original (redirected to /careers)
  ERROR      — Timeout, connection error, other HTTP error

Usage:
    scripts/url-check.py [--name APP_NAME] [--json]
"""

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Keywords indicating a closed/filled position
CLOSED_KEYWORDS = [
    "no longer accepting",
    "position has been filled",
    "this job is closed",
    "this position is no longer available",
    "this role has been filled",
    "job expired",
    "job posting expired",
    "posting has expired",
    "posting removed",
    "not currently hiring",
    "this listing has expired",
    "this job has been removed",
    "this vacancy is closed",
    "this vacancy has been filled",
    "applications are closed",
    "no longer available",
    "this position has been closed",
]

# These redirect targets suggest the job was removed
DEAD_REDIRECT_PATTERNS = [
    "/careers",
    "/jobs",
    "/404",
    "/not-found",
    "error",
]


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------

def load_meta(app_dir: Path) -> dict:
    if not HAS_YAML:
        return {}
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def check_url(original_url: str) -> dict:
    """Check a single URL and return status dict."""
    if not HAS_REQUESTS:
        return {"status": "error", "detail": "requests not installed"}

    try:
        resp = requests.get(
            original_url,
            headers=HEADERS,
            timeout=15,
            allow_redirects=True,
        )
        final_url = resp.url
        status_code = resp.status_code

        # HTTP error codes → closed
        if status_code in (404, 410, 403):
            return {
                "status": "closed",
                "detail": f"HTTP {status_code}",
                "final_url": final_url,
                "code": status_code,
            }

        # Non-200 but not explicit close code
        if status_code != 200:
            return {
                "status": "error",
                "detail": f"HTTP {status_code}",
                "final_url": final_url,
                "code": status_code,
            }

        # Check for redirect to generic page
        orig_parsed = urllib.parse.urlparse(original_url)
        final_parsed = urllib.parse.urlparse(final_url)
        was_redirected = orig_parsed.netloc != final_parsed.netloc or (
            orig_parsed.path != final_parsed.path and
            final_url.rstrip("/") != original_url.rstrip("/")
        )

        if was_redirected:
            # Is the redirect to a generic "careers" page?
            final_path = final_parsed.path.lower()
            is_dead_redirect = any(
                final_path == p or final_path == p + "/" or final_path.startswith(p + "?")
                for p in DEAD_REDIRECT_PATTERNS
            )
            # Also check if redirected to the root
            if final_path in ("/", ""):
                is_dead_redirect = True

            return {
                "status": "redirected" if not is_dead_redirect else "closed",
                "detail": f"→ {final_url}",
                "final_url": final_url,
                "code": status_code,
            }

        # Check page content for closed-job keywords
        try:
            content = resp.text.lower()
        except Exception:
            content = ""

        for kw in CLOSED_KEYWORDS:
            if kw in content:
                return {
                    "status": "closed",
                    "detail": f'"{kw}"',
                    "final_url": final_url,
                    "code": status_code,
                }

        return {
            "status": "live",
            "detail": f"HTTP {status_code}",
            "final_url": final_url,
            "code": status_code,
        }

    except requests.exceptions.Timeout:
        return {"status": "error", "detail": "timeout (15s)", "final_url": original_url}
    except requests.exceptions.ConnectionError as e:
        return {"status": "error", "detail": f"connection error: {str(e)[:60]}", "final_url": original_url}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:80], "final_url": original_url}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

STATUS_ICON = {
    "live":       "✅",
    "closed":     "❌",
    "redirected": "⚠️ ",
    "error":      "🔴",
}


def run(name_filter: str = "", json_mode: bool = False) -> int:
    if not HAS_REQUESTS:
        print("❌ requests not installed: pip install requests")
        return 1

    apps_dir = _REPO_ROOT / "applications"
    if not apps_dir.exists():
        print("❌ No applications/ directory found")
        return 1

    # Collect apps with job.url
    targets = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        if name_filter and d.name != name_filter:
            continue
        job_url_path = d / "job.url"
        if not job_url_path.exists():
            continue
        url = job_url_path.read_text(encoding="utf-8").strip()
        if url:
            meta = load_meta(d)
            targets.append({
                "name": d.name,
                "company": meta.get("company", d.name),
                "url": url,
            })

    if not targets:
        if name_filter:
            print(f"⚠️  No job.url found for: {name_filter}")
        else:
            print("⚠️  No job.url files found in any application directory")
        return 0

    print(f"📡 URL Status Check — {len(targets)} application{'s' if len(targets) != 1 else ''}\n")

    results = []
    closed_apps = []
    error_apps = []

    for t in targets:
        print(f"   Checking {t['name']}...", end=" ", flush=True)
        result = check_url(t["url"])
        result["name"] = t["name"]
        result["company"] = t["company"]
        result["original_url"] = t["url"]
        results.append(result)

        icon = STATUS_ICON.get(result["status"], "❓")
        status_str = result["status"].upper().ljust(10)
        detail = result.get("detail", "")[:60]
        print(f"\r  {icon} {t['name']:<35} {status_str} {detail}")

        if result["status"] == "closed":
            closed_apps.append(t["name"])
        elif result["status"] == "error":
            error_apps.append(t["name"])

    print()

    if closed_apps:
        print("💡 Closed positions — consider urgent follow-up or:")
        for n in closed_apps:
            print(f"   make notify NAME={n} STATUS=ghosted")
        print()

    if json_mode:
        print(json.dumps(results, indent=2, ensure_ascii=False))

    # Summary counts
    by_status = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    parts = [f"{v} {k}" for k, v in sorted(by_status.items())]
    print("Summary: " + " · ".join(parts))

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Check if job posting URLs are still live"
    )
    parser.add_argument(
        "--name", default="", metavar="APP_NAME",
        help="Check a single application only"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output JSON results"
    )
    args = parser.parse_args()
    sys.exit(run(name_filter=args.name, json_mode=args.json))


if __name__ == "__main__":
    main()
