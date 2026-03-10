#!/usr/bin/env python3
"""
Template Marketplace Client — browse and install LaTeX CV templates.

Registry: https://raw.githubusercontent.com/janedoe/cv-templates/main/registry.json

Usage:
    scripts/template-market.py list [--tag TAG] [--json]
    scripts/template-market.py search QUERY [--json]
    scripts/template-market.py info NAME
    scripts/template-market.py install NAME
    scripts/template-market.py installed [--json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import REPO_ROOT, USER_AGENT

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGISTRY_URL = "https://raw.githubusercontent.com/janedoe/cv-templates/main/registry.json"
TEMPLATES_BASE_URL = "https://raw.githubusercontent.com/janedoe/cv-templates/main/templates"
FETCH_TIMEOUT = 10  # seconds

BUILT_INS: list[dict] = [
    {
        "name": "awesome-cv",
        "description": "Classic Awesome-CV (default, built-in)",
        "author": "posquit0 / janedoe",
        "version": "1.0.0",
        "built_in": True,
        "tags": ["professional", "sidebar", "colorful"],
    },
    {
        "name": "moderncv",
        "description": "ModernCV — TeX Live built-in, multiple styles",
        "author": "Xavier Danaux",
        "version": "2.3.1",
        "built_in": True,
        "tags": ["professional", "classic", "minimal"],
    },
    {
        "name": "deedy",
        "description": "Deedy-Resume style — 1 page, 2-column",
        "author": "Debarghya Das / janedoe",
        "version": "1.0.0",
        "built_in": True,
        "tags": ["tech", "one-page", "two-column"],
    },
]

BUILT_IN_NAMES: frozenset[str] = frozenset(t["name"] for t in BUILT_INS)

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _fetch_registry() -> list[dict] | None:
    """Download registry.json. Returns list of template dicts, or None on error."""
    req = urllib.request.Request(REGISTRY_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("templates", [])
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None


def _get_templates(offline_fallback: bool = True) -> tuple[list[dict], bool]:
    """Return (templates, is_online).

    Falls back to built-ins only when the registry is unreachable.
    """
    registry = _fetch_registry()
    if registry is not None:
        return registry, True
    if offline_fallback:
        return list(BUILT_INS), False
    return list(BUILT_INS), False


# ---------------------------------------------------------------------------
# Installed templates
# ---------------------------------------------------------------------------


def _get_installed() -> list[dict]:
    """Return list of locally installed (non-built-in) template dicts."""
    templates_dir = REPO_ROOT / "templates"
    installed: list[dict] = []
    if templates_dir.is_dir():
        for d in sorted(templates_dir.iterdir()):
            if not d.is_dir():
                continue
            name = d.name
            # Try to read template.yml for metadata
            meta: dict = {}
            meta_path = d / "template.yml"
            if meta_path.exists():
                try:
                    # Simple YAML key: value parser (avoid yaml dep)
                    for line in meta_path.read_text(encoding="utf-8").splitlines():
                        if ":" in line and not line.startswith("#"):
                            k, _, v = line.partition(":")
                            meta[k.strip()] = v.strip().strip('"').strip("'")
                except OSError:
                    pass
            installed.append(
                {
                    "name": name,
                    "description": meta.get("description", ""),
                    "author": meta.get("author", ""),
                    "version": meta.get("version", ""),
                    "built_in": False,
                    "tags": [t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                    "installed": True,
                }
            )
    return installed


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _fmt_tags(tags: list[str]) -> str:
    return "  ".join(f"[{t}]" for t in tags) if tags else ""


def _print_template_row(t: dict, *, show_status: bool = False) -> None:
    name = t["name"]
    desc = t.get("description", "")
    author = t.get("author", "")
    version = t.get("version", "")
    tags = _fmt_tags(t.get("tags", []))

    status_parts: list[str] = []
    if t.get("built_in"):
        status_parts.append("built-in")
    if t.get("installed"):
        status_parts.append("installed")
    status = f" ({', '.join(status_parts)})" if status_parts and show_status else ""

    print(f"  {name:<20} {desc}")
    if author or version:
        print(f"  {'':20} by {author}  v{version}{status}")
    if tags:
        print(f"  {'':20} {tags}")
    print()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    templates, is_online = _get_templates()
    if not is_online:
        print(
            "Warning: registry unreachable — showing built-in templates only.",
            file=sys.stderr,
        )

    tag_filter: str | None = getattr(args, "tag", None)
    if tag_filter:
        templates = [t for t in templates if tag_filter.lower() in [x.lower() for x in t.get("tags", [])]]

    if args.json:
        print(json.dumps({"templates": templates, "online": is_online}, indent=2))
        return 0

    print(f"\nAvailable templates ({len(templates)}):\n")
    for t in templates:
        _print_template_row(t, show_status=True)

    if not is_online:
        print("(tip: check your internet connection for the full marketplace)")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = args.query.lower()
    templates, is_online = _get_templates()
    if not is_online:
        print(
            "Warning: registry unreachable — searching built-in templates only.",
            file=sys.stderr,
        )

    results = [
        t
        for t in templates
        if query in t.get("name", "").lower()
        or query in t.get("description", "").lower()
        or any(query in tag.lower() for tag in t.get("tags", []))
        or query in t.get("author", "").lower()
    ]

    if args.json:
        print(json.dumps({"query": query, "results": results, "online": is_online}, indent=2))
        return 0

    if not results:
        print(f"No templates matched '{args.query}'.")
        return 0

    print(f"\nSearch results for '{args.query}' ({len(results)} found):\n")
    for t in results:
        _print_template_row(t, show_status=True)
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    name = args.name
    templates, is_online = _get_templates()
    if not is_online:
        print(
            "Warning: registry unreachable — checking built-ins only.",
            file=sys.stderr,
        )

    # Check installed locals too
    installed_map = {t["name"]: t for t in _get_installed()}

    match = next((t for t in templates if t["name"] == name), None)
    if match is None:
        match = installed_map.get(name)
    if match is None:
        print(f"Template '{name}' not found.")
        return 1

    print(f"\nTemplate: {match['name']}")
    print(f"  Description : {match.get('description', '')}")
    print(f"  Author      : {match.get('author', '')}")
    print(f"  Version     : {match.get('version', '')}")
    print(f"  Tags        : {', '.join(match.get('tags', []))}")
    built_in_label = "yes (built-in)" if match.get("built_in") else "no"
    print(f"  Built-in    : {built_in_label}")

    local_dir = REPO_ROOT / "templates" / name
    print(f"  Installed   : {'yes — ' + str(local_dir) if local_dir.is_dir() else 'no'}")

    if match.get("built_in"):
        print(f"\n  Use with: make render TEMPLATE={name}")
    else:
        if local_dir.is_dir():
            print(f"\n  Installed at: {local_dir}")
        else:
            print(f"\n  Install with: make market-install NAME={name}")
    print()
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    name = args.name

    # Built-in: no action needed
    if name in BUILT_IN_NAMES:
        print(f"'{name}' is already built-in. Use: make render TEMPLATE={name}")
        return 0

    dest = REPO_ROOT / "templates" / name

    # Check if already installed
    if dest.is_dir():
        print(f"Template '{name}' is already installed at {dest}.")
        return 0

    # Fetch template from registry to verify it exists
    templates, is_online = _get_templates()
    if not is_online:
        print(
            "Error: registry unreachable. Cannot install external templates offline.",
            file=sys.stderr,
        )
        return 1

    registry_entry = next((t for t in templates if t["name"] == name), None)
    if registry_entry is None:
        print(f"Template '{name}' not found in registry.")
        return 1

    # Attempt to download .cls and optional template.yml
    dest.mkdir(parents=True, exist_ok=True)
    files_to_try = [f"{name}.cls", "template.yml"]
    downloaded: list[str] = []

    for fname in files_to_try:
        url = f"{TEMPLATES_BASE_URL}/{name}/{fname}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                content = resp.read()
            out_path = dest / fname
            out_path.write_bytes(content)
            downloaded.append(fname)
            print(f"  Downloaded: {fname}")
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            if fname.endswith(".cls"):
                # .cls is required — clean up and abort
                shutil.rmtree(dest, ignore_errors=True)
                print(
                    f"Error: could not download '{fname}' from registry ({exc}).",
                    file=sys.stderr,
                )
                return 1
            # template.yml is optional — skip silently

    if not downloaded:
        shutil.rmtree(dest, ignore_errors=True)
        print(f"Error: no files downloaded for template '{name}'.", file=sys.stderr)
        return 1

    print(f"\nInstalled '{name}' to {dest}")
    print(f"Use with: make render TEMPLATE={name}")
    return 0


def cmd_installed(args: argparse.Namespace) -> int:
    local = _get_installed()
    local_names = {t["name"] for t in local}

    # Merge: built-ins always shown, then additional installed
    all_entries: list[dict] = list(BUILT_INS)
    for t in local:
        if t["name"] not in BUILT_IN_NAMES:
            all_entries.append(t)

    if args.json:
        print(json.dumps({"installed": all_entries}, indent=2))
        return 0

    print(f"\nInstalled templates ({len(all_entries)}):\n")
    for t in all_entries:
        _print_template_row(t, show_status=True)

    extra = [n for n in local_names if n not in BUILT_IN_NAMES]
    if not extra:
        print("(no community templates installed — use 'make market-install NAME=...')")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="template-market.py",
        description="Browse and install LaTeX CV templates from the marketplace.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # list
    p_list = sub.add_parser("list", help="List all available templates")
    p_list.add_argument("--tag", metavar="TAG", help="Filter by tag")
    p_list.add_argument("--json", action="store_true", help="JSON output")

    # search
    p_search = sub.add_parser("search", help="Search templates by name/tag/description")
    p_search.add_argument("query", metavar="QUERY")
    p_search.add_argument("--json", action="store_true", help="JSON output")

    # info
    p_info = sub.add_parser("info", help="Show details for a template")
    p_info.add_argument("name", metavar="NAME")

    # install
    p_install = sub.add_parser("install", help="Install a template locally")
    p_install.add_argument("name", metavar="NAME")

    # installed
    p_installed = sub.add_parser("installed", help="List locally installed templates")
    p_installed.add_argument("--json", action="store_true", help="JSON output")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "search": cmd_search,
        "info": cmd_info,
        "install": cmd_install,
        "installed": cmd_installed,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
