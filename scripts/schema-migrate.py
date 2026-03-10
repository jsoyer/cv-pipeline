"""schema-migrate.py — Add missing fields to meta.yml files and cv.yml.

Usage:
    scripts/schema-migrate.py [--target apps|cv|all] [--dry-run] [--verbose]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# Allow running from anywhere in the repo
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import REPO_ROOT  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TODAY_YYYYMM: str = date.today().strftime("%Y-%m")

# Fields to add to meta.yml when absent.
# Value is (default, sentinel) where sentinel=True means "skip if missing AND
# not listed here" — i.e. truly optional fields that we never inject.
# Fields whose default is _SKIP are left out entirely when absent.
_SKIP = object()

META_FIELDS: list[tuple[str, Any]] = [
    ("position", ""),
    ("created", TODAY_YYYYMM),
    ("outcome", "applied"),
    ("tailor_provider", ""),
    # deadline and response_days: optional — only add if key is totally absent
    # and the user has not set them; we keep them null rather than omitting.
    # Per spec: skip adding if missing.
]

# Optional sections that cv.yml must have (as empty lists when absent).
CV_OPTIONAL_SECTIONS: list[str] = ["projects", "volunteer"]


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, raising SystemExit on parse error."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        print(f"ERROR: Failed to parse {path}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if not isinstance(data, dict):
        print(f"ERROR: {path} does not contain a YAML mapping.", file=sys.stderr)
        raise SystemExit(1)
    return data


def _dump_yaml(data: dict[str, Any]) -> str:
    """Dump data to a YAML string."""
    return yaml.dump(data, allow_unicode=True, sort_keys=False)


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically via a temp file in the same directory."""
    dir_ = path.parent
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".schema-migrate-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# meta.yml migration
# ---------------------------------------------------------------------------


def migrate_meta(
    meta_path: Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> list[str]:
    """Migrate a single meta.yml. Returns list of field names added."""
    data = _load_yaml(meta_path)

    # Skip entirely if 'company' is missing — we have no safe default.
    if "company" not in data:
        if verbose:
            print(f"  SKIP {meta_path} — 'company' field missing, cannot migrate.")
        return []

    added: list[str] = []
    for field, default in META_FIELDS:
        if field not in data:
            data[field] = default
            added.append(field)
            if verbose:
                print(f"    + {field}: {default!r}")

    if not added:
        return []

    if not dry_run:
        _atomic_write(meta_path, _dump_yaml(data))

    return added


def migrate_all_apps(
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Migrate all applications/*/meta.yml files. Returns count of files changed."""
    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.is_dir():
        print(f"No applications/ directory found at {apps_dir}")
        return 0

    meta_files = sorted(apps_dir.glob("*/meta.yml"))
    if not meta_files:
        print("No meta.yml files found in applications/.")
        return 0

    changed = 0
    for meta_path in meta_files:
        app_name = meta_path.parent.name
        added = migrate_meta(meta_path, dry_run=dry_run, verbose=verbose)
        if added:
            changed += 1
            tag = "[dry-run] " if dry_run else ""
            print(f"  {tag}{app_name}: added {', '.join(added)}")

    return changed


# ---------------------------------------------------------------------------
# cv.yml migration
# ---------------------------------------------------------------------------


def migrate_cv(
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> list[str]:
    """Ensure optional sections exist in data/cv.yml. Returns list of keys added."""
    cv_path = REPO_ROOT / "data" / "cv.yml"
    if not cv_path.exists():
        print(f"ERROR: {cv_path} not found.", file=sys.stderr)
        raise SystemExit(1)

    data = _load_yaml(cv_path)
    added: list[str] = []

    for section in CV_OPTIONAL_SECTIONS:
        if section not in data:
            data[section] = []
            added.append(section)
            if verbose:
                print(f"    + {section}: []")

    if added and not dry_run:
        _atomic_write(cv_path, _dump_yaml(data))

    return added


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add missing fields to meta.yml files and cv.yml.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target",
        choices=["apps", "cv", "all"],
        default="all",
        help="What to migrate: apps, cv, or all (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing any files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-field details.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dry_run: bool = args.dry_run
    verbose: bool = args.verbose
    target: str = args.target

    if dry_run:
        print("Dry-run mode — no files will be written.\n")

    total_changed = 0

    # --- apps ---
    if target in ("apps", "all"):
        print("Migrating applications/*/meta.yml ...")
        n = migrate_all_apps(dry_run=dry_run, verbose=verbose)
        total_changed += n
        if n == 0:
            print("  Nothing to migrate in applications/.")
        else:
            tag = "Would update" if dry_run else "Updated"
            print(f"  {tag} {n} meta.yml file(s).")

    # --- cv.yml ---
    if target in ("cv", "all"):
        print("Migrating data/cv.yml ...")
        added = migrate_cv(dry_run=dry_run, verbose=verbose)
        if added:
            total_changed += 1
            tag = "[dry-run] " if dry_run else ""
            print(f"  {tag}data/cv.yml: added {', '.join(added)}")
        else:
            print("  Nothing to migrate in data/cv.yml.")

    # --- summary ---
    print()
    if total_changed == 0:
        print("Nothing to migrate.")
    else:
        verb = "Would update" if dry_run else "Updated"
        print(f"{verb} {total_changed} file(s).")


if __name__ == "__main__":
    main()
