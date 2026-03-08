#!/usr/bin/env python3
"""
Fetch job description from URL and save as job.txt.

Usage:
    scripts/fetch-job.py <application-dir>
    scripts/fetch-job.py --extract <URL>   # print {"company": "...", "position": "..."} as JSON
"""

import argparse
import json
import os
import re
import sys

try:
    import requests
except ImportError:
    print("❌ requests required: pip install requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ beautifulsoup4 required: pip install beautifulsoup4")
    sys.exit(1)

from lib.common import USER_AGENT

HEADERS = {
    "User-Agent": USER_AGENT,
}

REMOVE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_via_jina(url):
    """Fetch via Jina Reader API — handles JS-rendered SPAs. Returns plain text."""
    jina_url = f"https://r.jina.ai/{url}"
    resp = requests.get(jina_url, headers={"Accept": "text/plain", **HEADERS}, timeout=120)
    resp.raise_for_status()
    return resp.text


def fetch_url(url):
    """Fetch URL. Returns (text, html) tuple. Falls back to Jina Reader if text is sparse (<50 words)."""
    resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    html = resp.text
    text = extract_text(html)
    if len(text.split()) < 50:
        print("⚡ SPA detected — trying Jina Reader...")
        try:
            jina_text = fetch_via_jina(url)
            if len(jina_text.split()) > len(text.split()):
                text = jina_text
                print(f"   ✓ Jina returned {len(text.split())} words")
            else:
                print("   ⚠️  Jina returned no additional content")
        except Exception as e:
            print(f"   ⚠️  Jina fallback failed: {e}")
    return text, html


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(html):
    """Extract clean text from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in REMOVE_TAGS:
        for el in soup.find_all(tag):
            el.decompose()

    # Try to find job description container
    content = None
    for selector in ["article", "main", "[class*=job]", "[class*=description]",
                     "[class*=posting]", "[id*=job]", "[role=main]"]:
        content = soup.select_one(selector)
        if content:
            break

    if not content:
        content = soup.body or soup

    text = content.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ---------------------------------------------------------------------------
# Company / position extraction (for --extract mode)
# ---------------------------------------------------------------------------

def _extract_from_url(url):
    """Extract company from well-known ATS URL patterns. Returns (company, '') or ('', '')."""
    # Greenhouse: https://job-boards.greenhouse.io/COMPANY/jobs/ID
    m = re.search(r"greenhouse\.io/([^/]+)/jobs", url)
    if m:
        return m.group(1).replace("-", " ").title(), ""

    # Lever: https://jobs.lever.co/COMPANY/UUID
    m = re.search(r"jobs\.lever\.co/([^/?]+)", url)
    if m:
        return m.group(1).replace("-", " ").title(), ""

    # Workday: https://COMPANY.wd1.myworkdayjobs.com/...
    m = re.search(r"([^.]+)\.wd\d+\.myworkdayjobs\.com", url)
    if m:
        return m.group(1).replace("-", " ").title(), ""

    # Ashby subdomain: https://COMPANY.ashbyhq.com/...
    m = re.search(r"([^.]+)\.ashbyhq\.com", url)
    if m:
        return m.group(1).replace("-", " ").title(), ""

    # SmartRecruiters: https://jobs.smartrecruiters.com/COMPANY/ID
    m = re.search(r"smartrecruiters\.com/([^/]+)/", url)
    if m:
        return m.group(1).replace("-", " ").title(), ""

    return "", ""


def _extract_from_html(html):
    """Extract company and position from HTML meta tags and headings.
    Returns (company, position) — empty strings if not found."""
    soup = BeautifulSoup(html, "html.parser")

    company = ""
    position = ""

    # og:site_name → company
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        company = og_site["content"].strip()

    # og:title or <title> → parse "Position at Company" / "Company — Position" / "Company | Position"
    og_title = soup.find("meta", property="og:title")
    title_text = (og_title["content"] if og_title and og_title.get("content")
                  else soup.title.string if soup.title else "")
    title_text = (title_text or "").strip()

    if title_text:
        # Pattern: "Position at Company"
        m = re.match(r"^(.+?)\s+at\s+(.+?)(?:\s*[-|—].*)?$", title_text, re.IGNORECASE)
        if m:
            position = position or m.group(1).strip()
            company = company or m.group(2).strip()
        else:
            # Pattern: "Company — Position" or "Company | Position" or "Company - Position"
            m = re.match(r"^(.+?)\s*[—|–|-]\s*(.+)$", title_text)
            if m:
                # Heuristic: shorter part is usually the company
                part1, part2 = m.group(1).strip(), m.group(2).strip()
                if len(part1) <= len(part2):
                    company = company or part1
                    position = position or part2
                else:
                    company = company or part2
                    position = position or part1

    # First <h1> as position fallback
    if not position:
        h1 = soup.find("h1")
        if h1:
            position = h1.get_text(strip=True)

    # Clean up trailing site names from position (e.g. "Senior SE - Figma - Greenhouse")
    if company and position and company.lower() in position.lower():
        position = re.sub(re.escape(company), "", position, flags=re.IGNORECASE).strip(" -—|")

    return company, position


def extract_job_info(url, text, html):
    """Extract company and position from URL, HTML, and text content.
    Returns {"company": str, "position": str}."""
    company, position = _extract_from_url(url)
    html_company, html_position = _extract_from_html(html)

    # Prefer HTML extraction for position (more accurate), URL extraction for company (reliable)
    company = company or html_company
    position = position or html_position

    # Clean whitespace
    company = re.sub(r"\s+", " ", company).strip()
    position = re.sub(r"\s+", " ", position).strip()

    return {"company": company, "position": position}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="fetch-job.py",
        description=(
            "Fetch job description from URL and save as job.txt.\n\n"
            "Reads job.url from the application directory, fetches the page "
            "(with Jina Reader fallback for SPAs), and writes job.txt.\n\n"
            "Alternatively, use --extract <URL> to extract company/position "
            "metadata from a URL and print it as JSON."
        ),
    )
    parser.add_argument(
        "app_dir",
        metavar="application-dir",
        nargs="?",
        help="Path to the application directory (must contain job.url)",
    )
    parser.add_argument(
        "--extract",
        metavar="URL",
        dest="extract_url",
        help='Extract company/position from URL and print as JSON {"company": ..., "position": ...}',
    )
    args = parser.parse_args()

    if not args.extract_url and not args.app_dir:
        parser.error("provide an application-dir or --extract URL")

    # --extract URL mode: print company/position as JSON
    if args.extract_url:
        url = args.extract_url
        try:
            text, html = fetch_url(url)
        except Exception as e:
            print(f"⚠️  Could not fetch URL: {e}", file=sys.stderr)
            text, html = "", ""
        info = extract_job_info(url, text, html)
        print(json.dumps(info))
        return 0

    app_dir = args.app_dir
    if not os.path.isdir(app_dir):
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    # Check for existing job.txt
    out_path = os.path.join(app_dir, "job.txt")
    if os.path.exists(out_path):
        print(f"⚠️  {out_path} already exists — overwriting")

    # Read URL
    url_file = os.path.join(app_dir, "job.url")
    if not os.path.exists(url_file):
        print(f"❌ No job.url found in {app_dir}/")
        sys.exit(1)

    with open(url_file, encoding="utf-8") as f:
        url = f.read().strip().replace("\\", "")

    if not url:
        print("❌ job.url is empty")
        sys.exit(1)

    print(f"🌐 Fetching: {url}")

    try:
        text, _ = fetch_url(url)
    except Exception as e:
        print(f"❌ Failed to fetch URL: {e}")
        print("   Try saving the job description manually as job.txt")
        sys.exit(1)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    words = len(text.split())
    print(f"✅ Saved {out_path} ({words} words)")
    print(f"   👉 Next: make score NAME={os.path.basename(app_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
