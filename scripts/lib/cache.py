"""Disk-based AI response cache with TTL.

Cache entries are stored as JSON files in CV_CACHE_DIR
(default: ~/.cache/cv-ai/).  Keys are SHA-256 hashes of
(provider, model, prompt).

Usage::

    from lib.cache import cache_get, cache_set, DEFAULT_TTL

    hit = cache_get(prompt, "gemini")
    if hit is None:
        result = call_ai(prompt, "gemini", api_key)
        cache_set(prompt, "gemini", result)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

__all__ = [
    "make_key",
    "cache_get",
    "cache_set",
    "cache_clear",
    "cache_stats",
    "DEFAULT_TTL",
    "CACHE_DIR",
]

CACHE_DIR: Path = Path(os.environ.get("CV_CACHE_DIR", str(Path.home() / ".cache" / "cv-ai")))
DEFAULT_TTL: int = 3600 * 24 * 7  # 7 days


def make_key(prompt: str, provider: str, model: str | None = None) -> str:
    """Return a 32-char hex cache key for (provider, model, prompt)."""
    data = f"{provider}:{model or ''}:{prompt}"
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:32]


def cache_get(
    prompt: str,
    provider: str,
    model: str | None = None,
    ttl: int = DEFAULT_TTL,
) -> str | None:
    """Return cached response or None (if miss or expired)."""
    path = CACHE_DIR / f"{make_key(prompt, provider, model)}.json"
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - entry["ts"] > ttl:
            path.unlink(missing_ok=True)
            return None
        return entry["response"]
    except Exception:
        return None


def cache_set(
    prompt: str,
    provider: str,
    response: str,
    model: str | None = None,
) -> None:
    """Write a response to the disk cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{make_key(prompt, provider, model)}.json"
    entry = {
        "ts": time.time(),
        "provider": provider,
        "model": model,
        "prompt_prefix": prompt[:120],
        "response": response,
    }
    path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")


def cache_clear(max_age: int = DEFAULT_TTL) -> int:
    """Delete cache entries older than max_age seconds. Returns count deleted."""
    if not CACHE_DIR.exists():
        return 0
    deleted = 0
    now = time.time()
    for p in CACHE_DIR.glob("*.json"):
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
            if now - entry["ts"] > max_age:
                p.unlink()
                deleted += 1
        except Exception:
            try:
                p.unlink()
            except Exception:
                pass
            deleted += 1
    return deleted


def cache_stats() -> dict:
    """Return a summary dict: entries, size_bytes, dir."""
    if not CACHE_DIR.exists():
        return {"entries": 0, "size_bytes": 0, "dir": str(CACHE_DIR)}
    files = list(CACHE_DIR.glob("*.json"))
    size = sum(p.stat().st_size for p in files)
    # Oldest entry age in hours
    ages = []
    for p in files:
        try:
            ts = json.loads(p.read_text(encoding="utf-8"))["ts"]
            ages.append(time.time() - ts)
        except Exception:
            pass
    return {
        "entries": len(files),
        "size_bytes": size,
        "dir": str(CACHE_DIR),
        "oldest_hours": round(max(ages) / 3600, 1) if ages else 0,
        "newest_hours": round(min(ages) / 3600, 1) if ages else 0,
    }
