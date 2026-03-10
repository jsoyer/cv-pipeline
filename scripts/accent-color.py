#!/usr/bin/env python3
"""
Auto-detect company accent color from their website for theme matching.

Detection heuristics (in order):
  1. HTML <meta name="theme-color"> tag
  2. CSS custom properties (--color-primary, --brand-color, --primary-color, etc.)
  3. Open Graph image dominant color (requires Pillow)
  4. Favicon dominant color (requires Pillow)
  5. Preset palette picker (fallback)

Updates:
  - data/themes/<company-slug>.yml  — new/updated theme file
  - applications/NAME/meta.yml      — adds accent_color field

Usage:
    scripts/accent-color.py <app-dir>
    make accent NAME=2026-02-acme
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from lib.common import REPO_ROOT, USER_AGENT, load_meta

HEADERS = {"User-Agent": USER_AGENT}

# Preset palette for fallback — covers most company types
PRESETS = {
    "1": ("Tech Blue (default)", "1A5276"),
    "2": ("Startup Orange", "E67E22"),
    "3": ("Executive Dark", "2C3E50"),
    "4": ("Cyber Red", "C0392B"),
    "5": ("Growth Green", "27AE60"),
    "6": ("Enterprise Slate", "2980B9"),
    "7": ("Fintech Navy", "154360"),
    "8": ("Healthcare Teal", "148F77"),
    "9": ("Creative Purple", "7D3C98"),
    "0": ("Minimal Black", "1C2833"),
}


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------


def _normalize_hex(val: str) -> str | None:
    """Normalize any CSS color to 6-char hex, or None if unparseable."""
    val = val.strip().lstrip("#")
    # 3-char shorthand → 6-char
    if len(val) == 3 and all(c in "0123456789abcdefABCDEF" for c in val):
        val = "".join(c * 2 for c in val)
    if len(val) == 6 and all(c in "0123456789abcdefABCDEF" for c in val):
        return val.upper()
    # rgb(r, g, b)
    m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", val, re.IGNORECASE)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{r:02X}{g:02X}{b:02X}"
    return None


def _is_useful_color(hex_color: str) -> bool:
    """Reject near-white, near-black, and pure grays."""
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    saturation = max(r, g, b) - min(r, g, b)
    return 30 < brightness < 230 and saturation > 30


def _ansi_swatch(hex_color: str) -> str:
    """Return ANSI escape sequence for a colored block."""
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"\x1b[48;2;{r};{g};{b}m   \x1b[0m"


# ---------------------------------------------------------------------------
# Detection strategies
# ---------------------------------------------------------------------------


def _get_domain(app_dir: Path, company: str) -> str:
    """Derive company domain from job.url or company name."""
    url_file = app_dir / "job.url"
    if url_file.exists():
        raw = url_file.read_text(encoding="utf-8").strip()
        parsed = urllib.parse.urlparse(raw)
        netloc = parsed.netloc.lower().lstrip("www.")
        for board in (
            "linkedin.com",
            "indeed.com",
            "greenhouse.io",
            "lever.co",
            "ashbyhq.com",
            "glassdoor.com",
            "wellfound.com",
        ):
            if board in netloc:
                break
        else:
            if "." in netloc:
                return netloc.split("/")[0]
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    return f"{slug}.com"


def _fetch(url: str, timeout: int = 10) -> str | None:
    if HAS_REQUESTS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    else:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            pass
    return None


def _detect_meta_theme_color(html: str) -> str | None:
    """Extract <meta name="theme-color" content="#HEX">."""
    m = re.search(r'<meta[^>]+name=["\']theme-color["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']theme-color["\']', html, re.IGNORECASE)
    if m:
        return _normalize_hex(m.group(1))
    return None


_CSS_PROPS = [
    "--color-primary",
    "--primary-color",
    "--brand-color",
    "--color-brand",
    "--accent-color",
    "--color-accent",
    "--main-color",
    "--primary",
    "--color-cta",
    "--highlight-color",
    "--theme-color",
]


def _detect_css_variable(html: str) -> str | None:
    """Search for common CSS custom property color declarations."""
    # Inline styles and <style> blocks
    css_blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL | re.IGNORECASE)
    css_text = " ".join(css_blocks) + " " + html

    for prop in _CSS_PROPS:
        # Match: --prop: #hex  or  --prop: rgb(...)
        pattern = re.escape(prop) + r"\s*:\s*(#[0-9a-fA-F]{3,8}|rgb\([^)]+\))"
        m = re.search(pattern, css_text, re.IGNORECASE)
        if m:
            color = _normalize_hex(m.group(1))
            if color and _is_useful_color(color):
                return color
    return None


def _detect_og_color(html: str) -> str | None:
    """Try to extract a dominant color from the OG image URL via Pillow."""
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if not m:
        return None
    img_url = m.group(1)
    return _pillow_dominant_color(img_url)


def _detect_favicon_color(domain: str) -> str | None:
    """Try to extract dominant color from favicon via Pillow."""
    for url in (f"https://{domain}/favicon.ico", f"https://www.{domain}/favicon.ico"):
        color = _pillow_dominant_color(url)
        if color:
            return color
    return None


def _pillow_dominant_color(url: str) -> str | None:
    """Download an image and return its dominant non-background color (requires Pillow)."""
    try:
        from PIL import Image
        import io
    except ImportError:
        return None

    if HAS_REQUESTS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                return None
            data = r.content
        except Exception:
            return None
    else:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
        except Exception:
            return None

    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = img.resize((32, 32))
        pixels = list(img.getdata())
        # Count colors, skip near-white and near-black
        from collections import Counter

        counts = Counter()
        for r, g, b in pixels:
            hex_c = f"{r:02X}{g:02X}{b:02X}"
            if _is_useful_color(hex_c):
                # Quantize to reduce noise
                rq, gq, bq = (r // 32) * 32, (g // 32) * 32, (b // 32) * 32
                counts[f"{rq:02X}{gq:02X}{bq:02X}"] += 1
        if counts:
            return counts.most_common(1)[0][0]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Detection pipeline
# ---------------------------------------------------------------------------


def detect_color(app_dir: Path, company: str) -> tuple[str | None, str]:
    """Run all detection heuristics. Returns (hex_color, source_name)."""
    domain = _get_domain(app_dir, company)
    print(f"🌐 Fetching {domain}...")

    html = _fetch(f"https://{domain}") or _fetch(f"https://www.{domain}")
    if not html:
        print("   ⚠️  Could not fetch website")
        return None, ""

    # 1. meta theme-color (most reliable)
    color = _detect_meta_theme_color(html)
    if color and _is_useful_color(color):
        return color, "meta[theme-color]"

    # 2. CSS variables
    color = _detect_css_variable(html)
    if color:
        return color, "CSS custom property"

    # 3. OG image (requires Pillow)
    color = _detect_og_color(html)
    if color and _is_useful_color(color):
        return color, "OG image (Pillow)"

    # 4. Favicon (requires Pillow)
    color = _detect_favicon_color(domain)
    if color and _is_useful_color(color):
        return color, "favicon (Pillow)"

    return None, ""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-detect company accent color for theme matching")
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument("--no-write", action="store_true", help="Detect only, do not write theme file")
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {app_dir}")
        return 1

    meta = load_meta(app_dir)
    company = meta.get("company", app_dir.name)
    slug = re.sub(r"[^a-z0-9-]", "-", company.lower()).strip("-")

    print(f"🎨 Detecting accent color for {company}...\n")
    color, source = detect_color(app_dir, company)

    if color:
        swatch = _ansi_swatch(color)
        print(f"   Found: {swatch}  #{color}  (via {source})")
    else:
        print("   ⚠️  Auto-detection failed. Choose from presets:\n")
        for k, (name, hex_c) in PRESETS.items():
            swatch = _ansi_swatch(hex_c)
            print(f"   [{k}] {swatch}  #{hex_c}  {name}")
        choice = input("\n   Enter number (or custom hex like 1A5276): ").strip()
        if choice in PRESETS:
            color = PRESETS[choice][1]
            source = "preset"
        else:
            color = _normalize_hex(choice)
            if not color:
                print("❌ Invalid hex color")
                return 1
            source = "manual"

    print(f"\n✅ Accent color: #{color}  (source: {source})")

    if args.no_write:
        print("   --no-write: skipping file writes")
        return 0

    # Write theme file
    theme_dir = REPO_ROOT / "data" / "themes"
    theme_dir.mkdir(parents=True, exist_ok=True)
    theme_path = theme_dir / f"{slug}.yml"
    theme_content = f'# {company} brand theme — auto-detected\ncolor: "{color}"\nfont_size: "10pt"\n'
    theme_path.write_text(theme_content, encoding="utf-8")
    print(f"   ✅ Theme file: {theme_path}")

    # Update meta.yml
    meta_path = app_dir / "meta.yml"
    if meta_path.exists():
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta_data = yaml.safe_load(f) or {}
            meta_data["accent_color"] = color
            meta_data["theme"] = str(theme_path.relative_to(REPO_ROOT))
            with open(meta_path, "w", encoding="utf-8") as f:
                yaml.dump(meta_data, f, allow_unicode=True, sort_keys=False)
            print(f"   ✅ meta.yml updated: accent_color={color}")
        except Exception as e:
            print(f"   ⚠️  Could not update meta.yml: {e}")

    print(f"\n💡 Use this theme: make render NAME={app_dir.name} (theme auto-applied via meta.yml)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
