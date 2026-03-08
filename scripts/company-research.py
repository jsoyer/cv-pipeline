#!/usr/bin/env python3
"""
Company Research — Fetch company intelligence from public sources.

Sources:
  1. Company website (description, size hints)
  2. Google News RSS (recent news)
  3. StackShare (tech stack)
  4. Crunchbase public (funding — often blocked, graceful fallback)

Output:
  - applications/NAME/company-research.md
  - Updates applications/NAME/meta.yml with structured fields

No API key required.

Usage:
    scripts/company-research.py <application-dir>
    scripts/company-research.py <application-dir> --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ Missing deps: pip install requests beautifulsoup4")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("❌ Missing deps: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT, USER_AGENT

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Employee count patterns → company size classification
SIZE_PATTERNS = [
    (r"(\d[\d,]+)\s*(?:\+)?\s*employees?", None),
    (r"team\s+of\s+(\d[\d,]+)", None),
    (r"over\s+(\d[\d,]+)\s*(?:people|employees|professionals)", None),
    (r"(\d[\d,]+)\s*(?:people|professionals|team members)", None),
]


def classify_size(employee_count: int) -> str:
    if employee_count < 200:
        return "startup"
    elif employee_count < 2000:
        return "mid-market"
    else:
        return "enterprise"


def get_request(url: str, timeout: int = 15) -> requests.Response | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


def fetch_company_website(company_name: str, job_url: str = "") -> dict:
    """Scrape company website for description and size hints."""
    result = {"description": "", "company_size": "", "hq": "", "source_url": ""}

    # Determine base URL
    base_url = ""
    if job_url:
        try:
            parsed = urlparse(job_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass

    urls_to_try = []
    if base_url:
        urls_to_try.append(base_url)
        urls_to_try.append(f"{base_url}/about")
        urls_to_try.append(f"{base_url}/company")

    # Fallback: try company slug as domain
    slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
    if slug:
        urls_to_try.append(f"https://www.{slug}.com")
        urls_to_try.append(f"https://{slug}.com/about")

    for url in urls_to_try:
        resp = get_request(url)
        if not resp:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract description: try meta description first
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if not meta_desc:
            meta_desc = soup.find("meta", attrs={"property": "og:description"})
        if meta_desc and meta_desc.get("content"):
            desc = meta_desc["content"].strip()
            if len(desc) >= 50:
                result["description"] = desc[:500]

        # If no meta, find first substantial paragraph
        if not result["description"]:
            for tag in ["p", "div"]:
                for el in soup.find_all(tag):
                    text = el.get_text(strip=True)
                    if 80 <= len(text) <= 600 and not text.startswith("<"):
                        result["description"] = text[:500]
                        break
                if result["description"]:
                    break

        # Employee count
        page_text = soup.get_text()
        for pattern, _ in SIZE_PATTERNS:
            m = re.search(pattern, page_text, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(",", "")
                try:
                    count = int(raw)
                    result["company_size"] = classify_size(count)
                except ValueError:
                    pass
                break

        # HQ hint
        hq_patterns = [
            r"headquartered? (?:in|at) ([A-Z][a-zA-Z\s,]+?)(?:\.|,|\s{2}|$)",
            r"based in ([A-Z][a-zA-Z\s,]+?)(?:\.|,|\s{2}|$)",
        ]
        for pat in hq_patterns:
            m = re.search(pat, page_text)
            if m:
                result["hq"] = m.group(1).strip()[:50]
                break

        result["source_url"] = url
        if result["description"]:
            break

    return result


def fetch_google_news(company_name: str) -> list:
    """Fetch recent news via Google News RSS."""
    results = []
    query = quote_plus(f'"{company_name}"')
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    resp = get_request(url, timeout=15)
    if not resp:
        return results

    try:
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if not channel:
            return results

        for item in channel.findall("item")[:5]:
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")

            if not title_el or not title_el.text:
                continue

            # Parse date
            date_str = ""
            if pub_el and pub_el.text:
                try:
                    dt = datetime.strptime(pub_el.text[:16], "%a, %d %b %Y")
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    date_str = pub_el.text[:10] if pub_el.text else ""

            # Clean up Google News redirect URLs
            link = link_el.text if link_el and link_el.text else ""
            # Google News links often go through redir — keep as-is
            if not link.startswith("http"):
                link = ""

            results.append({
                "date": date_str,
                "title": title_el.text.strip(),
                "url": link,
            })
    except ET.ParseError:
        pass

    return results[:3]


def fetch_stackshare(company_name: str) -> list:
    """Scrape StackShare for tech stack (may return empty if blocked)."""
    slug = re.sub(r"[^a-z0-9-]", "-", company_name.lower()).strip("-")
    url = f"https://stackshare.io/{slug}"

    resp = get_request(url, timeout=12)
    if not resp or resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    tech_items = []

    # StackShare uses various structures — try common patterns
    # Pattern 1: data-name attributes
    for el in soup.find_all(attrs={"data-name": True}):
        name = el["data-name"].strip()
        if name and len(name) >= 2 and len(name) <= 30:
            tech_items.append(name)

    # Pattern 2: links in tool sections
    if not tech_items:
        for a in soup.find_all("a", href=re.compile(r"^/[a-z]")):
            title = a.get("title", "").strip()
            if title and len(title) >= 2 and len(title) <= 30:
                tech_items.append(title)

    # Pattern 3: alt text on images in stacks
    if not tech_items:
        for img in soup.find_all("img", alt=True):
            alt = img["alt"].strip()
            if 2 <= len(alt) <= 30 and not alt.lower().startswith("logo"):
                tech_items.append(alt)

    # Deduplicate and filter noise
    seen = set()
    clean = []
    for item in tech_items:
        key = item.lower()
        if key not in seen and len(item) > 1:
            seen.add(key)
            clean.append(item)

    return clean[:12]


def fetch_crunchbase(company_name: str) -> str:
    """Attempt to get funding info from Crunchbase (often blocked)."""
    slug = re.sub(r"[^a-z0-9-]", "-", company_name.lower()).strip("-")
    url = f"https://www.crunchbase.com/organization/{slug}"

    resp = get_request(url, timeout=12)
    if not resp or resp.status_code in (403, 429, 503):
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text()

    # Look for funding patterns
    funding_patterns = [
        r"raised?\s+\$[\d.,]+[MBK]",
        r"Series [A-Z]\s+[•·-]\s+\$[\d.,]+[MBK]",
        r"\$[\d.,]+[MBK]\s+(?:in\s+)?(?:Series|Seed|Round)",
        r"total\s+funding[:\s]+\$[\d.,]+[MBK]",
    ]
    for pat in funding_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()

    return ""


def update_meta_yml(meta_path: Path, updates: dict) -> None:
    """Add new fields to meta.yml without overwriting existing content."""
    try:
        with open(meta_path, encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}
    except Exception:
        existing = {}

    # Only add new fields, don't overwrite existing
    changed = False
    for key, value in updates.items():
        if key not in existing and value:
            existing[key] = value
            changed = True

    if changed:
        # Write back preserving order (basic yaml.dump)
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.dump(existing, f, default_flow_style=False, allow_unicode=True,
                      sort_keys=False)


def main():
    parser = argparse.ArgumentParser(
        prog="company-research.py",
        description=(
            "Company Research — Fetch company intelligence from public sources.\n\n"
            "Sources: company website, Google News RSS, StackShare, Crunchbase. "
            "Writes company-research.md and updates meta.yml. No API key required."
        ),
    )
    parser.add_argument(
        "app_dir",
        metavar="application-dir",
        help="Path to the application directory (must contain meta.yml with a 'company' field)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_mode",
        help="Also print the full result as JSON after writing files",
    )
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    json_mode = args.json_mode

    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    # Load meta.yml
    meta_path = app_dir / "meta.yml"
    meta = {}
    if meta_path.exists():
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except Exception:
            pass

    company_name = meta.get("company", "")
    if not company_name:
        print(f"❌ No 'company' field in {meta_path}")
        sys.exit(1)

    # Read job URL hint
    job_url = ""
    url_path = app_dir / "job.url"
    if url_path.exists():
        try:
            job_url = url_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    app_name = app_dir.name
    print(f"🔍 Researching: {company_name}  ({app_name})")

    sources_used = []

    # ── Source 1: Company website ─────────────────────────────────────
    print("   📄 Company website...", end=" ", flush=True)
    website_data = fetch_company_website(company_name, job_url)
    if website_data.get("description"):
        print("✅ Description extracted")
        sources_used.append("website")
    else:
        print("⚠️  No description found")

    # ── Source 2: Google News RSS ─────────────────────────────────────
    print("   📡 Google News RSS...", end=" ", flush=True)
    news = fetch_google_news(company_name)
    if news:
        print(f"✅ {len(news)} news item(s)")
        sources_used.append("google_news")
    else:
        print("⚠️  No recent news found")

    # ── Source 3: StackShare ──────────────────────────────────────────
    print("   🛠️  StackShare...", end="      ", flush=True)
    tech_stack = fetch_stackshare(company_name)
    if tech_stack:
        print(f"✅ {len(tech_stack)} technologies found")
        sources_used.append("stackshare")
    else:
        print("⚠️  Not found or blocked")

    # ── Source 4: Crunchbase ──────────────────────────────────────────
    print("   💰 Crunchbase...", end="      ", flush=True)
    funding = fetch_crunchbase(company_name)
    if funding:
        print(f"✅ {funding}")
        sources_used.append("crunchbase")
    else:
        print("⚠️  Blocked (normal)")

    print()

    # ── Assemble results ──────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    result = {
        "company": company_name,
        "company_size": website_data.get("company_size", ""),
        "description": website_data.get("description", ""),
        "hq": website_data.get("hq", ""),
        "tech_stack": tech_stack,
        "last_funding": funding,
        "recent_news": news,
        "sources_used": sources_used,
        "generated": today,
    }

    # ── Write company-research.md ─────────────────────────────────────
    md_path = app_dir / "company-research.md"
    lines = [f"# Company Research: {company_name}", "", f"**Generated:** {today}", ""]

    if result["description"]:
        lines += ["## Overview", "", result["description"], ""]
    if result["company_size"]:
        lines.append(f"**Size:** {result['company_size'].title()}")
    if result["hq"]:
        lines.append(f"**HQ:** {result['hq']}")
    if result["company_size"] or result["hq"]:
        lines.append("")

    if tech_stack:
        lines += ["## Tech Stack", "", "- " + ", ".join(tech_stack), ""]

    if funding:
        lines += ["## Funding", "", f"- {funding}", ""]

    if news:
        lines += ["## Recent News", ""]
        for item in news:
            date = f"[{item['date']}] " if item["date"] else ""
            link = f"  ({item['url']})" if item["url"] else ""
            lines.append(f"- {date}{item['title']}{link}")
        lines.append("")

    # Interview prep notes
    lines += [
        "## Notes for Interview",
        "",
        "*(Add your personal notes here)*",
        "",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ company-research.md saved → {md_path}")

    # ── Update meta.yml ───────────────────────────────────────────────
    meta_updates: dict = {}
    if result["company_size"]:
        meta_updates["company_size"] = result["company_size"]
    if tech_stack:
        meta_updates["tech_stack"] = tech_stack
    if news:
        meta_updates["recent_news"] = [
            {k: v for k, v in item.items() if v} for item in news
        ]

    if meta_updates and meta_path.exists():
        update_meta_yml(meta_path, meta_updates)
        updated_fields = ", ".join(meta_updates.keys())
        print(f"✅ meta.yml updated with: {updated_fields}")
    print()

    if json_mode:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print(f"💡 View notes: cat {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
