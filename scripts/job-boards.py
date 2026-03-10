#!/usr/bin/env python3
"""
Job board integration — fetch job postings from Greenhouse and Lever public APIs.

Both APIs are fully public (no auth required) and return structured JSON.
Matches jobs against keywords from your profile, then optionally creates
application folders.

Supported boards:
  - Greenhouse: https://boards.greenhouse.io/v1/boards/{company}/jobs
  - Lever:      https://api.lever.co/v0/postings/{company}?mode=json

Usage:
    scripts/job-boards.py --board greenhouse --company stripe [--keywords "python,api"]
    scripts/job-boards.py --board lever --company vercel [--create] [--min-score 30]
    scripts/job-boards.py --companies-file data/job-boards.yml  # batch mode
    make boards BOARD=greenhouse COMPANY=stripe
    make boards-file                                            # batch from config
"""

from __future__ import annotations

import argparse
import json
import re
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

from lib.common import REPO_ROOT, USER_AGENT

HEADERS = {"User-Agent": USER_AGENT}
BOARDS_CONFIG = REPO_ROOT / "data" / "job-boards.yml"


# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------


def fetch_greenhouse(company_slug: str) -> list[dict]:
    """Fetch all jobs from Greenhouse public API. Returns normalized job list."""
    url = f"https://boards.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print(f"   ⚠️  Greenhouse: no board found for '{company_slug}'")
            return []
        raise
    except Exception as e:
        print(f"   ⚠️  Greenhouse error: {e}")
        return []

    jobs = []
    for j in data.get("jobs", []):
        # Extract location
        loc = j.get("location", {}).get("name", "")
        # Extract departments
        depts = [d.get("name", "") for d in j.get("departments", [])]
        # Flatten content (HTML stripped)
        content = re.sub(r"<[^>]+>", " ", j.get("content") or "")
        content = re.sub(r"\s+", " ", content).strip()
        jobs.append(
            {
                "board": "greenhouse",
                "company_slug": company_slug,
                "id": str(j.get("id", "")),
                "title": j.get("title", ""),
                "location": loc,
                "departments": depts,
                "url": j.get("absolute_url", ""),
                "description": content[:3000],
                "updated_at": j.get("updated_at", ""),
            }
        )
    return jobs


def fetch_lever(company_slug: str) -> list[dict]:
    """Fetch all jobs from Lever public API. Returns normalized job list."""
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            print(f"   ⚠️  Lever: no postings found for '{company_slug}'")
            return []
        raise
    except Exception as e:
        print(f"   ⚠️  Lever error: {e}")
        return []

    jobs = []
    for j in data if isinstance(data, list) else []:
        # Build description from lists
        text_parts = []
        for section in j.get("lists", []):
            text_parts.append(section.get("text", ""))
            for item in section.get("content", []):
                text_parts.append(re.sub(r"<[^>]+>", " ", item))
        desc = re.sub(r"\s+", " ", " ".join(text_parts)).strip()

        # Additional sections
        for key in ("descriptionPlain", "additionalPlain"):
            if j.get(key):
                desc += " " + j[key][:500]

        jobs.append(
            {
                "board": "lever",
                "company_slug": company_slug,
                "id": j.get("id", ""),
                "title": j.get("text", ""),
                "location": j.get("categories", {}).get("location", ""),
                "departments": [j.get("categories", {}).get("department", "")],
                "url": j.get("hostedUrl", ""),
                "description": desc[:3000],
                "updated_at": str(j.get("updatedAt", "")),
            }
        )
    return jobs


BOARD_FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
}


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b[a-z]{3,}\b", text.lower()))


def keyword_score(job: dict, keywords: list[str]) -> float:
    """Return % of keywords found in job title + description."""
    if not keywords:
        return 100.0
    text = (job["title"] + " " + job["description"]).lower()
    found = sum(1 for kw in keywords if kw.lower() in text)
    return round(found / len(keywords) * 100, 1)


# ---------------------------------------------------------------------------
# Application creation
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-")[:40]


def _app_dirname(company_slug: str, title: str) -> str:
    from datetime import date

    month = date.today().strftime("%Y-%m")
    pos_slug = _slugify(title)
    return f"{month}-{company_slug[:20]}-{pos_slug}"


