"""Normalize YAML file formatting with consistent style and canonical key ordering.

Usage:
    scripts/yaml-beautify.py data/cv.yml
    scripts/yaml-beautify.py --dry-run data/cv.yml
    scripts/yaml-beautify.py --check data/cv.yml
    make beautify
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import REPO_ROOT, setup_logging  # noqa: E402

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml")
    raise SystemExit(1)

CV_KEY_ORDER: list[str] = [
    "personal",
    "profile",
    "skills",
    "key_wins",
    "experience",
    "early_career",
    "education",
    "certifications",
    "awards",
    "publications",
    "languages",
    "interests",
]

META_KEY_ORDER: list[str] = [
    "company",
    "position",
    "created",
    "deadline",
    "outcome",
    "response_days",
    "tailor_provider",
    "ats_history",
    "followup_issue",
]

DUMP_KWARGS: dict[str, Any] = {
    "allow_unicode": True,
    "sort_keys": False,
    "default_flow_style": False,
    "width": 120,
    "indent": 2,
}


def detect_ordering(data: dict[str, Any]) -> list[str] | None:
    """Return the canonical key order for the given data dict, or None."""
    if "personal" in data:
        return CV_KEY_ORDER
    if "company" in data and "outcome" in data:
        return META_KEY_ORDER
    return None


def reorder(data: dict[str, Any], order: list[str]) -> dict[str, Any]:
    """Return a new dict with keys sorted by canonical order, extras appended."""
    ordered = {k: data[k] for k in order if k in data}
    extras = {k: v for k, v in data.items() if k not in ordered}
    return {**ordered, **extras}


def beautify(data: dict[str, Any]) -> str:
    """Serialize data to a canonical YAML string."""
    order = detect_ordering(data)
    if order is not None:
        data = reorder(data, order)
    return yaml.dump(data, **DUMP_KWARGS)


def process_file(
    path: Path,
    *,
    dry_run: bool,
    check: bool,
    verbose: bool,
) -> bool:
    """Process a single YAML file. Returns True if file was (or would be) changed."""
    log = setup_logging(verbose)

    original = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(original)
    except yaml.YAMLError as exc:
        log.error("%s: YAML parse error: %s", path, exc)
        return False

    if not isinstance(data, dict):
        log.warning("%s: top-level is not a mapping — skipping", path)
        return False

    reformatted = beautify(data)

    if reformatted == original:
        log.debug("%s: already canonical", path)
        return False

    if dry_run or check:
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            reformatted.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        sys.stdout.writelines(diff)
        if check:
            log.info("%s: would be reformatted", path)
        return True

    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(reformatted)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise

    log.info("%s: reformatted", path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize YAML formatting with consistent style.",
    )
    parser.add_argument("files", nargs="+", metavar="FILE", help="YAML files to process")
    parser.add_argument("--dry-run", action="store_true", help="Print diff, do not write")
    parser.add_argument("--check", action="store_true", help="Exit 1 if any file would change")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    changed = False
    for pattern in args.files:
        paths = sorted(Path(REPO_ROOT).glob(pattern)) if "*" in pattern else [Path(pattern)]
        for path in paths:
            if not path.exists():
                print(f"yaml-beautify: {path}: file not found", file=sys.stderr)
                continue
            changed |= process_file(
                path,
                dry_run=args.dry_run,
                check=args.check,
                verbose=args.verbose,
            )

    if args.check and changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
