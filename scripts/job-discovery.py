#!/usr/bin/env python3
"""
Job Discovery — scan Greenhouse, Lever, and SerpAPI for relevant job postings.

Usage:
    scripts/job-discovery.py [--source greenhouse|lever|all] [--limit N]
                             [--auto-apply] [--json] [--reset-seen]

Examples:
    python3 scripts/job-discovery.py
    python3 scripts/job-discovery.py --source greenhouse --limit 10
    python3 scripts/job-discovery.py --json
    python3 scripts/job-discovery.py --auto-apply
    python3 scripts/job-discovery.py --reset-seen
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Missing deps: pip install requests beautifulsoup4 pyyaml")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("Missing deps: pip install pyyaml")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}

REQUEST_TIMEOUT = 15  # seconds

DIVIDER = "-" * 65


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config():
    """Load data/job-discovery.yml."""
    config_path = _REPO_ROOT / "data" / "job-discovery.yml"
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def load_seen(config):
    """Load the set of already-seen job IDs from the seen_jobs_file."""
    seen_file = _REPO_ROOT / config.get("seen_jobs_file", ".job-discovery-seen.json")
    if seen_file.exists():
        try:
            with open(seen_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_seen(config, seen):
    """Persist seen job IDs back to disk."""
    seen_file = _REPO_ROOT / config.get("seen_jobs_file", ".job-discovery-seen.json")
    try:
        with open(seen_file, "w", encoding="utf-8") as f:
            json.dump(seen, f, indent=2)
    except OSError as e:
        print(f"   Warning: could not save seen file: {e}")


def reset_seen(config):
    """Clear the seen jobs file."""
    seen_file = _REPO_ROOT / config.get("seen_jobs_file", ".job-discovery-seen.json")
    if seen_file.exists():
        seen_file.unlink()
        print(f"Cleared seen jobs file: {seen_file.name}")
    else:
        print("No seen jobs file found — nothing to clear.")


# ---------------------------------------------------------------------------
# Keyword / location matching
# ---------------------------------------------------------------------------

def matches_keywords(title, keywords):
    """Return True if title contains any of the configured keywords."""
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in keywords)


def matches_location(location, locations):
    """Return True if location matches any configured location (or is remote)."""
    if not location:
        return False
    loc_lower = location.lower()
    return any(loc.lower() in loc_lower for loc in locations) or "remote" in loc_lower


# ---------------------------------------------------------------------------
# Source: Greenhouse
# ---------------------------------------------------------------------------

def fetch_greenhouse(company, config):
    """
    Fetch jobs from boards.greenhouse.io/{greenhouse_id}/jobs.json
    Returns list of normalised job dicts.
    """
    greenhouse_id = company.get("greenhouse_id")
    if not greenhouse_id:
        return []

    url = f"https://boards.greenhouse.io/{greenhouse_id}/jobs.json"
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    keywords = config.get("keywords", [])
    locations = config.get("locations", [])
    results = []

    for job in data.get("jobs", []):
        title = job.get("title", "")
        location = job.get("location", {}).get("name", "")
        job_url = job.get("absolute_url", "")
        job_id = str(job.get("id", ""))

        if not matches_keywords(title, keywords):
            continue
        if locations and not matches_location(location, locations):
            continue

        results.append({
            "company": company["name"],
            "title": title,
            "location": location,
            "url": job_url,
            "source": "greenhouse",
            "id": f"greenhouse-{greenhouse_id}-{job_id}",
        })

    return results


# ---------------------------------------------------------------------------
# Source: Lever
# ---------------------------------------------------------------------------

def fetch_lever(company, config):
    """
    Fetch jobs from api.lever.co/v0/postings/{lever_id}?mode=json
    Returns list of normalised job dicts.
    """
    lever_id = company.get("lever_id")
    if not lever_id:
        return []

    url = f"https://api.lever.co/v0/postings/{lever_id}?mode=json"
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    keywords = config.get("keywords", [])
    locations = config.get("locations", [])
    results = []

    for job in data:
        title = job.get("text", "")
        location = (job.get("categories") or {}).get("location", "")
        job_url = job.get("hostedUrl", "")
        job_id = job.get("id", "")

        if not matches_keywords(title, keywords):
            continue
        if locations and not matches_location(location, locations):
            continue

        results.append({
            "company": company["name"],
            "title": title,
            "location": location,
            "url": job_url,
            "source": "lever",
            "id": f"lever-{lever_id}-{job_id}",
        })

    return results


# ---------------------------------------------------------------------------
# Source: Ashby
# ---------------------------------------------------------------------------

def fetch_ashby(company, config):
    """
    Fetch jobs from Ashby API for companies with ashby_id.
    Returns list of normalised job dicts.

    TODO: Ashby's public jobs API endpoint is:
      POST https://api.ashbyhq.com/posting-api/job-board/{ashby_id}
      with Content-Type: application/json and empty body {}
    Requires ashby_id to be set on the company entry.
    """
    ashby_id = company.get("ashby_id")
    if not ashby_id:
        return []

    url = f"https://api.ashbyhq.com/posting-api/job-board/{ashby_id}"
    resp = requests.post(
        url,
        headers={**HEADERS, "Content-Type": "application/json"},
        json={},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    keywords = config.get("keywords", [])
    locations = config.get("locations", [])
    results = []

    for job in data.get("jobs", []):
        title = job.get("title", "")
        # Ashby nests location inside primaryLocation or locations list
        location = job.get("primaryLocation", {}).get("locationStr", "")
        if not location:
            locs = job.get("locations", [])
            location = locs[0].get("locationStr", "") if locs else ""
        job_url = job.get("jobUrl", "")
        job_id = job.get("id", "")

        if not matches_keywords(title, keywords):
            continue
        if locations and not matches_location(location, locations):
            continue

        results.append({
            "company": company["name"],
            "title": title,
            "location": location,
            "url": job_url,
            "source": "ashby",
            "id": f"ashby-{ashby_id}-{job_id}",
        })

    return results


# ---------------------------------------------------------------------------
# Source: Indeed (disabled — fragile)
# ---------------------------------------------------------------------------

def fetch_indeed(config):
    """
    Indeed scraping is unreliable due to bot-detection.
    TODO: Implement when a stable Indeed jobs API becomes available.
    """
    print("   Warning: Indeed scraping is unreliable — disabled")
    return []


# ---------------------------------------------------------------------------
# Source: SerpAPI
# ---------------------------------------------------------------------------

def fetch_serpapi(config):
    """
    Fetch jobs via SerpAPI Google Jobs engine.
    Requires SERPAPI_KEY environment variable.
    """
    api_key = os.environ.get("SERPAPI_KEY", "")
    if not api_key:
        print("   Warning: SERPAPI_KEY not set — skipping SerpAPI")
        return []

    keywords = config.get("keywords", [])
    locations = config.get("locations", [])
    results = []

    # Query each keyword x location combo (first location only to limit API calls)
    primary_location = locations[0] if locations else "France"
    seen_urls = set()

    for keyword in keywords:
        query = f"{keyword} {primary_location}"
        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google_jobs",
            "q": query,
            "api_key": api_key,
            "hl": "en",
        }
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"   Warning: SerpAPI query '{query}' failed: {e}")
            continue

        for job in data.get("jobs_results", []):
            title = job.get("title", "")
            company_name = job.get("company_name", "Unknown")
            location = job.get("location", "")
            # SerpAPI provides a share link; use detected_extensions.posted_at as fallback
            job_url = ""
            for ext in job.get("related_links", []):
                job_url = ext.get("link", "")
                break
            job_id = job.get("job_id", "")

            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            if not matches_keywords(title, keywords):
                continue

            results.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url,
                "source": "serpapi",
                "id": f"serpapi-{job_id}" if job_id else f"serpapi-{hash(job_url)}",
            })

    return results


# ---------------------------------------------------------------------------
# Discovery orchestration
# ---------------------------------------------------------------------------

def discover_jobs(config, source_filter="all", quiet=False):
    """
    Run all enabled sources and return list of job dicts.
    source_filter: "all" | "greenhouse" | "lever" | "ashby" | "serpapi"
    """
    sources_cfg = config.get("sources", {})
    companies = config.get("companies", [])
    all_jobs = []

    if not quiet:
        print("Discovering jobs...")

    # --- Greenhouse ---
    if source_filter in ("all", "greenhouse") and sources_cfg.get("greenhouse", True):
        gh_companies = [c for c in companies if c.get("ats") == "greenhouse" and c.get("greenhouse_id")]
        for company in gh_companies:
            label = f"Greenhouse: {company['name']}"
            if not quiet:
                print(f"   Scanning {label}...", end="", flush=True)
            try:
                jobs = fetch_greenhouse(company, config)
                all_jobs.extend(jobs)
                if not quiet:
                    count = len(jobs)
                    noun = "match" if count == 1 else "matches"
                    print(f" {count} {noun}")
            except Exception as e:
                if not quiet:
                    print(f" error: {e}")

    # --- Lever ---
    if source_filter in ("all", "lever") and sources_cfg.get("lever", True):
        lv_companies = [c for c in companies if c.get("ats") == "lever" and c.get("lever_id")]
        for company in lv_companies:
            label = f"Lever: {company['name']}"
            if not quiet:
                print(f"   Scanning {label}...", end="", flush=True)
            try:
                jobs = fetch_lever(company, config)
                all_jobs.extend(jobs)
                if not quiet:
                    count = len(jobs)
                    noun = "match" if count == 1 else "matches"
                    print(f" {count} {noun}")
            except Exception as e:
                if not quiet:
                    print(f" error: {e}")

    # --- Ashby ---
    if source_filter in ("all", "ashby") and sources_cfg.get("ashby", False):
        ab_companies = [c for c in companies if c.get("ats") == "ashby" and c.get("ashby_id")]
        for company in ab_companies:
            label = f"Ashby: {company['name']}"
            if not quiet:
                print(f"   Scanning {label}...", end="", flush=True)
            try:
                jobs = fetch_ashby(company, config)
                all_jobs.extend(jobs)
                if not quiet:
                    count = len(jobs)
                    noun = "match" if count == 1 else "matches"
                    print(f" {count} {noun}")
            except Exception as e:
                if not quiet:
                    print(f" error: {e}")

    # --- Indeed ---
    if source_filter in ("all", "indeed") and sources_cfg.get("indeed", False):
        if not quiet:
            fetch_indeed(config)

    # --- SerpAPI ---
    if source_filter in ("all", "serpapi") and sources_cfg.get("serpapi", False):
        if not quiet:
            print(f"   Scanning SerpAPI...", end="", flush=True)
        try:
            jobs = fetch_serpapi(config)
            all_jobs.extend(jobs)
            if not quiet:
                count = len(jobs)
                noun = "match" if count == 1 else "matches"
                print(f" {count} {noun}")
        except Exception as e:
            if not quiet:
                print(f" error: {e}")

    return all_jobs


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_job(index, job):
    """Print a single job entry in human-readable format."""
    print(f"\n  {index}. {job['company']} -- {job['title']}")
    print(f"     Location: {job['location'] or 'Not specified'}  |  Source: {job['source']}")
    print(f"     {job['url']}")


def print_apply_hint(index, job):
    """Print the make apply command hint for a job."""
    company = job["company"]
    title = job["title"]
    url = job["url"]
    print(f'   make apply COMPANY="{company}" POSITION="{title}" URL="{url}"')


# ---------------------------------------------------------------------------
# Auto-apply
# ---------------------------------------------------------------------------

def auto_apply(jobs):
    """
    Run 'make apply' for each job in the list.
    Continues on failure, prints a summary at the end.
    """
    if not jobs:
        print("No jobs to apply to.")
        return

    print(f"\nAuto-applying to {len(jobs)} job(s)...")
    print(DIVIDER)

    success = []
    failed = []

    for job in jobs:
        company = job["company"]
        title = job["title"]
        url = job["url"]
        print(f"\n  Applying: {company} -- {title}")
        cmd = [
            "make", "apply",
            f"COMPANY={company}",
            f"POSITION={title}",
            f"URL={url}",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                print(f"     OK")
                success.append(job)
            else:
                print(f"     FAILED (exit {result.returncode})")
                if result.stderr:
                    for line in result.stderr.strip().splitlines()[-3:]:
                        print(f"       {line}")
                failed.append(job)
        except subprocess.TimeoutExpired:
            print(f"     FAILED (timeout)")
            failed.append(job)
        except Exception as e:
            print(f"     FAILED ({e})")
            failed.append(job)

    print(f"\n{DIVIDER}")
    print(f"Auto-apply summary: {len(success)} succeeded, {len(failed)} failed")
    if failed:
        print("Failed jobs:")
        for job in failed:
            print(f"  - {job['company']} -- {job['title']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Discover relevant job postings from Greenhouse, Lever, and more.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        choices=["greenhouse", "lever", "ashby", "serpapi", "all"],
        default="all",
        help="Limit discovery to a specific source (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Show at most N new jobs (default: no limit)",
    )
    parser.add_argument(
        "--auto-apply",
        action="store_true",
        help="Run 'make apply' for each new job found",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (suppresses human-readable output)",
    )
    parser.add_argument(
        "--reset-seen",
        action="store_true",
        help="Clear the seen jobs file and exit",
    )
    args = parser.parse_args()

    config = load_config()
    quiet = args.json

    # Handle --reset-seen
    if args.reset_seen:
        reset_seen(config)
        return 0

    # Load seen jobs for deduplication
    seen = load_seen(config)

    # Discover
    all_jobs = discover_jobs(config, source_filter=args.source, quiet=quiet)

    if not quiet:
        print(f"   {DIVIDER}")

    # Deduplicate
    today = datetime.date.today().isoformat()
    new_jobs = []
    already_seen_jobs = []

    for job in all_jobs:
        job_id = job["id"]
        if job_id in seen:
            already_seen_jobs.append(job)
        else:
            new_jobs.append(job)

    # Apply limit
    if args.limit and args.limit > 0:
        new_jobs = new_jobs[: args.limit]

    # Mark new jobs as seen
    for job in new_jobs:
        seen[job["id"]] = today
    save_seen(config, seen)

    # --- JSON output ---
    if args.json:
        output = {
            "total_new": len(new_jobs),
            "total_seen": len(already_seen_jobs),
            "jobs": new_jobs,
        }
        print(json.dumps(output, indent=2))
        return 0

    # --- Human-readable output ---
    print()
    if not new_jobs:
        print(f"No new jobs found. ({len(already_seen_jobs)} already seen)")
        print()
        print(f"Tip: run with --reset-seen to start fresh.")
        return 0

    noun = "Job" if len(new_jobs) == 1 else "Jobs"
    print(f"New {noun} Found: {len(new_jobs)}")

    for i, job in enumerate(new_jobs, start=1):
        print_job(i, job)

    print(f"\n{DIVIDER}")

    if len(new_jobs) == 1:
        print(f"To apply to this job:")
        print_apply_hint(1, new_jobs[0])
    else:
        print(f"To apply to a specific job:")
        print_apply_hint(1, new_jobs[0])
        print()
        print(f"Or to apply to all {len(new_jobs)} at once:")
        print(f"   python3 scripts/job-discovery.py --auto-apply")

    if already_seen_jobs:
        print(f"\n({len(already_seen_jobs)} previously seen job(s) hidden. Use --reset-seen to show again.)")

    # --- Auto-apply ---
    if args.auto_apply:
        auto_apply(new_jobs)

    return 0


if __name__ == "__main__":
    sys.exit(main())