def create_application(job: dict, apps_dir: Path, dry_run: bool) -> Path | None:
    """Create applications/NAME/ with meta.yml and job.txt."""
    app_name = _app_dirname(job["company_slug"], job["title"])
    app_dir = apps_dir / app_name

    if app_dir.exists():
        print(f"      ⚠️  Already exists: {app_name}")
        return app_dir

    if dry_run:
        print(f"      [DRY] Would create: {app_name}")
        return None

    app_dir.mkdir(parents=True)

    # meta.yml
    meta = {
        "company": job["company_slug"].title(),
        "position": job["title"],
        "created": str(Path(app_name).name[:7]),
        "outcome": "applied",
        "board": job["board"],
        "board_id": job["id"],
    }
    if job.get("location"):
        meta["location"] = job["location"]

    (app_dir / "meta.yml").write_text(yaml.dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")

    # job.txt
    (app_dir / "job.txt").write_text(
        f"{job['title']}\n{'=' * len(job['title'])}\n\n{job['description']}\n",
        encoding="utf-8",
    )

    # job.url
    if job.get("url"):
        (app_dir / "job.url").write_text(job["url"], encoding="utf-8")

    print(f"      ✅ Created: {app_name}")
    return app_dir


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


def run_board(
    board: str, company_slug: str, keywords: list[str], min_score: float, create: bool, dry_run: bool, apps_dir: Path
) -> list[dict]:
    fetcher = BOARD_FETCHERS.get(board)
    if not fetcher:
        print(f"❌ Unknown board: {board}. Supported: {', '.join(BOARD_FETCHERS)}")
        return []

    print(f"🔍 Fetching {board}/{company_slug}...")
    jobs = fetcher(company_slug)
    if not jobs:
        print(f"   No jobs found.")
        return []

    print(f"   Found {len(jobs)} postings")

    # Score and filter
    scored = []
    for j in jobs:
        s = keyword_score(j, keywords)
        if s >= min_score:
            scored.append((s, j))

    scored.sort(key=lambda x: -x[0])
    print(f"   {len(scored)} match filter (score ≥ {min_score}%)\n")

    results = []
    for score, job in scored:
        loc = f"  [{job['location']}]" if job.get("location") else ""
        print(f"   {score:5.0f}%  {job['title']}{loc}")
        if job.get("url"):
            print(f"          {job['url']}")
        if create or dry_run:
            create_application(job, apps_dir, dry_run)
        results.append({**job, "match_score": score})

    return results


def run_from_config(config_path: Path, create: bool, dry_run: bool, apps_dir: Path) -> None:
    if not config_path.exists():
        print(f"❌ Config not found: {config_path}")
        print(f"   Create data/job-boards.yml with entries:")
        print(f"   - board: greenhouse")
        print(f"     company: stripe")
        print(f"     keywords: [python, api, platform]")
        print(f"     min_score: 40")
        return

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or []
    if not isinstance(config, list):
        print("❌ job-boards.yml must be a list of entries")
        return

    for entry in config:
        board = entry.get("board", "greenhouse")
        company = entry.get("company", "")
        keywords = entry.get("keywords", [])
        min_score = float(entry.get("min_score", 30))
        if not company:
            continue
        run_board(board, company, keywords, min_score, create, dry_run, apps_dir)
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch jobs from Greenhouse/Lever public APIs")
    parser.add_argument("--board", choices=list(BOARD_FETCHERS), default="greenhouse", help="Job board to query")
    parser.add_argument("--company", metavar="SLUG", help="Company slug on the board")
    parser.add_argument("--keywords", metavar="K1,K2,...", help="Comma-separated keywords to filter jobs")
    parser.add_argument("--min-score", type=float, default=0, help="Minimum keyword match %% (default: 0 = show all)")
    parser.add_argument("--create", action="store_true", help="Create application folders for matched jobs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing")
    parser.add_argument(
        "--companies-file", metavar="PATH", help="YAML config file for batch mode (default: data/job-boards.yml)"
    )
    parser.add_argument("--json", action="store_true", dest="json_mode", help="Output JSON")
    args = parser.parse_args()

    apps_dir = REPO_ROOT / "applications"
    apps_dir.mkdir(exist_ok=True)

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else []

    # Batch mode
    if args.companies_file or not args.company:
        config_path = Path(args.companies_file) if args.companies_file else BOARDS_CONFIG
        run_from_config(config_path, args.create, args.dry_run, apps_dir)
        return 0

    # Single company mode
    results = run_board(
        args.board,
        args.company,
        keywords,
        args.min_score,
        args.create,
        args.dry_run,
        apps_dir,
    )

    if args.json_mode:
        print(json.dumps(results, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
