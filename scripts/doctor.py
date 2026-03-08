#!/usr/bin/env python3
"""Doctor — Check all dependencies and environment for the CV system."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from lib.common import REPO_ROOT, load_env

# ---------------------------------------------------------------------------
# Tool checks
# ---------------------------------------------------------------------------

TOOL_CHECKS = [
    ("xelatex",  "XeLaTeX (LaTeX engine)",          "/usr/local/texlive/2025basic/bin/universal-darwin/xelatex"),
    ("chktex",   "ChkTeX (LaTeX linter)",            None),
    ("gh",       "GitHub CLI",                       None),
    ("python3",  "Python 3",                         None),
    ("convert",  "ImageMagick",                      None),
    ("aspell",   "Aspell (spell checker)",           None),
    ("pandoc",   "Pandoc (DOCX conversion)",         None),
    ("git",      "Git",                              None),
]

OPTIONAL_TOOLS = [
    ("tidy",     "HTML tidy (dashboard)"),
    ("ollama",   "Ollama (local AI)"),
    ("jq",       "jq (JSON processing)"),
]

# ---------------------------------------------------------------------------
# Python module checks
# ---------------------------------------------------------------------------

REQUIRED_MODULES = [
    ("yaml",     "PyYAML",           "pip install pyyaml"),
    ("requests", "requests",         "pip install requests"),
    ("bs4",      "Beautiful Soup 4", "pip install beautifulsoup4"),
]

OPTIONAL_MODULES = [
    ("watchdog",           "watchdog (watch mode)",         "pip install watchdog"),
    ("textual",            "Textual (TUI)",                 "pip install textual"),
    ("google.generativeai","google-generativeai (Gemini)",  "pip install google-generativeai"),
    ("anthropic",          "anthropic SDK",                 "pip install anthropic"),
    ("openai",             "openai SDK",                    "pip install openai"),
    ("mistralai",          "mistralai SDK",                 "pip install mistralai"),
]

# ---------------------------------------------------------------------------
# API key checks
# ---------------------------------------------------------------------------

API_KEYS = [
    ("GEMINI_API_KEY",       "Gemini API key",         "https://aistudio.google.com/apikey"),
    ("ANTHROPIC_API_KEY",    "Anthropic API key",      "https://console.anthropic.com/"),
    ("OPENAI_API_KEY",       "OpenAI API key",         "https://platform.openai.com/api-keys"),
    ("MISTRAL_API_KEY",      "Mistral API key",        "https://console.mistral.ai/"),
    ("SLACK_WEBHOOK_URL",    "Slack webhook URL",      None),
    ("DISCORD_WEBHOOK_URL",  "Discord webhook URL",    None),
    ("NOTION_TOKEN",         "Notion API token",       None),
    ("GITHUB_TOKEN",         "GitHub token (CI only)", None),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OK  = "✅"
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("🔍 CV System Doctor\n")

    all_ok = True
    missing_install = []

    # ── Required tools ────────────────────────────────────────────────────────
    print("🛠️  Required tools:")
    for cmd, name, path in TOOL_CHECKS:
        ok = check_command(cmd, path)
        print(f"  {OK if ok else FAIL} {name}")
        if not ok:
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

    for key, label, url in API_KEYS:
        val = os.environ.get(key, "")
        if val:
            masked = val[:4] + "…" + val[-4:] if len(val) > 12 else "***"
            print(f"  {OK} {label}: {masked}")
        else:
            suffix = f"  → {url}" if url else ""
            print(f"  {WARN} {label}: not set{suffix}")
    print()

    # ── Git configuration ─────────────────────────────────────────────────────
    print("🔀 Git configuration:")
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        git_name = result.stdout.strip()
        result2 = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        git_email = result2.stdout.strip()
        if git_name and git_email:
            print(f"  {OK} user.name: {git_name}")
            print(f"  {OK} user.email: {git_email}")
        else:
            print(f"  {WARN} Git user not configured — run: git config --global user.name / user.email")
            all_ok = False
    except Exception:
        print(f"  {WARN} Could not read git config")

    # Check submodule
    awesome_cv_cls = REPO_ROOT / "awesome-cv" / "awesome-cv.cls"
    if awesome_cv_cls.exists():
        print(f"  {OK} awesome-cv submodule initialized")
    else:
        print(f"  {FAIL} awesome-cv submodule missing — run: git submodule update --init --recursive")
        all_ok = False
    print()

    # ── Data files ────────────────────────────────────────────────────────────
    print("📄 Data files:")
    data_files = [
        (REPO_ROOT / "data" / "cv.yml",         "data/cv.yml (master CV)"),
        (REPO_ROOT / "data" / "cv-schema.json", "data/cv-schema.json (schema)"),
        (REPO_ROOT / "CV.tex",                  "CV.tex (LaTeX template)"),
        (REPO_ROOT / "CoverLetter.tex",          "CoverLetter.tex (CL template)"),
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
        print("✅ All required dependencies are installed!\n")
        return 0
    else:
        print("❌ Some required dependencies are missing.\n")
        print("   Install required tools:")
        print("     brew install texlive chktex gh imagemagick aspell pandoc  (macOS)")
        print("     sudo apt install texlive-xetex chktex gh imagemagick aspell pandoc  (Linux)")
        print("   Install required Python modules:")
        print("     pip install pyyaml requests beautifulsoup4")
        return 1


if __name__ == "__main__":
    sys.exit(main())
