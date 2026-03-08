#!/usr/bin/env python3
"""
Manage named CV versions — full YAML snapshots for different role targets.

Versions are stored as complete cv.yml files in data/versions/.
Useful when targeting different role levels/tracks before AI tailoring.

Actions:
    list              List all saved versions + which is active
    save VERSION      Snapshot current data/cv.yml as a named version
    activate VERSION  Copy saved version to data/cv.yml (with backup)
    diff VERSION      Diff current cv.yml vs a saved version
    show VERSION      Print version file path and description

Usage:
    scripts/cv-versions.py list
    scripts/cv-versions.py save vp-se
    scripts/cv-versions.py activate director-sales
    scripts/cv-versions.py diff vp-se
    scripts/cv-versions.py show vp-se
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

from lib.common import REPO_ROOT

_VERSIONS_DIR = REPO_ROOT / "data" / "versions"
_CV_PATH = REPO_ROOT / "data" / "cv.yml"


def _ensure_versions_dir() -> None:
    _VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    gitkeep = _VERSIONS_DIR / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()


def _list_versions() -> list:
    if not _VERSIONS_DIR.exists():
        return []
    return sorted(
        p for p in _VERSIONS_DIR.glob("*.yml")
        if not p.name.startswith(".")
    )


def _current_position() -> str:
    """Read position field from current data/cv.yml."""
    if not _CV_PATH.exists():
        return "?"
    with open(_CV_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("personal", {}).get("position", "?")


def _version_position(path: Path) -> str:
    """Read position field from a version file."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("personal", {}).get("position", "?")
    except Exception:
        return "?"


def _active_version() -> str | None:
    """
    Try to detect which saved version matches the current cv.yml
    by comparing position + skills.
    """
    if not _CV_PATH.exists():
        return None
    current = _CV_PATH.read_text(encoding="utf-8")
    for vpath in _list_versions():
        if vpath.read_text(encoding="utf-8") == current:
            return vpath.stem
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(_args) -> int:
    versions = _list_versions()
    active   = _active_version()
    cur_pos  = _current_position()

    print(f"\n📂 CV Versions  ({_VERSIONS_DIR})\n")
    print(f"   {'★  Current':>5}  data/cv.yml  →  {cur_pos}\n")

    if not versions:
        print("   No saved versions yet.")
        print(f"   Save one: make cv-versions ACTION=save VERSION=my-version")
        return 0

    print(f"   {'Active':>5}  {'Name':<25}  Position")
    print("   " + "─" * 55)
    for v in versions:
        marker  = "✅ " if v.stem == active else "   "
        pos     = _version_position(v)
        size_kb = v.stat().st_size // 1024 or 1
        print(f"   {marker}  {v.stem:<25}  {pos}")
    print()
    return 0


def cmd_save(args) -> int:
    if not args.version:
        print("❌ VERSION required: make cv-versions ACTION=save VERSION=my-name")
        return 1
    if not _CV_PATH.exists():
        print(f"❌ {_CV_PATH} not found")
        return 1

    _ensure_versions_dir()
    dest = _VERSIONS_DIR / f"{args.version}.yml"
    existed = dest.exists()

    shutil.copy2(_CV_PATH, dest)
    pos = _current_position()
    verb = "Updated" if existed else "Saved"
    print(f"✅ {verb}: data/versions/{args.version}.yml  ({pos})")
    return 0


def cmd_activate(args) -> int:
    if not args.version:
        print("❌ VERSION required: make cv-versions ACTION=activate VERSION=my-name")
        return 1

    src = _VERSIONS_DIR / f"{args.version}.yml"
    if not src.exists():
        print(f"❌ Version not found: {src}")
        versions = _list_versions()
        if versions:
            print("   Available: " + ", ".join(v.stem for v in versions))
        return 1

    # Backup current cv.yml
    if _CV_PATH.exists():
        ts     = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = REPO_ROOT / "data" / f"cv.backup-{ts}.yml"
        shutil.copy2(_CV_PATH, backup)
        print(f"🔒 Backup: {backup.name}")

    shutil.copy2(src, _CV_PATH)
    pos = _version_position(src)
    print(f"✅ Activated: {args.version}  ({pos})")
    print(f"   data/cv.yml updated — run: make render")
    return 0


def cmd_diff(args) -> int:
    if not args.version:
        print("❌ VERSION required")
        return 1

    src = _VERSIONS_DIR / f"{args.version}.yml"
    if not src.exists():
        print(f"❌ Version not found: {src}")
        return 1
    if not _CV_PATH.exists():
        print(f"❌ {_CV_PATH} not found")
        return 1

    print(f"📊 Diff: current cv.yml  ←→  {args.version}\n")
    result = subprocess.run(
        ["diff", "--color=always", "-u", str(src), str(_CV_PATH)],
        cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        print("✅ No differences — files are identical")
    return 0


def cmd_show(args) -> int:
    if not args.version:
        print("❌ VERSION required")
        return 1

    src = _VERSIONS_DIR / f"{args.version}.yml"
    if not src.exists():
        print(f"❌ Version not found: {src}")
        return 1

    pos  = _version_position(src)
    size = src.stat().st_size
    mtime = datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    print(f"\n📄 Version: {args.version}")
    print(f"   File:     {src}")
    print(f"   Position: {pos}")
    print(f"   Size:     {size} bytes")
    print(f"   Modified: {mtime}")
    print()
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMANDS = {
    "list":     cmd_list,
    "save":     cmd_save,
    "activate": cmd_activate,
    "diff":     cmd_diff,
    "show":     cmd_show,
}


def main():
    parser = argparse.ArgumentParser(
        description="Manage named CV versions"
    )
    parser.add_argument(
        "action", nargs="?", default="list",
        choices=list(COMMANDS),
        help=f"Action: {' | '.join(COMMANDS)}"
    )
    parser.add_argument(
        "version", nargs="?", default=None,
        help="Version name (e.g. vp-se, director-sales)"
    )
    args = parser.parse_args()

    return COMMANDS[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
