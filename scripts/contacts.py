#!/usr/bin/env python3
"""
Find recruiter/hiring manager contacts for a job application.

Sources (combined):
  1. Hunter.io API   — domain-based email search (HUNTER_API_KEY)
  2. Company website — scrape /about /team /company for mailto: and names
  3. GitHub search   — search for company employees with public emails

Usage:
    scripts/contacts.py <app-dir> [--json]

Output saved to: <app-dir>/contacts.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from lib.common import load_env, load_meta, REPO_ROOT, USER_AGENT

HEADERS = {
    "User-Agent": USER_AGENT,
}

RECRUITER_KEYWORDS = {
    "recruiter", "talent", "hr", "human resources", "people", "hiring",
    "staffing", "acquisition", "headhunter", "talent acquisition",
    "people partner", "people ops", "talent partner",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_domain(app_dir: Path, company: str) -> str:
    """Extract domain from job.url or infer from company name."""
    job_url_path = app_dir / "job.url"
    if job_url_path.exists():
        url = job_url_path.read_text(encoding="utf-8").strip()
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        # Strip www. and job board prefixes
        for prefix in ("www.", "jobs.", "careers.", "job.", "apply.", "boards.greenhouse.io",
                       "job-boards.greenhouse.io", "api.lever.co", "jobs.ashbyhq.com"):
            if netloc.startswith(prefix):
                netloc = netloc[len(prefix):]
                break
        # If netloc contains slashes (like greenhouse: domain/company), take first part
        netloc = netloc.split("/")[0]
        # Ignore generic job boards — fall through to company name fallback
        job_boards = ("linkedin.com", "indeed.com", "glassdoor.com", "wellfound.com",
                      "monster.com", "ziprecruiter.com", "simplyhired.com")
        if "." in netloc and netloc != parsed.netloc.lower() and netloc not in job_boards:
            return netloc

    # Fallback: company name → domain guess
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    return f"{slug}.com"


def _safe_get(url, timeout=10):
    if not HAS_REQUESTS:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        return resp
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Source 1: Hunter.io API
# ---------------------------------------------------------------------------

def search_hunter(domain: str, api_key: str) -> list:
    """Search Hunter.io for email addresses at domain."""
    if not api_key:
        return []
    url = (
        f"https://api.hunter.io/v2/domain-search"
        f"?domain={urllib.parse.quote(domain)}&limit=5&api_key={api_key}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "python-contacts-script"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        contacts = []
        for e in data.get("data", {}).get("emails", []):
            contacts.append({
                "name": f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                "email": e.get("value", ""),
                "position": e.get("position", ""),
                "confidence": e.get("confidence", 0),
                "source": "hunter",
            })
        return contacts
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("   ⚠️  Hunter.io: invalid API key")
        elif e.code == 429:
            print("   ⚠️  Hunter.io: rate limit reached (25 free searches/month)")
        return []
    except Exception as e:
        print(f"   ⚠️  Hunter.io error: {e}")
        return []


# ---------------------------------------------------------------------------
# Source 2: Company website scraping
# ---------------------------------------------------------------------------

def _is_recruiter_context(text_near: str) -> bool:
    text_lower = text_near.lower()
    return any(kw in text_lower for kw in RECRUITER_KEYWORDS)


def scrape_company_website(domain: str) -> list:
    """Scrape company website for recruiter names and emails."""
    if not HAS_REQUESTS:
        return []

    contacts = []
    seen_emails = set()

    for path in ("/about", "/team", "/company", "/people", "/careers/team"):
        url = f"https://{domain}{path}"
        resp = _safe_get(url, timeout=10)
        if not resp or resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract mailto: links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("mailto:"):
                email = href[7:].split("?")[0].strip().lower()
                if email and "@" in email and email not in seen_emails:
                    # Try to get name from surrounding context
                    parent = a.find_parent(["div", "li", "p", "td"])
                    context = parent.get_text(" ", strip=True) if parent else ""
                    if _is_recruiter_context(context) or _is_recruiter_context(email):
                        seen_emails.add(email)
                        contacts.append({
                            "name": "",
                            "email": email,
                            "position": "Contact (website)",
                            "confidence": 50,
                            "source": "website",
                        })

        # Extract emails from visible text using regex
        page_text = soup.get_text(" ")
        email_re = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        for email in re.findall(email_re, page_text):
            email = email.lower()
            if email not in seen_emails and domain.split(".")[0] in email:
                seen_emails.add(email)
                contacts.append({
                    "name": "",
                    "email": email,
                    "position": "Contact (website)",
                    "confidence": 40,
                    "source": "website",
                })

        if contacts:
            break  # Stop at first page that yielded results

    return contacts[:5]


# ---------------------------------------------------------------------------
# Source 3: GitHub search
# ---------------------------------------------------------------------------

def search_github(company: str) -> list:
    """Search GitHub for company employees with public emails."""
    if not HAS_REQUESTS:
        return []

    # Normalize company name for search
    query = urllib.parse.quote(f"type:user company:{company}")
    url = f"https://api.github.com/search/users?q={query}&per_page=5"

    try:
        resp = requests.get(url, headers={**HEADERS, "Accept": "application/vnd.github+json"}, timeout=10)
        if resp.status_code == 403:
            print("   ⚠️  GitHub: rate limit reached — try again later")
            return []
        if resp.status_code != 200:
            return []
        users = resp.json().get("items", [])
    except Exception:
        return []

    contacts = []
    for user in users[:5]:
        try:
            profile_resp = requests.get(
                f"https://api.github.com/users/{user['login']}",
                headers={**HEADERS, "Accept": "application/vnd.github+json"},
                timeout=10,
            )
            if profile_resp.status_code != 200:
                continue
            profile = profile_resp.json()
            email = profile.get("email", "")
            if email:
                contacts.append({
                    "name": profile.get("name", user["login"]),
                    "email": email,
                    "position": profile.get("bio", f"@{user['login']}"),
                    "confidence": 30,
                    "source": "github",
                    "handle": user["login"],
                })
        except Exception:
            continue

    return contacts


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _pick_primary(all_contacts: list) -> dict | None:
    """Pick the best primary contact (highest confidence, prefer recruiter roles)."""
    if not all_contacts:
        return None
    # Sort: Hunter.io first (most reliable), then by confidence
    ordered = sorted(
        all_contacts,
        key=lambda c: (
            0 if c["source"] == "hunter" else 1,
            -c.get("confidence", 0),
        )
    )
    # Prefer contacts with recruiter-related positions
    for c in ordered:
        if _is_recruiter_context((c.get("position") or "") + " " + (c.get("name") or "")):
            return c
    return ordered[0]


def print_results(company: str, domain: str, hunter: list, website: list, github: list) -> None:
    print(f"\n👤 Contacts — {company} ({domain})")
    print("─" * 60)

    if hunter:
        print("\n📧 Hunter.io:")
        for c in hunter:
            print(f"   {c['name'] or '(unknown)':25} {c['email']:35} {c.get('position', '')} ({c['confidence']}%)")
    else:
        print("\n📧 Hunter.io: no results")

    if website:
        print("\n🌐 Company website:")
        for c in website:
            print(f"   {c['email']}")

    if github:
        print("\n🐙 GitHub:")
        for c in github:
            handle = c.get("handle", "")
            print(f"   @{handle:20} {c['email']:35} {c.get('name', '')}")

    all_contacts = hunter + website + github
    primary = _pick_primary(all_contacts)
    if primary:
        print(f"\n✅ Suggested contact: {primary.get('name', '')} <{primary['email']}>")
    print()


def save_contacts(app_dir: Path, company: str, domain: str,
                  hunter: list, website: list, github: list,
                  candidate_name: str = "Candidate") -> None:
    all_contacts = hunter + website + github
    primary = _pick_primary(all_contacts)
    today = date.today().isoformat()

    lines = [f"# Contacts — {company}", f"*Generated: {today} · Domain: {domain}*", ""]

    if hunter:
        lines += ["## Hunter.io", "",
                  "| Name | Email | Position | Confidence |",
                  "|------|-------|----------|------------|"]
        for c in hunter:
            lines.append(f"| {c.get('name','—')} | {c['email']} | {c.get('position','—')} | {c.get('confidence',0)}% |")
        lines.append("")

    if website:
        lines += ["## Company Website", ""]
        for c in website:
            lines.append(f"- {c['email']}")
        lines.append("")

    if github:
        lines += ["## GitHub", ""]
        for c in github:
            h = c.get("handle", "")
            lines.append(f"- [@{h}](https://github.com/{h}) — {c['email']} — {c.get('name', '')}")
        lines.append("")

    if primary:
        lines += [
            "## Suggested Next Step",
            "",
            f"**Primary contact:** {primary.get('name', '')} <{primary['email']}>",
            "",
            f"Subject: Following up on my application for [Position] — {candidate_name}",
        ]
    elif not all_contacts:
        lines += ["## No contacts found", "",
                  "- Check LinkedIn for hiring manager manually",
                  "- Try: https://www.linkedin.com/search/results/people/?keywords=" +
                  urllib.parse.quote(f"{company} recruiter talent")]
    lines.append("")

    out_path = app_dir / "contacts.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ Saved to {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    load_env()

    parser = argparse.ArgumentParser(
        description="Find recruiter/hiring manager contacts for a job application"
    )
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    meta = load_meta(app_dir)
    company = meta.get("company", app_dir.name)
    api_key = os.environ.get("HUNTER_API_KEY", "")

    if not HAS_REQUESTS:
        print("⚠️  requests/beautifulsoup4 not installed — website/GitHub scraping disabled")
        print("   pip install requests beautifulsoup4")

    domain = extract_domain(app_dir, company)
    print(f"🔍 Searching contacts for {company} ({domain})...")

    # Source 1: Hunter.io
    print("   📧 Hunter.io...", end=" ", flush=True)
    if api_key:
        hunter = search_hunter(domain, api_key)
        print(f"{'✅ ' + str(len(hunter)) + ' found' if hunter else '⚠️  none found'}")
    else:
        hunter = []
        print("⚠️  HUNTER_API_KEY not set — skipping")

    # Source 2: Company website
    print("   🌐 Company website...", end=" ", flush=True)
    website = scrape_company_website(domain)
    print(f"{'✅ ' + str(len(website)) + ' found' if website else '⚠️  none found'}")

    # Source 3: GitHub
    print("   🐙 GitHub...", end=" ", flush=True)
    github = search_github(company)
    print(f"{'✅ ' + str(len(github)) + ' found' if github else '⚠️  none found'}")

    # Load candidate name from cv.yml
    cv_src = app_dir / "cv-tailored.yml"
    if not cv_src.exists():
        cv_src = REPO_ROOT / "data" / "cv.yml"
    candidate_name = "Candidate"
    if cv_src.exists():
        with open(cv_src, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f) or {}
        personal = cv_data.get("personal", {})
        candidate_name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip() or "Candidate"

    if args.json:
        all_contacts = hunter + website + github
        print(json.dumps(all_contacts, indent=2, ensure_ascii=False))
    else:
        print_results(company, domain, hunter, website, github)
        save_contacts(app_dir, company, domain, hunter, website, github,
                      candidate_name=candidate_name)


if __name__ == "__main__":
    main()
