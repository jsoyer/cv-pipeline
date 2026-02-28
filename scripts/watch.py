#!/usr/bin/env python3
"""
Watch Mode — Auto-recompile when YAML files change in an application folder.

Watches cv-tailored.yml and coverletter.yml for changes, then automatically:
  1. Renders YAML → LaTeX (render.py)
  2. Compiles LaTeX → PDF (xelatex)
  3. Reports page count and any errors

Usage:
    scripts/watch.py <app-dir>           Watch specific application
    scripts/watch.py                     Watch all applications/

Requires: watchdog (pip install watchdog)
Fallback: polling mode (no deps required)
"""

import os
import subprocess
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parent

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

# Detect xelatex
import platform
if platform.system() == "Darwin":
    XELATEX = os.environ.get("XELATEX", "/usr/local/texlive/2025basic/bin/universal-darwin/xelatex")
else:
    XELATEX = os.environ.get("XELATEX", "xelatex")

TEXINPUTS = str(_REPO_ROOT / "awesome-cv") + ":" + os.environ.get("TEXINPUTS", "")

WATCH_FILES = {"cv-tailored.yml", "coverletter.yml", "data/cv.yml", "data/coverletter.yml"}


def get_pdf_pages(pdf_path: Path) -> int:
    """Count PDF pages using regex on raw bytes."""
    import re
    try:
        with open(pdf_path, "rb") as f:
            content = f.read()
        m = re.search(rb"/Type\s*/Pages\b[^>]*/Count\s+(\d+)", content)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def render_and_compile(app_dir: Path, changed_file: str = "") -> bool:
    """Run render.py + xelatex for the given application."""
    env = os.environ.copy()
    env["TEXINPUTS"] = TEXINPUTS

    print(f"\n🔄 Change detected: {changed_file or app_dir.name}")
    print(f"   {'─' * 48}")

    # Render CV
    cv_tailored = app_dir / "cv-tailored.yml"
    cv_tex_files = list(app_dir.glob("CV - *.tex"))
    if cv_tailored.exists() and cv_tex_files:
        cv_tex = cv_tex_files[0]
        print(f"   📄 Rendering CV...", end=" ", flush=True)
        result = subprocess.run(
            ["python3", "scripts/render.py", "-d", str(cv_tailored), "-o", str(cv_tex)],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        if result.returncode == 0:
            print("✅")
        else:
            print(f"❌\n   {result.stderr.strip()[:120]}")

    # Render CL
    cl_yml = app_dir / "coverletter.yml"
    cl_tex_files = list(app_dir.glob("CoverLetter - *.tex"))
    if cl_yml.exists() and cl_tex_files:
        cl_tex = cl_tex_files[0]
        cv_data = str(cv_tailored) if cv_tailored.exists() else "data/cv.yml"
        print(f"   📨 Rendering Cover Letter...", end=" ", flush=True)
        result = subprocess.run(
            ["python3", "scripts/render.py", "-d", str(cl_yml), "-o", str(cl_tex),
             "--cv-data", str(_REPO_ROOT / cv_data)],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        if result.returncode == 0:
            print("✅")
        else:
            print(f"❌\n   {result.stderr.strip()[:120]}")

    # Compile all .tex files
    tex_files = list(app_dir.glob("*.tex"))
    if not tex_files:
        print(f"   ⚠️  No .tex files found in {app_dir}/")
        return False

    all_ok = True
    for tex in sorted(tex_files):
        name = tex.stem
        print(f"   🔨 Compiling {tex.name}...", end=" ", flush=True)
        result = subprocess.run(
            [XELATEX, "-interaction=nonstopmode", f"-output-directory={app_dir}", str(tex)],
            capture_output=True, text=True, env=env, cwd=_REPO_ROOT,
        )
        pdf = app_dir / (tex.stem + ".pdf")
        if result.returncode == 0 and pdf.exists():
            pages = get_pdf_pages(pdf)
            is_cl = "CoverLetter" in tex.name
            limit = 1 if is_cl else 2
            page_icon = "✅" if pages <= limit else "❌"
            print(f"✅  ({pages} page{'s' if pages != 1 else ''} {page_icon})")
        else:
            # Extract last error from log
            log_lines = result.stdout.splitlines()
            errors = [l for l in log_lines if l.startswith("!")]
            err_msg = errors[-1][:80] if errors else "compilation failed"
            print(f"❌  {err_msg}")
            all_ok = False

    print(f"   {'─' * 48}")
    ts = time.strftime("%H:%M:%S")
    print(f"   ⏱  {ts} — watching for changes…")
    return all_ok


# ── Watchdog handler ───────────────────────────────────────────────────────────

if HAS_WATCHDOG:
    class YAMLChangeHandler(FileSystemEventHandler):
        def __init__(self, app_dirs: list):
            self.app_dirs = app_dirs
            self._last_trigger: dict = {}  # debounce per file

        def on_modified(self, event):
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix not in (".yml", ".yaml"):
                return
            # Debounce: ignore events within 1 second of last trigger
            now = time.time()
            key = str(path)
            if now - self._last_trigger.get(key, 0) < 1.0:
                return
            self._last_trigger[key] = now

            # Find which app_dir this belongs to
            for app_dir in self.app_dirs:
                try:
                    path.relative_to(app_dir)
                    render_and_compile(app_dir, path.name)
                    return
                except ValueError:
                    continue


# ── Polling fallback ───────────────────────────────────────────────────────────

def poll_watch(app_dirs: list, interval: float = 1.5) -> None:
    """Polling-based file watcher (fallback when watchdog is not installed)."""
    mtimes: dict = {}

    # Initialize mtimes
    for app_dir in app_dirs:
        for f in app_dir.glob("*.yml"):
            mtimes[str(f)] = f.stat().st_mtime

    print(f"   (polling mode — install watchdog for faster detection)")

    while True:
        time.sleep(interval)
        for app_dir in app_dirs:
            for f in app_dir.glob("*.yml"):
                key = str(f)
                try:
                    mtime = f.stat().st_mtime
                except FileNotFoundError:
                    continue
                if key not in mtimes:
                    mtimes[key] = mtime
                    render_and_compile(app_dir, f.name)
                elif mtime > mtimes[key]:
                    mtimes[key] = mtime
                    render_and_compile(app_dir, f.name)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    app_dirs = []

    # Resolve app directories to watch
    if args and not args[0].startswith("-"):
        d = Path(args[0])
        if not d.is_dir():
            print(f"❌ Directory not found: {d}")
            sys.exit(1)
        app_dirs = [d]
    else:
        # Watch all application folders
        apps_root = _REPO_ROOT / "applications"
        if apps_root.exists():
            app_dirs = [d for d in sorted(apps_root.iterdir())
                        if d.is_dir() and any(d.glob("*.tex"))]
        if not app_dirs:
            print("❌ No application directories with .tex files found")
            print("   Usage: scripts/watch.py <app-dir>")
            sys.exit(1)

    # Initial build
    print("👀 Watch Mode")
    print(f"   Watching {len(app_dirs)} application(s):")
    for d in app_dirs:
        print(f"   • {d.name}")
    print()

    if not HAS_WATCHDOG:
        print("💡 Tip: pip install watchdog for faster file detection")
        print()

    # Do initial compile
    for app_dir in app_dirs:
        render_and_compile(app_dir, "(initial build)")

    print()
    print("⌨️  Press Ctrl+C to stop watching")
    print()

    try:
        if HAS_WATCHDOG:
            handler = YAMLChangeHandler(app_dirs)
            observer = Observer()
            for app_dir in app_dirs:
                observer.schedule(handler, str(app_dir), recursive=False)
            observer.start()
            try:
                while True:
                    time.sleep(1)
            finally:
                observer.stop()
                observer.join()
        else:
            poll_watch(app_dirs)
    except KeyboardInterrupt:
        print("\n\n⏹  Watch mode stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
