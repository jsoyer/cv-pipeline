#!/usr/bin/env python3
"""
CV Pipeline API — HTTP webhook server to trigger the pipeline from external tools.

Exposes a simple REST API so the Tampermonkey userscript (Phase 22) and other
integrations can trigger CV tailoring without a terminal.

Endpoints:
  GET  /health             — liveness check
  GET  /status             — list all applications with outcome
  GET  /status/<name>      — single application meta
  POST /pipeline           — create app + tailor (body: {url, company, position})
  POST /fetch              — fetch job description only (body: {url, name})
  GET  /score/<name>       — ATS score for an application

Requires: Python 3.9+ (stdlib http.server — no extra deps)
Optional: install `requests` for full pipeline support

Usage:
    scripts/cv-api.py [--port 8765] [--host 127.0.0.1]
    make cv-api [PORT=8765]

Security: binds to 127.0.0.1 by default. Change HOST= only for trusted networks.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import date
from http import HTTPStatus
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# Adjust PYTHONPATH so scripts/ imports work
SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from lib.common import load_meta
except ImportError:

    def load_meta(path):  # type: ignore[misc]
        return {}


DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_response(handler, status: int, data: dict | list) -> None:
    body = json.dumps(data, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if not length:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _slugify(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9-]", "-", text.lower()).strip("-")[:40]


def _list_applications() -> list[dict]:
    apps_dir = REPO_ROOT / "applications"
    if not apps_dir.is_dir():
        return []
    results = []
    for d in sorted(apps_dir.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "meta.yml"
        if not meta_path.exists():
            continue
        if yaml:
            try:
                meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            except Exception:
                meta = {}
        else:
            meta = {}
        results.append(
            {
                "name": d.name,
                "company": meta.get("company", ""),
                "position": meta.get("position", ""),
                "outcome": meta.get("outcome", ""),
                "created": meta.get("created", ""),
            }
        )
    return results


def _get_meta(name: str) -> dict | None:
    app_dir = REPO_ROOT / "applications" / name
    meta_path = app_dir / "meta.yml"
    if not meta_path.exists():
        return None
    if yaml:
        try:
            return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def _run_make(target: str, env_extra: dict | None = None) -> tuple[int, str]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["make", target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    output = result.stdout + result.stderr
    return result.returncode, output


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


class CVApiHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[cv-api] {self.address_string()} {fmt % args}\n")

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/health":
            _json_response(self, 200, {"status": "ok", "version": "1.0.0"})

        elif path == "/status":
            apps = _list_applications()
            _json_response(self, 200, {"total": len(apps), "applications": apps})

        elif path.startswith("/status/"):
            name = path[len("/status/") :]
            meta = _get_meta(name)
            if meta is None:
                _json_response(self, 404, {"error": f"Application '{name}' not found"})
            else:
                _json_response(self, 200, {"name": name, **meta})

        elif path.startswith("/score/"):
            name = path[len("/score/") :]
            app_dir = REPO_ROOT / "applications" / name
            if not app_dir.is_dir():
                _json_response(self, 404, {"error": f"Application '{name}' not found"})
                return
            rc, out = _run_make(f"score NAME={name}")
            # Parse score from output
            import re

            m = re.search(r"(\d+\.?\d*)%", out)
            score = float(m.group(1)) if m else None
            _json_response(self, 200, {"name": name, "score": score, "output": out[-500:]})

        else:
            _json_response(self, 404, {"error": "Not found", "path": path})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = _read_body(self)

        if path == "/fetch":
            return self._handle_fetch(body)
        elif path == "/pipeline":
            return self._handle_pipeline(body)
        elif path == "/notify":
            return self._handle_notify(body)
        else:
            _json_response(self, 404, {"error": "Not found"})

    def _handle_fetch(self, body: dict) -> None:
        """POST /fetch — fetch job description from URL."""
        url = body.get("url", "").strip()
        name = body.get("name", "").strip()

        if not url:
            _json_response(self, 400, {"error": "url is required"})
            return

        if not name:
            _json_response(self, 400, {"error": "name is required"})
            return

        app_dir = REPO_ROOT / "applications" / name
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "job.url").write_text(url, encoding="utf-8")

        rc, out = _run_make(f"fetch NAME={name}")
        if rc == 0:
            _json_response(self, 200, {"status": "ok", "name": name, "output": out[-300:]})
        else:
            _json_response(self, 500, {"status": "error", "name": name, "output": out[-500:]})

    def _handle_pipeline(self, body: dict) -> None:
        """POST /pipeline — create app dir and run full pipeline.

        Body fields:
          url         — job posting URL (used for fetch if no description)
          company     — company name
          position    — job title
          description — full job description text (extracted by userscript, skips fetch)
          name        — optional app name (auto-generated from date+company if omitted)
          provider    — AI provider (default: gemini)
        """
        url = body.get("url", "").strip()
        company = body.get("company", "").strip()
        position = body.get("position", "").strip()
        description = body.get("description", "").strip()
        name = body.get("name", "").strip()
        provider = body.get("provider", "gemini").strip()

        if not url and not name and not description:
            _json_response(self, 400, {"error": "url, name, or description is required"})
            return

        # Auto-generate name if not provided
        if not name:
            month = date.today().strftime("%Y-%m")
            slug = _slugify(company or "company")
            name = f"{month}-{slug}"

        app_dir = REPO_ROOT / "applications" / name
        app_dir.mkdir(parents=True, exist_ok=True)

        # Bootstrap meta.yml if missing
        meta_path = app_dir / "meta.yml"
        if not meta_path.exists() and yaml:
            meta = {
                "company": company or name,
                "position": position or "",
                "created": date.today().strftime("%Y-%m"),
                "outcome": "applied",
            }
            meta_path.write_text(yaml.dump(meta, allow_unicode=True, sort_keys=False))

        # Write job.url
        if url:
            (app_dir / "job.url").write_text(url, encoding="utf-8")

        steps = []

        if description:
            # Userscript sent the description directly — write to job.txt, skip fetch
            (app_dir / "job.txt").write_text(description, encoding="utf-8")
            steps.append({"step": "description", "rc": 0, "output": f"Wrote {len(description)} chars to job.txt"})
        elif url:
            # Fall back to fetching from URL
            rc, out = _run_make(f"fetch NAME={name}")
            steps.append({"step": "fetch", "rc": rc, "output": out[-200:]})
            if rc != 0:
                _json_response(self, 500, {"status": "error", "name": name, "steps": steps})
                return

        rc, out = _run_make(f"tailor NAME={name} AI={provider}")
        steps.append({"step": "tailor", "rc": rc, "output": out[-200:]})

        status = "ok" if rc == 0 else "error"
        http_status = 200 if rc == 0 else 500
        _json_response(
            self,
            http_status,
            {
                "status": status,
                "name": name,
                "company": company,
                "position": position,
                "steps": steps,
            },
        )

    def _handle_notify(self, body: dict) -> None:
        """POST /notify — update application status."""
        name = body.get("name", "").strip()
        status = body.get("status", "").strip()

        if not name or not status:
            _json_response(self, 400, {"error": "name and status are required"})
            return

        rc, out = _run_make(f"notify NAME={name} STATUS={status}")
        http_status = 200 if rc == 0 else 500
        _json_response(
            self,
            http_status,
            {
                "status": "ok" if rc == 0 else "error",
                "output": out[-300:],
            },
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="CV Pipeline API server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host to bind to (default: {DEFAULT_HOST})")
    args = parser.parse_args()

    server = http.server.HTTPServer((args.host, args.port), CVApiHandler)
    print(f"🚀 cv-api listening on http://{args.host}:{args.port}")
    print(f"   GET  /health           — liveness check")
    print(f"   GET  /status           — list all applications")
    print(f"   GET  /status/<name>    — single application")
    print(f"   POST /pipeline         — {{url, company, position, provider}}")
    print(f"   POST /fetch            — {{url, name}}")
    print(f"   GET  /score/<name>     — ATS score")
    print(f"   POST /notify           — {{name, status}}")
    print(f"\n   Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
