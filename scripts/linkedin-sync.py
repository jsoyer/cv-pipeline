#!/usr/bin/env python3
"""
Sync CV data from YAML to LinkedIn profile.

Reads data/cv.yml and pushes to LinkedIn via their API.
Controlled by LINKEDIN_PUSH in .env (true/false).

Usage:
    scripts/linkedin-sync.py                # dry-run (show what would be pushed)
    scripts/linkedin-sync.py --push         # actually push to LinkedIn
    scripts/linkedin-sync.py --export       # export LinkedIn-ready JSON

Requires:
    LINKEDIN_ACCESS_TOKEN in .env
    LINKEDIN_PUSH=true in .env (or --push flag)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from lib.common import require_yaml, load_env

yaml = require_yaml()


API_BASE = "https://api.linkedin.com/v2"


def strip_bold(text):
    """Remove **bold** markers."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def linkedin_api(endpoint, token, method="GET", data=None):
    """Make a LinkedIn API request."""
    url = f"{API_BASE}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"LinkedIn API error ({e.code}): {error_body}")


def build_linkedin_profile(cv_data):
    """Build LinkedIn-compatible profile data from CV YAML."""
    p = cv_data["personal"]

    profile = {
        "headline": p["position"],
        "summary": strip_bold(cv_data["profile"]),
        "firstName": p["first_name"],
        "lastName": p["last_name"],
        "location": p["address"],
    }

    # Build positions
    positions = []
    for exp in cv_data.get("experience", []):
        position = {
            "title": exp["title"],
            "company": exp["company"],
            "location": exp["location"],
            "dateRange": exp["dates"],
        }
        items = exp.get("items", [])
        if items:
            bullets = []
            for it in items:
                text = strip_bold(it["text"])
                label = it.get("label")
                if label:
                    bullets.append(f"{label}: {text}")
                else:
                    bullets.append(text)
            position["description"] = "\n".join(f"• {b}" for b in bullets)
        positions.append(position)

    # Add early career
    for exp in cv_data.get("early_career", []):
        positions.append({
            "title": exp["title"],
            "company": exp["company"],
            "location": exp["location"],
            "dateRange": exp["dates"],
        })

    profile["positions"] = positions

    # Education
    education = []
    for edu in cv_data.get("education", []):
        entry = {
            "degree": edu["degree"],
            "school": edu["school"],
            "dateRange": edu["dates"],
        }
        if edu.get("note"):
            entry["description"] = edu["note"]
        education.append(entry)
    profile["education"] = education

    # Skills
    skills = []
    for skill_group in cv_data.get("skills", []):
        for skill in skill_group["items"].split(", "):
            skills.append(skill.strip())
    profile["skills"] = skills

    # Certifications
    certifications = []
    for cert in cv_data.get("certifications", []):
        certifications.append({
            "name": cert["name"],
            "authority": cert["institution"],
            "date": cert["date"],
        })
    profile["certifications"] = certifications

    # Languages
    profile["languages"] = cv_data.get("languages", [])

    return profile


def push_to_linkedin(profile, token):
    """Push profile data to LinkedIn API."""
    # Get current user URN
    me = linkedin_api("me", token)
    urn = me.get("id")
    if not urn:
        print("❌ Could not get LinkedIn user ID")
        sys.exit(1)

    print(f"👤 LinkedIn user: {me.get('localizedFirstName', '')} {me.get('localizedLastName', '')}")
    print(f"   URN: {urn}")
    print()

    # Update headline/summary
    # Note: LinkedIn v2 API has limited profile update capabilities.
    # Full profile updates require the r_liteprofile and w_member_social scopes.
    # This pushes what's available via the API.

    print("📝 Updating headline...")
    try:
        linkedin_api(
            f"people/(id:{urn})",
            token,
            method="POST",
            data={"headline": {"localized": {"en_US": profile["headline"]}}},
        )
        print("   ✅ Headline updated")
    except RuntimeError as e:
        print(f"   ⚠️  {e}")
        print("   💡 Use --export to generate LinkedIn-ready JSON for manual import")

    print()
    print("✅ LinkedIn sync complete")
    print("   💡 For full profile updates, use LinkedIn's import feature")
    print("      with: scripts/linkedin-sync.py --export")


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Sync CV data to LinkedIn")
    parser.add_argument("-d", "--data", default="data/cv.yml",
                        help="YAML data file (default: data/cv.yml)")
    parser.add_argument("--push", action="store_true",
                        help="Actually push to LinkedIn (default: dry-run)")
    parser.add_argument("--export", action="store_true",
                        help="Export LinkedIn-ready JSON to stdout")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"❌ Data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        cv_data = yaml.safe_load(f)

    profile = build_linkedin_profile(cv_data)

    # Export mode
    if args.export:
        print(json.dumps(profile, indent=2, ensure_ascii=False))
        return 0

    # Check .env switch
    env_push = os.environ.get("LINKEDIN_PUSH", "false").lower() == "true"
    should_push = args.push or env_push

    if not should_push:
        print("🔍 DRY RUN — showing what would be pushed to LinkedIn")
        print("   (use --push flag or set LINKEDIN_PUSH=true in .env)")
        print()
        print(f"  Headline:      {profile['headline']}")
        print(f"  Location:      {profile['location']}")
        print(f"  Summary:       {profile['summary'][:80]}...")
        print(f"  Positions:     {len(profile['positions'])}")
        print(f"  Education:     {len(profile['education'])}")
        print(f"  Skills:        {len(profile['skills'])}")
        print(f"  Certifications:{len(profile['certifications'])}")
        print(f"  Languages:     {', '.join(profile['languages'])}")
        print()
        print("👉 To push: scripts/linkedin-sync.py --push")
        print("👉 To export JSON: scripts/linkedin-sync.py --export")
        return 0

    # Push mode
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    if not token:
        print("❌ LINKEDIN_ACCESS_TOKEN not set")
        print("   Add it to .env or export it")
        print("   Get a token at: https://www.linkedin.com/developers/apps")
        sys.exit(1)

    push_to_linkedin(profile, token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
