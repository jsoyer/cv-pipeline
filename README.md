# CV Pipeline

An end-to-end CV and cover letter automation system built on the [Awesome-CV](https://github.com/posquit0/Awesome-CV) LaTeX template.

AI handles content generation (tailoring, cover letters). Claude Code handles all code, build, and automation.

## Architecture

```
data/cv.yml + job.txt → AI (Claude / Gemini / OpenAI / Mistral / Ollama)
                       → cv-tailored.yml + coverletter.yml
                       → render.py → .tex → XeLaTeX → PDF
```

- **Data**: `data/cv.yml` — YAML source of truth, no LaTeX in YAML
- **Renderer**: `scripts/render.py` — YAML → LaTeX, handles escaping + `**bold**` → `\textbf{}`
- **AI Tailoring**: `scripts/ai-tailor.py` — multi-provider (Claude, Gemini, OpenAI, Mistral, Ollama)
- **ATS Scoring**: `scripts/ats-score.py` — keyword scoring with section-aware weighting
- **Build**: `Makefile` with ~35 targets

## AI Providers

| Provider | Key |
|----------|-----|
| Claude (default) | `ANTHROPIC_API_KEY` |
| Gemini | `GEMINI_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Mistral | `MISTRAL_API_KEY` |
| Ollama | `OLLAMA_HOST` / `OLLAMA_MODEL` (local, no key) |

## Quick Start

```bash
cp .env.example .env        # add your API keys
make                        # build master CV + Cover Letter
make tailor NAME=my-app AI=claude   # AI tailor for a specific job
make open NAME=my-app       # build + open PDFs
```

## Key Commands

```bash
make tailor NAME=... [AI=claude|gemini|openai] [TARGET=cv|cl|both] [MODEL=...]
make app NAME=...           # build specific application
make score NAME=...         # ATS keyword score
make review NAME=...        # render + build + validate + ATS
make check                  # YAML validation + lint + ATS
make help                   # all ~35 targets
```

## CI/CD

13 GitHub Actions workflows: PDF build, ATS scoring comparison, page validation, PR preview with DRAFT watermark, GitHub Release on merge, Notion sync, follow-up reminders, and more.

## Scripts

22 scripts in `scripts/` — AI tailoring, ATS scoring, interview prep, skills gap analysis, changelog, LinkedIn sync, TUI, and more.

## Stack

- **LaTeX**: XeLaTeX + Awesome-CV template
- **AI**: Claude API (Anthropic), Gemini, OpenAI, Mistral, Ollama
- **CI/CD**: GitHub Actions
- **Python**: render.py, ats-score.py, ai-tailor.py, 22 scripts total
- **TUI**: Textual
