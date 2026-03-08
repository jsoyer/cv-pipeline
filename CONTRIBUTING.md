# Contributing

This is a personal CV repository, but the automation tooling may be useful to others.

## Setup

```bash
git clone --recurse-submodules https://github.com/jsoyer/CV.git
cd CV
pip install -r requirements.txt
make doctor    # Check all dependencies
```

## Project Structure

- `data/` — YAML source of truth (CV content, schema, templates)
- `scripts/` — 67 Python scripts + shared library (`scripts/lib/`)
- `scripts/lib/` — Shared modules: `ai.py` (multi-provider AI), `common.py` (utilities)
- `Makefile` — 83+ build/automation targets
- `.github/workflows/` — 14 CI/CD workflows

## Development

```bash
make help          # See all available targets
make doctor        # Verify dependencies
make check         # Run all validations
python3 -m py_compile scripts/<script>.py  # Syntax check
```

## Conventions

- **YAML is the source of truth** — no LaTeX in YAML, no manual `.tex` editing
- **AI outputs YAML, not LaTeX** — `render.py` handles all LaTeX rendering
- **Conventional commits**: `feat:`, `fix:`, `refactor:`, `chore:`, `style:`
- **Branch naming**: `apply/YYYY-MM-company` for applications
- **CV ≤ 2 pages, Cover Letter ≤ 1 page** — CI enforces this
- **Python 3.8+** with `pyyaml`, `requests`, `beautifulsoup4`

## License

CV content is personal and proprietary. The [Awesome-CV](https://github.com/posquit0/Awesome-CV) template is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Automation scripts are MIT-licensed.
