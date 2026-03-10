"""Shared utilities for CV pipeline scripts."""

from __future__ import annotations

import glob
import logging
import os
import shutil
from pathlib import Path
from types import ModuleType
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

__all__ = [
    "find_xelatex",
    "load_env",
    "load_meta",
    "require_yaml",
    "company_from_dirname",
    "setup_logging",
    "REPO_ROOT",
    "SCRIPTS_DIR",
    "USER_AGENT",
    "STOP_WORDS",
]

REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR: Path = REPO_ROOT / "scripts"


def find_xelatex() -> str:
    """Auto-detect the xelatex binary across platforms.

    Resolution order:
    1. ``XELATEX`` environment variable (explicit override)
    2. ``xelatex`` found anywhere in ``$PATH`` (most installs)
    3. ``/Library/TeX/texbin/xelatex`` — BasicTeX / MacTeX symlink on macOS
    4. Any TeX Live year under ``/usr/local/texlive/`` (vanilla TeX Live)
    5. Fedora/RPM paths under ``/usr/share/texlive/``
    6. Fallback to the bare name so the shell surfaces a clear error.
    """
    if env := os.environ.get("XELATEX"):
        return env

    if found := shutil.which("xelatex"):
        return found

    candidates = [
        "/Library/TeX/texbin/xelatex",  # BasicTeX / MacTeX (macOS)
        *sorted(glob.glob("/usr/local/texlive/*/bin/universal-darwin/xelatex")),
        *sorted(glob.glob("/usr/local/texlive/*/bin/x86_64-darwin/xelatex")),
        *sorted(glob.glob("/usr/local/texlive/*/bin/aarch64-linux/xelatex")),
        *sorted(glob.glob("/usr/local/texlive/*/bin/x86_64-linux/xelatex")),
        # Fedora / RPM-based: texlive-xetex installs here
        *sorted(glob.glob("/usr/share/texlive/*/bin/x86_64-linux/xelatex")),
        *sorted(glob.glob("/usr/share/texlive/*/bin/aarch64-linux/xelatex")),
        "/opt/homebrew/bin/xelatex",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    return "xelatex"

# Default timeouts (seconds)
TIMEOUT_HTTP: int = 15
TIMEOUT_SUBPROCESS: int = 30
TIMEOUT_SUBPROCESS_LONG: int = 300
TIMEOUT_GIT: int = 10

USER_AGENT: str = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure structured logging for CV pipeline scripts.

    Returns a logger named after the calling script.

    Args:
        verbose: When True, enables DEBUG level with timestamped format.
            When False (default), uses INFO level with a concise format.

    Returns:
        A Logger instance named after the calling module stem.
    """
    import inspect

    caller = Path(inspect.stack()[1].filename).stem
    logger = logging.getLogger(caller)
    if not logger.handlers:
        handler = logging.StreamHandler()
        # LOG_LEVEL env var overrides verbose flag
        env_level = os.environ.get("LOG_LEVEL", "").upper()
        if env_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            level = getattr(logging, env_level)
            verbose = level == logging.DEBUG
        else:
            level = logging.DEBUG if verbose else logging.INFO
        if verbose:
            fmt = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"
        else:
            fmt = "%(levelname)-5s %(message)s"
        handler.setLevel(level)
        logger.setLevel(level)
        handler.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
        logger.addHandler(handler)
    return logger


def require_yaml() -> ModuleType:
    """Return the yaml module or exit with a helpful message."""
    if yaml is None:
        print("PyYAML required: pip install pyyaml")
        raise SystemExit(1)
    return yaml


def load_env() -> None:
    """Load .env file from the repo root into os.environ (setdefault only)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def load_meta(app_dir: str | Path) -> dict[str, Any]:
    """Load meta.yml from an application directory. Returns dict or {}."""
    require_yaml()
    meta_path = Path(app_dir) / "meta.yml"
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def company_from_dirname(name: str) -> str:
    """Extract a company display name from an application dir name (YYYY-MM-slug)."""
    parts = name.split("-", 2)
    return parts[2].replace("-", " ").title() if len(parts) > 2 else name


STOP_WORDS: frozenset[str] = frozenset({
    "a", "ab", "able", "about", "above", "across", "after", "again", "all",
    "also", "am", "an", "and", "any", "are", "as", "at", "back", "be",
    "because", "been", "before", "being", "between", "both", "but", "by",
    "can", "come", "could", "day", "de", "did", "do", "does", "each",
    "even", "every", "few", "first", "for", "from", "further", "get",
    "great", "had", "has", "have", "he", "help", "her", "here", "high",
    "him", "his", "how", "i", "if", "in", "including", "into", "is", "it",
    "its", "just", "know", "la", "last", "le", "les", "like", "long",
    "look", "make", "many", "may", "me", "might", "more", "most", "much",
    "must", "my", "need", "new", "no", "nor", "not", "now", "of", "on",
    "one", "only", "or", "other", "our", "out", "over", "own", "part",
    "plus", "re", "role", "same", "she", "should", "so", "some", "such",
    "take", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "through", "time", "to", "too",
    "two", "under", "up", "upon", "us", "use", "used", "using", "very",
    "want", "was", "way", "we", "well", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "work",
    "working", "would", "year", "years", "you", "your",
    # Job posting filler
    "ability", "apply", "bonus", "candidate", "company", "description",
    "equal", "employer", "experience", "job", "looking", "opportunity",
    "position", "preferred", "qualifications", "required", "requirements",
    "responsibilities", "team",
})
