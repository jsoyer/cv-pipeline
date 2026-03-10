#!/usr/bin/env python3
"""Doctor — Check all dependencies and environment for the CV system."""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from lib.common import REPO_ROOT, find_xelatex, load_env

# ---------------------------------------------------------------------------
# OS / distro detection (used for per-tool install hints)
# ---------------------------------------------------------------------------

def _detect_os() -> str:
    """Return a normalised OS tag: 'macos' | 'debian' | 'fedora' | 'arch' | 'windows' | 'unknown'."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Windows":
        return "windows"
    if system == "Linux":
        try:
            text = Path("/etc/os-release").read_text(encoding="utf-8").lower()
        except OSError:
            return "linux"
        if "ubuntu" in text or "debian" in text:
            return "debian"
        if "fedora" in text or "rhel" in text or "centos" in text or "rocky" in text:
            return "fedora"
        if "arch" in text or "manjaro" in text or "endeavour" in text:
            return "arch"
        return "linux"
    return "unknown"


OS_TAG = _detect_os()


# Install hint per (tool_name, os_tag) — shown inline next to ❌ findings
_INSTALL_HINTS: dict[str, dict[str, str]] = {
    "xelatex": {
        "macos":   "brew install --cask mactex-no-gui  (or: make install-deps)",
        "debian":  "sudo apt install texlive-xetex texlive-fonts-extra  (or: make install-deps)",
        "fedora":  "sudo dnf install texlive-xetex  (or: make install-deps)",
        "arch":    "sudo pacman -S texlive-xetex  (or: make install-deps)",
        "windows": "scoop install texlive  (or: make install-deps)",
    },
    "uv": {
        "macos":   "brew install uv",
        "debian":  "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "fedora":  "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "arch":    "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "windows": "scoop install uv",
    },
    "gh": {
        "macos":   "brew install gh",
        "debian":  "sudo apt install gh  (or see: https://cli.github.com)",
        "fedora":  "sudo dnf install gh",
        "arch":    "sudo pacman -S github-cli",
        "windows": "scoop install gh",
    },
    "python3": {
        "macos":   "brew install python",
        "debian":  "sudo apt install python3",
        "fedora":  "sudo dnf install python3",
        "arch":    "sudo pacman -S python",
        "windows": "scoop install python",
    },
    "pdfinfo": {
        "macos":   "brew install poppler",
        "debian":  "sudo apt install poppler-utils",
        "fedora":  "sudo dnf install poppler-utils",
        "arch":    "sudo pacman -S poppler",
        "windows": "scoop install poppler",
    },
    "convert": {
        "macos":   "brew install imagemagick",
        "debian":  "sudo apt install imagemagick",
        "fedora":  "sudo dnf install ImageMagick",
        "arch":    "sudo pacman -S imagemagick",
        "windows": "scoop install imagemagick",
    },
    "aspell": {
        "macos":   "brew install aspell",
        "debian":  "sudo apt install aspell aspell-en aspell-fr",
        "fedora":  "sudo dnf install aspell aspell-en",
        "arch":    "sudo pacman -S aspell aspell-en",
        "windows": "scoop install aspell",
    },
    "chktex": {
        "macos":   "brew install chktex",
        "debian":  "sudo apt install chktex",
        "fedora":  "sudo dnf install texlive-chktex",
        "arch":    "sudo pacman -S texlive-binextra",
        "windows": "tlmgr install chktex",
    },
    "pandoc": {
        "macos":   "brew install pandoc",
        "debian":  "sudo apt install pandoc",
        "fedora":  "sudo dnf install pandoc",
        "arch":    "sudo pacman -S pandoc",
        "windows": "scoop install pandoc",
    },
    "git": {
        "macos":   "brew install git",
        "debian":  "sudo apt install git",
        "fedora":  "sudo dnf install git",
        "arch":    "sudo pacman -S git",
        "windows": "scoop install git",
    },
}


def _install_hint(cmd: str) -> str:
    hints = _INSTALL_HINTS.get(cmd, {})
    return hints.get(OS_TAG, hints.get("debian", "see: make install-deps"))

# ---------------------------------------------------------------------------
# Tool checks
# ---------------------------------------------------------------------------

TOOL_CHECKS = [
    ("xelatex", "XeLaTeX (LaTeX engine)", find_xelatex()),
    ("python3", "Python 3", None),
    ("uv", "uv (Python package manager)", None),
    ("git", "Git", None),
    ("gh", "GitHub CLI", None),
    ("pdfinfo", "pdfinfo / poppler (PDF page count)", None),
    ("convert", "ImageMagick (visual diff)", None),
    ("aspell", "Aspell (spell checker)", None),
    ("chktex", "ChkTeX (LaTeX linter)", None),
    ("pandoc", "Pandoc (DOCX export)", None),
]

OPTIONAL_TOOLS = [
    ("tidy", "HTML tidy (dashboard)"),
    ("ollama", "Ollama (local AI)"),
    ("jq", "jq (JSON processing)"),
]

# TeX Live packages verified via kpsewhich
TEXLIVE_PACKAGES = [
    ("fontawesome6.sty",  "fontawesome6 (icons)"),
    ("tcolorbox.sty",     "tcolorbox (section boxes)"),
    ("fontspec.sty",      "fontspec (XeTeX font loading)"),
    ("unicode-math.sty",  "unicode-math (math fonts)"),
    ("enumitem.sty",      "enumitem (list formatting)"),
    ("ragged2e.sty",      "ragged2e (text alignment)"),
    ("geometry.sty",      "geometry (page layout)"),
    ("hyperref.sty",      "hyperref (PDF links)"),
]

# ---------------------------------------------------------------------------
# Python module checks
# ---------------------------------------------------------------------------

REQUIRED_MODULES = [
    ("yaml",       "PyYAML",          "pip install pyyaml"),
    ("requests",   "requests",        "pip install requests"),
    ("bs4",        "Beautiful Soup 4","pip install beautifulsoup4"),
    ("jsonschema", "jsonschema",      "pip install jsonschema"),
]

OPTIONAL_MODULES = [
    ("watchdog", "watchdog (watch mode)", "pip install watchdog"),
    ("textual", "Textual (TUI)", "pip install textual"),
    ("google.generativeai", "google-generativeai (Gemini)", "pip install google-generativeai"),
    ("anthropic", "anthropic SDK", "pip install anthropic"),
    ("openai", "openai SDK", "pip install openai"),
    ("mistralai", "mistralai SDK", "pip install mistralai"),
]

# ---------------------------------------------------------------------------
# API key checks
# ---------------------------------------------------------------------------

API_KEYS = [
    ("GEMINI_API_KEY", "Gemini API key", "https://aistudio.google.com/apikey"),
    ("ANTHROPIC_API_KEY", "Anthropic API key", "https://console.anthropic.com/"),
    ("OPENAI_API_KEY", "OpenAI API key", "https://platform.openai.com/api-keys"),
    ("MISTRAL_API_KEY", "Mistral API key", "https://console.mistral.ai/"),
    ("SLACK_WEBHOOK_URL", "Slack webhook URL", None),
    ("DISCORD_WEBHOOK_URL", "Discord webhook URL", None),
    ("NOTION_TOKEN", "Notion API token", None),
    ("GITHUB_TOKEN", "GitHub token (CI only)", None),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OK = "✅"
FAIL = "❌"
WARN = "⚠️ "
INFO = "ℹ️ "


def check_command(cmd, path=None):
    if path and os.path.exists(path):
        return True
    return shutil.which(cmd) is not None


def check_python_module(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def check_texlive_package(sty_file: str) -> bool:
    """Check if a TeX Live package is installed via kpsewhich."""
    result = subprocess.run(
        ["kpsewhich", sty_file],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def check_source_sans_font() -> tuple[bool, str]:
    """Return (found, variant) where variant is 'SourceSans3' or 'SourceSansPro'."""
    result = subprocess.run(["fc-list"], capture_output=True, text=True)
    output = result.stdout.lower()
    if "sourcesans3" in output or "source sans 3" in output:
        return True, "SourceSans3"
    if "sourcesanspro" in output or "source sans pro" in output:
        return True, "SourceSansPro"
    return False, ""


def check_submodule_fresh() -> tuple[str, str]:
    """
    Check if awesome-cv submodule is behind its remote.
    Returns (status, message):
      'ok'      — up to date
      'behind'  — remote has newer commits
      'uninit'  — not initialised
      'error'   — could not determine
    """
    awesome_cv_path = REPO_ROOT / "awesome-cv"
    if not (awesome_cv_path / "awesome-cv.cls").exists():
        return "uninit", "submodule not initialised"
    try:
        # Check git submodule status — '+' prefix means recorded commit != checked out
        result = subprocess.run(
            ["git", "submodule", "status", "awesome-cv"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        line = result.stdout.strip()
        if line.startswith("+"):
            return "behind", "recorded commit differs from checked-out — run: make submodule-update"
        if line.startswith("-"):
            return "uninit", "not initialised — run: git submodule update --init --recursive"
        return "ok", "up to date"
    except Exception as exc:
        return "error", str(exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _fix_submodule() -> bool:
    """Auto-fix: initialize missing awesome-cv submodule."""
    result = subprocess.run(
        ["git", "submodule", "update", "--init", "--recursive"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _fix_pip_modules(modules: list[tuple[str, str, str]]) -> list[str]:
    """Auto-fix: pip install missing required modules. Returns list of fixed module names."""
    fixed = []
    for module, name, install_cmd in modules:
        if not check_python_module(module):
            # Extract just the pip package name from the install command
            pkg = install_cmd.replace("pip install ", "").strip()
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "-q"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                fixed.append(name)
                print(f"  {OK} Installed: {name}")
            else:
                print(f"  {FAIL} Failed to install {name}: {result.stderr.strip()[:80]}")
    return fixed


def _fix_env_file() -> bool:
    """Auto-fix: copy .env.example → .env if missing."""
    env_path = REPO_ROOT / ".env"
    example_path = REPO_ROOT / ".env.example"
    if env_path.exists():
        return False  # nothing to fix
    if example_path.exists():
        import shutil as _shutil

        _shutil.copy(example_path, env_path)
        print(f"  {OK} Copied .env.example → .env (fill in your API keys)")
        return True
    else:
        # Create minimal .env template
        env_path.write_text(
            "# CV Pipeline environment — fill in your API keys\n"
            "GEMINI_API_KEY=\n"
            "ANTHROPIC_API_KEY=\n"
            "OPENAI_API_KEY=\n"
            "MISTRAL_API_KEY=\n"
            "SLACK_WEBHOOK_URL=\n"
            "NOTION_TOKEN=\n"
            "NOTION_DB_ID=\n",
            encoding="utf-8",
        )
        print(f"  {OK} Created .env template — fill in your API keys")
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CV System Doctor — check and fix dependencies")
    parser.add_argument("--fix", action="store_true", help="Auto-fix common issues (pip install, submodule init, .env)")
    args = parser.parse_args()

    fix_mode = args.fix
    if fix_mode:
        print("🔧 CV System Doctor — FIX MODE\n")
    else:
        print("🔍 CV System Doctor\n")

    all_ok = True
    missing_install = []

    # ── Required tools ────────────────────────────────────────────────────────
    print("🛠️  Required tools:")
    for cmd, name, path in TOOL_CHECKS:
        ok = check_command(cmd, path)
        if ok:
            print(f"  {OK} {name}")
        else:
            hint = _install_hint(cmd)
            print(f"  {FAIL} {name}  →  {hint}")
            all_ok = False
            missing_install.append(cmd)
    print()

    # ── Optional tools ────────────────────────────────────────────────────────
    print("🔧 Optional tools:")
    for cmd, label in OPTIONAL_TOOLS:
        ok = check_command(cmd)
        print(f"  {OK if ok else WARN} {label}")
    print()

    # ── Required Python modules ───────────────────────────────────────────────
    print("📦 Required Python modules:")
    missing_modules = [(m, n, c) for m, n, c in REQUIRED_MODULES if not check_python_module(m)]
    if fix_mode and missing_modules:
        print(f"  🔧 Installing {len(missing_modules)} missing module(s)...")
        _fix_pip_modules(missing_modules)
    for module, name, install_cmd in REQUIRED_MODULES:
        ok = check_python_module(module)
        print(f"  {OK if ok else FAIL} {name}")
        if not ok:
            all_ok = False
            missing_install.append(f"'{install_cmd}'")
    print()

    # ── Optional Python modules ───────────────────────────────────────────────
    print("📦 Optional Python modules:")
    for module, name, install_cmd in OPTIONAL_MODULES:
        ok = check_python_module(module)
        print(f"  {OK if ok else WARN} {name}")
    print()

    # ── .env file ─────────────────────────────────────────────────────────────
    print("🔑 Environment & API keys:")
    env_exists = load_env()
    env_path = REPO_ROOT / ".env"
    if env_exists:
        print(f"  {OK} .env file found ({env_path})")
    else:
        print(f"  {WARN} .env file not found — copy .env.example and fill in keys")

    if fix_mode and not env_exists:
        _fix_env_file()

    for key, label, url in API_KEYS:
        val = os.environ.get(key, "")
        if val:
            masked = val[:4] + "…" + val[-4:] if len(val) > 12 else "***"
            print(f"  {OK} {label}: {masked}")
        else:
            suffix = f"  → {url}" if url else ""
            print(f"  {WARN} {label}: not set{suffix}")
    print()

    # ── TeX Live packages ─────────────────────────────────────────────────────
    print("📦 TeX Live packages:")
    if check_command("kpsewhich"):
        for sty, label in TEXLIVE_PACKAGES:
            ok = check_texlive_package(sty)
            if ok:
                print(f"  {OK} {label}")
            else:
                pkg = sty.replace(".sty", "")
                print(f"  {FAIL} {label}  →  tlmgr install {pkg}")
                all_ok = False
    else:
        print(f"  {WARN} kpsewhich not found — cannot verify TeX Live packages")
    print()

    # ── Fonts ─────────────────────────────────────────────────────────────────
    print("🔤 Fonts:")
    if check_command("fc-list"):
        found, variant = check_source_sans_font()
        if found:
            print(f"  {OK} {variant} (required by awesome-cv)")
        else:
            if OS_TAG == "macos":
                hint = "brew install --cask font-source-sans-3"
            elif OS_TAG == "debian":
                hint = "sudo apt install fonts-open-sans  (or install via tlmgr)"
            elif OS_TAG == "windows":
                hint = "scoop install nerd-fonts  or install SourceSans3 manually"
            else:
                hint = "install SourceSans3 system font or via tlmgr install sourcecodepro"
            print(f"  {WARN} SourceSans3/SourceSansPro not found  →  {hint}")
            print(f"       (awesome-cv.cls will be auto-patched to use SourceSans3 if available)")
    else:
        print(f"  {WARN} fc-list not found — cannot verify fonts (fontconfig not installed)")
    print()

    # ── Git configuration ─────────────────────────────────────────────────────
    print("🔀 Git configuration:")
    try:
        result = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, cwd=REPO_ROOT)
        git_name = result.stdout.strip()
        result2 = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True, cwd=REPO_ROOT)
        git_email = result2.stdout.strip()
        if git_name and git_email:
            print(f"  {OK} user.name: {git_name}")
            print(f"  {OK} user.email: {git_email}")
        else:
            print(f"  {WARN} Git user not configured — run: git config --global user.name / user.email")
            all_ok = False
    except Exception:
        print(f"  {WARN} Could not read git config")

    # Check submodule initialised
    awesome_cv_cls = REPO_ROOT / "awesome-cv" / "awesome-cv.cls"
    if awesome_cv_cls.exists():
        print(f"  {OK} awesome-cv submodule initialised")
        # Check freshness
        status, msg = check_submodule_fresh()
        if status == "ok":
            print(f"  {OK} awesome-cv submodule up to date")
        elif status == "behind":
            print(f"  {WARN} awesome-cv submodule: {msg}")
            print(f"       run: make submodule-update")
        elif status == "error":
            print(f"  {WARN} awesome-cv submodule freshness unknown: {msg}")
    else:
        if fix_mode:
            print(f"  🔧 Initialising awesome-cv submodule...")
            if _fix_submodule():
                print(f"  {OK} awesome-cv submodule initialised")
            else:
                print(f"  {FAIL} awesome-cv submodule init failed")
                all_ok = False
        else:
            print(f"  {FAIL} awesome-cv submodule missing — run: git submodule update --init --recursive")
            all_ok = False
    print()

    # ── Data files ────────────────────────────────────────────────────────────
    print("📄 Data files:")
    data_files = [
        (REPO_ROOT / "data" / "cv.yml", "data/cv.yml (master CV)"),
        (REPO_ROOT / "data" / "cv-schema.json", "data/cv-schema.json (schema)"),
        (REPO_ROOT / "CV.tex", "CV.tex (LaTeX template)"),
        (REPO_ROOT / "CoverLetter.tex", "CoverLetter.tex (CL template)"),
    ]
    for path, label in data_files:
        ok = path.exists()
        print(f"  {OK if ok else WARN} {label}")
        if not ok and "cv.yml" in str(path):
            all_ok = False
    print()

    # ── Applications summary ──────────────────────────────────────────────────
    apps_dir = REPO_ROOT / "applications"
    if apps_dir.exists():
        app_dirs = [d for d in apps_dir.iterdir() if d.is_dir()]
        print(f"📁 Applications: {len(app_dirs)} found")
        if app_dirs:
            print(f"   Latest: {sorted(d.name for d in app_dirs)[-1]}")
    print()

    # ── Summary ───────────────────────────────────────────────────────────────
    if all_ok:
        if fix_mode:
            print("✅ All required dependencies are installed! Nothing to fix.\n")
        else:
            print("✅ All required dependencies are installed!\n")
        return 0
    else:
        if fix_mode:
            print("⚠️  Some issues could not be auto-fixed.\n")
        else:
            print("❌ Some required dependencies are missing.\n")
        print("   Quick fix: run  make install-deps  to install all system dependencies")
        print("   Then:       run  make dev-setup     to create the Python venv")
        print("   Then:       run  make doctor        to verify everything is in order")
        return 1


if __name__ == "__main__":
    sys.exit(main())
