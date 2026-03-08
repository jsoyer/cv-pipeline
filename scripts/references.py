#!/usr/bin/env python3
"""
Manage professional references and generate reference request emails.

Data store: data/references.yml

Actions:
    list            — List all saved references
    add             — Add a new reference
    request <dir>   — Generate a reference request email for an application
    show <name>     — Show full details for one reference

Usage:
    scripts/references.py list
    scripts/references.py add --name "Jane Doe" --title "VP Sales" \
        --company "Acme" --email "jane@acme.com" --relationship "Former manager"
    scripts/references.py request applications/2026-02-cloudflare [--ref "Jane Doe"]
    scripts/references.py show "Jane Doe"
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT
_REFS_FILE = REPO_ROOT / "data" / "references.yml"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_refs() -> list:
    if not _REFS_FILE.exists():
        return []
    with open(_REFS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("references", [])


def save_refs(refs: list) -> None:
    _REFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REFS_FILE, "w", encoding="utf-8") as f:
        yaml.dump({"references": refs}, f, allow_unicode=True,
                  default_flow_style=False, sort_keys=False)


def _find_ref(refs: list, name: str) -> dict | None:
    name_l = name.lower()
    for r in refs:
        if r.get("name", "").lower() == name_l:
            return r
    # partial match
    for r in refs:
        if name_l in r.get("name", "").lower():
            return r
    return None


def _load_app_meta(app_dir: Path) -> dict:
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return {}
    with open(meta_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(_args) -> int:
    refs = load_refs()
    if not refs:
        print("📋 No references saved yet.")
        print(f"   Add one: scripts/references.py add --name \"Jane Doe\" ...")
        return 0

    print(f"\n📋 References ({len(refs)})\n")
    print(f"   {'Name':<25}  {'Title':<30}  {'Company':<20}  Contact")
    print("   " + "─" * 85)
    for r in refs:
        name     = r.get("name", "?")[:24]
        title    = r.get("title", "")[:29]
        company  = r.get("company", "")[:19]
        email    = r.get("email", r.get("phone", ""))
        print(f"   {name:<25}  {title:<30}  {company:<20}  {email}")
    print()
    return 0


def cmd_add(args) -> int:
    if not args.name:
        print("❌ --name required")
        return 1

    refs = load_refs()

    # Check duplicate
    existing = _find_ref(refs, args.name)
    if existing:
        print(f"⚠️  Reference '{existing['name']}' already exists — updating.")
        refs.remove(existing)

    ref = {
        "name":         args.name,
        "title":        args.title or "",
        "company":      args.company or "",
        "email":        args.email or "",
        "phone":        args.phone or "",
        "relationship": args.relationship or "",
        "notes":        args.notes or "",
        "added":        date.today().isoformat(),
    }
    # Remove empty fields
    ref = {k: v for k, v in ref.items() if v}

    refs.append(ref)
    save_refs(refs)
    print(f"✅ Saved reference: {args.name} ({args.title or ''} at {args.company or ''})")
    return 0


def cmd_show(args) -> int:
    if not args.ref_name:
        print("❌ Reference name required")
        return 1

    refs = load_refs()
    ref = _find_ref(refs, args.ref_name)
    if not ref:
        print(f"❌ Reference not found: {args.ref_name}")
        if refs:
            print("   Available: " + ", ".join(r["name"] for r in refs))
        return 1

    print(f"\n📄 Reference: {ref['name']}")
    for k, v in ref.items():
        if k != "name" and v:
            print(f"   {k.capitalize():<15} {v}")
    print()
    return 0


def cmd_request(args) -> int:
    if not args.app_dir:
        print("❌ Application directory required")
        return 1

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        return 1

    refs = load_refs()
    if not refs:
        print("❌ No references saved. Add one first: scripts/references.py add ...")
        return 1

    meta    = _load_app_meta(app_dir)
    company = meta.get("company", app_dir.name)
    position = meta.get("position", "the position")
    today   = date.today().isoformat()

    # Select which references to use
    if args.ref:
        selected = [_find_ref(refs, args.ref)]
        if not selected[0]:
            print(f"❌ Reference not found: {args.ref}")
            print("   Available: " + ", ".join(r["name"] for r in refs))
            return 1
    else:
        selected = refs  # generate for all

    out_lines = [
        f"# Reference Request Emails — {company}",
        f"*{position} · Generated: {today}*",
        "",
        "---",
        "",
    ]

    for ref in selected:
        ref_name     = ref.get("name", "")
        ref_title    = ref.get("title", "")
        ref_company  = ref.get("company", "")
        relationship = ref.get("relationship", "colleague")

        # Determine salutation
        first_name = ref_name.split()[0] if ref_name else "there"

        # Build the email
        subject = f"Reference request — {company} / {position}"

        body_lines = [
            f"Hi {first_name},",
            "",
            f"I hope you're doing well. I wanted to reach out because I'm in the running "
            f"for a {position} role at {company} and I'd be grateful if you'd be willing "
            f"to serve as a professional reference.",
            "",
            f"Given our time working together"
            + (f" at {ref_company}" if ref_company else "")
            + f", I believe you'd be well-placed to speak to my track record in leading "
            f"SE organisations, driving ARR growth, and managing complex technical programs.",
            "",
            f"The process is likely to move quickly, so if you're comfortable, they may "
            f"reach out within the next 2-3 weeks. I'll keep you posted on timelines.",
            "",
            f"Of course I'm happy to provide any context you'd need, or reciprocate in any "
            f"way I can. Please let me know if you have any questions.",
            "",
            "Many thanks,",
            "Jérôme",
        ]

        out_lines += [
            f"## {ref_name}",
        ]
        if ref_title or ref_company:
            out_lines.append(f"*{ref_title}{' — ' if ref_title and ref_company else ''}{ref_company}*")
        if ref.get("email"):
            out_lines.append(f"**To:** {ref.get('email')}")

        out_lines += [
            "",
            f"**Subject:** {subject}",
            "",
            "```",
        ] + body_lines + [
            "```",
            "",
        ]

    out_lines += [
        "---",
        "## Tips",
        "",
        "- Send at least 2 weeks before you expect the reference check",
        "- Brief your reference: share the JD + 2-3 key talking points",
        "- Follow up to thank them regardless of outcome",
        "",
    ]

    out_path = app_dir / "reference-request.md"
    out_path.write_text("\n".join(out_lines), encoding="utf-8")

    count = len(selected)
    print(f"✅ Generated {count} reference request email{'s' if count > 1 else ''} → {out_path}")

    # Print to terminal
    for ref in selected:
        print(f"\n   📄 {ref.get('name')} ({ref.get('email', 'no email')})")

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMANDS = {
    "list":    cmd_list,
    "add":     cmd_add,
    "show":    cmd_show,
    "request": cmd_request,
}


def main():
    parser = argparse.ArgumentParser(description="Manage professional references")
    subparsers = parser.add_subparsers(dest="action")

    # list
    subparsers.add_parser("list", help="List all references")

    # add
    p_add = subparsers.add_parser("add", help="Add a new reference")
    p_add.add_argument("--name", required=True, help="Full name")
    p_add.add_argument("--title", default="", help="Job title")
    p_add.add_argument("--company", default="", help="Company name")
    p_add.add_argument("--email", default="", help="Email address")
    p_add.add_argument("--phone", default="", help="Phone number")
    p_add.add_argument("--relationship", default="", help="e.g. 'Former manager at Varonis'")
    p_add.add_argument("--notes", default="", help="Private notes")

    # show
    p_show = subparsers.add_parser("show", help="Show one reference's details")
    p_show.add_argument("ref_name", nargs="?", help="Reference name")

    # request
    p_req = subparsers.add_parser("request", help="Generate reference request email(s)")
    p_req.add_argument("app_dir", nargs="?", help="Application directory")
    p_req.add_argument("--ref", default="", help="Specific reference name (default: all)")

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return 0

    return COMMANDS[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
