# Contributing

This is a personal CV repository, but the automation tooling may be useful to others.

## Setup

```bash
git clone --recurse-submodules https://github.com/jsoyer/cv-pipeline.git
cd cv-pipeline
pip install -r requirements.txt
make doctor    # Check all dependencies
```

## Project Structure

- `data/` — YAML source of truth (CV content, schema, templates)
- `scripts/` — 67 Python scripts + shared library (`scripts/lib/`)
- `scripts/lib/` — Shared modules: `ai.py` (multi-provider AI), `common.py` (utilities)
- `examples/meta.yml` — Sample application metadata (see below)
- `Makefile` — 83+ build/automation targets
- `.github/workflows/` — 14 CI/CD workflows

## Application Metadata

Each application directory contains a `meta.yml` file tracking its state. See `examples/meta.yml` for the template:

| Field | Required | Description |
|-------|----------|-------------|
| `company` | yes | Company name |
| `position` | yes | Job title |
| `created` | yes | Creation date (YYYY-MM) |
| `deadline` | no | Application deadline (YYYY-MM-DD) |
| `url` | no | Job posting URL |
| `outcome` | no | `applied` / `interview` / `offer` / `rejected` / `ghosted` |
| `response_days` | no | Days until first response |

## Development

```bash
make help          # See all available targets
make doctor        # Verify dependencies
make check         # Run all validations
python3 -m py_compile scripts/<script>.py  # Syntax check
```

## Testing

```bash
pip install pytest
python -m pytest tests/ -v    # 99 tests across 3 modules
```

Tests cover rendering (`test_render.py`), AI providers (`test_ai.py`), and shared utilities (`test_common.py`).

## Conventions

- **YAML is the source of truth** — no LaTeX in YAML, no manual `.tex` editing
- **AI outputs YAML, not LaTeX** — `render.py` handles all LaTeX rendering
- **JSON Schema** — `data/cv-schema.json` validates YAML before rendering
- **Conventional commits**: `feat:`, `fix:`, `refactor:`, `chore:`, `style:`
- **Branch naming**: `apply/YYYY-MM-company` for applications
- **CV max 2 pages, Cover Letter max 1 page** — CI enforces this
- **Python 3.8+** with `pyyaml`, `requests`, `beautifulsoup4`

## License

CV content is personal and proprietary. The [Awesome-CV](https://github.com/posquit0/Awesome-CV) template is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Automation scripts are MIT-licensed.
