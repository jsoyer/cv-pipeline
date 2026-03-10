# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-10

### Added

- **Multi-provider AI tailoring** — Gemini (default), Claude, OpenAI, Mistral, Ollama via `make tailor AI=...`
- **`render.py`** — YAML-to-LaTeX pipeline with full Awesome-CV section support (experience, education, skills, projects, certifications, languages, publications, honors)
- **`doctor.py`** — Dependency health check with per-tool, per-OS install hints (macOS/Debian/Fedora/Arch/Windows); detects TeX Live, fonts, Python modules, and env vars
- **`watch.py`** — File watcher for live PDF regeneration on YAML changes
- **`notify.py`** — Multi-channel status notifications (Slack, Discord, Telegram, Notion, GitHub labels) via `make notify`
- **`notion-twoway.py`** — Bidirectional sync between YAML and Notion database
- **`cv-api.py`** — Lightweight HTTP webhook server (stdlib only, no dependencies)
- **`scripts/lib/common.py`** — Shared utilities: `find_xelatex()` auto-detection across macOS/Debian/Fedora/Arch, `detect_os()`, AI provider helpers
- **`make install-deps`** — One-command system dependency installer for all major platforms
- **`make dev-setup`** — Creates Python venv and installs all dependencies
- **`make submodule-update`** — Updates Awesome-CV submodule
- **`make tailor`**, `make render`, `make watch`, `make validate`, `make notify`, `make stats`, `make digest` — 80+ Makefile targets
- **16 CI/CD workflows** — lint, test, security (Bandit + Safety), CodeQL, dependency review, portfolio sync, Notion sync, digest, deadline alerts, release
- **JSON Schema validation** — `data/cv-schema.json` validates YAML structure before rendering
- **xelatex auto-detection** — Resolves BasicTeX, TeX Live (macOS/Linux), system packages without manual path configuration
- **venv support** — Makefile auto-selects `venv/bin/python3` when available
- **`.env.example`** — Template for all supported environment variables

### Technical

- Baremetal-only (no Docker dependency)
- Python 3.8+ compatible
- `pyyaml`, `requests`, `beautifulsoup4`, `jsonschema` as core dependencies
- Awesome-CV submodule pinned at upstream HEAD
- YAML is the single source of truth — no manual `.tex` editing required
