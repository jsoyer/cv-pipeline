.PHONY: all open app new apply tailor render score status lint diff compare \
       archive export docx linkedin hooks check report fetch prep changelog status \
       skills visual-diff stats clean doctor timeline length match followup effectiveness review help \
       tone cl-score research discover discover-apply batch batch-dry dashboard \
       trends thankyou negotiate notify watch follow-up \
       contacts url-check digest json-resume question-bank ats-rank ats-text \
       job-fit linkedin-message cv-health cv-versions milestone deadline-alert cover-angles \
       recruiter-email references network-map prep-quiz competitor-map salary-bench cv-fr-tailor apply-board \
       archive-app linkedin-profile \
       interview-brief prep-star interview-debrief linkedin-post export-csv \
       elevator-pitch onboarding-plan cover-critique interview-sim \
       cv-keywords blind-spots current pipeline tui \
       status-active completions-bash completions-fish completions-ps1 completions-nu \
       test coverage preview clean-all dev-setup validate-all predict \
       compare-providers accent cache-stats cache-clear \
       ats-history funnel analytics \
       notion-pull notion-push notion-diff \
       boards boards-file cv-api \
       doctor-fix semantic smart-followup \
       beautify migrate \
       market-list market-search market-install market-installed \
       portfolio portfolio-fr docker-build docker-run

# Auto-load .env if present (for GEMINI_API_KEY)
-include .env
# Only export variables that child processes actually need (not all .env secrets)
export TEXINPUTS
export GEMINI_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY MISTRAL_API_KEY
export OLLAMA_HOST OLLAMA_MODEL
export SLACK_WEBHOOK_URL DISCORD_WEBHOOK_URL
export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
export LINKEDIN_ACCESS_TOKEN

# Reset LANG to avoid conflict with system locale (fr_FR.UTF-8)
# User can still pass: make render LANG=fr
LANG :=

# AI provider for make tailor (default: gemini)
# Usage: make tailor NAME=... AI=claude
AI ?= gemini

# Docker image name (used by make docker-build / make docker-run)
DOCKER_IMAGE ?= ghcr.io/janedoe/cv-pipeline

UNAME := $(shell uname -s)
ifeq ($(UNAME), Darwin)
    XELATEX ?= /usr/local/texlive/2025basic/bin/universal-darwin/xelatex
    OPEN_CMD := open
    SED_I := sed -i ''
else
    XELATEX ?= xelatex
    OPEN_CMD := xdg-open
    SED_I := sed -i
endif
TEXINPUTS := $(CURDIR)/awesome-cv/:$(TEXINPUTS)

# Use venv Python if available, else fall back to system python3
PYTHON := $(shell [ -x venv/bin/python3 ] && echo venv/bin/python3 || echo python3)

# Auto-init submodule if awesome-cv.cls is missing
ifeq (,$(wildcard $(CURDIR)/awesome-cv/awesome-cv.cls))
    $(shell git submodule update --init --recursive)
endif

# Auto-install fontawesome6 if missing (required by awesome-cv.cls)
ifeq (,$(shell kpsewhich fontawesome6.sty 2>/dev/null))
    $(shell tlmgr init-usertree 2>/dev/null; tlmgr install fontawesome6 2>/dev/null)
endif

# Auto-detect NAME from current apply/* branch when not explicitly provided
ifeq ($(NAME),)
_BRANCH := $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null)
ifneq ($(filter apply/%,$(_BRANCH)),)
NAME := $(_BRANCH:apply/%=%)
endif
endif

# Print the current application name (derived from apply/* branch)
# Usage: make current
current:
	@branch=$$(git rev-parse --abbrev-ref HEAD 2>/dev/null); \
	if printf '%s' "$$branch" | grep -q "^apply/"; then \
		echo "$${branch#apply/}"; \
	else \
		echo "Not on an apply/* branch (current: $$branch)" >&2; \
		exit 1; \
	fi

# Build master resume and cover letter PDFs
all:
	@$(MAKE) --no-print-directory render
	@echo "🔨 Compiling PDFs..."
	@$(XELATEX) -output-directory=. CV.tex > /dev/null 2>&1 && echo "   ✅ CV.pdf" || echo "   ❌ CV.tex — compilation failed"
	@if [ -f CoverLetter.tex ]; then \
		$(XELATEX) -output-directory=. CoverLetter.tex > /dev/null 2>&1 && echo "   ✅ CoverLetter.pdf" || echo "   ❌ CoverLetter.tex — compilation failed"; \
	fi
	@echo "✅ Build complete"

# Build and open PDFs in Preview
# Usage: make open  or  make open NAME=2026-02-databricks
open:
	@if [ -n "$(NAME)" ]; then \
		$(MAKE) --no-print-directory app NAME=$(NAME); \
		for f in "applications/$(NAME)/"*.pdf; do \
			[ -f "$$f" ] && $(OPEN_CMD) "$$f"; \
		done; \
	else \
		$(MAKE) --no-print-directory all; \
		$(OPEN_CMD) CV.pdf 2>/dev/null || true; $(OPEN_CMD) CoverLetter.pdf 2>/dev/null || true; \
	fi

# Build a specific application: make app NAME=2026-02-databricks
# Add DRAFT=true for watermark: make app NAME=... DRAFT=true
app:
	@test -n "$(NAME)" || (echo "Usage: make app NAME=2026-02-databricks" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@# Render CV: from tailored YAML if available, otherwise from root data/cv.yml
	@CV_TEX=$$(ls "applications/$(NAME)/CV "*.tex 2>/dev/null | head -1); \
	if [ -f "applications/$(NAME)/cv-tailored.yml" ]; then \
		echo "📄 Rendering tailored CV from YAML..."; \
		if [ -n "$$CV_TEX" ]; then \
			$(PYTHON) scripts/render.py -d "applications/$(NAME)/cv-tailored.yml" -o "$$CV_TEX"; \
		fi; \
	elif [ -n "$$CV_TEX" ]; then \
		echo "📄 Rendering CV from root data/cv.yml..."; \
		$(PYTHON) scripts/render.py -d "data/cv.yml" -o "$$CV_TEX"; \
	fi
	@if [ -f "applications/$(NAME)/coverletter.yml" ]; then \
		echo "📨 Rendering application-specific cover letter..."; \
		CV_DATA=$$([ -f "applications/$(NAME)/cv-tailored.yml" ] && echo "applications/$(NAME)/cv-tailored.yml" || echo "data/cv.yml"); \
		CL_TEX=$$(ls "applications/$(NAME)/CoverLetter "*.tex 2>/dev/null | head -1); \
		CL_OUT=$$([ -n "$$CL_TEX" ] && echo "$$CL_TEX" || echo "applications/$(NAME)/CoverLetter.tex"); \
		if [ "$(DRAFT)" = "true" ]; then \
			$(PYTHON) scripts/render.py -d "applications/$(NAME)/coverletter.yml" -o "$$CL_OUT" --cv-data "$$CV_DATA" --draft; \
		else \
			$(PYTHON) scripts/render.py -d "applications/$(NAME)/coverletter.yml" -o "$$CL_OUT" --cv-data "$$CV_DATA"; \
		fi; \
		if [ -n "$$CL_TEX" ] && [ "$$CL_TEX" != "applications/$(NAME)/CoverLetter.tex" ]; then \
			cp "$$CL_TEX" "applications/$(NAME)/CoverLetter.tex"; \
		fi; \
	fi
	@if [ "$(DRAFT)" = "true" ]; then \
		echo "📝 Adding DRAFT watermark..."; \
		for f in "applications/$(NAME)/"*.tex; do \
			[ -f "$$f" ] || continue; \
			if ! grep -q 'draftwatermark' "$$f"; then \
				$(SED_I) 's/\\begin{document}/\\usepackage{draftwatermark}\n\\SetWatermarkText{DRAFT}\n\\SetWatermarkScale{1.5}\n\\SetWatermarkColor[gray]{0.92}\n\\begin{document}/' "$$f"; \
			fi; \
		done; \
	fi
	@for f in "applications/$(NAME)/"*.tex; do \
		$(XELATEX) -output-directory="applications/$(NAME)" "$$f"; \
	done
	@echo "✅ Built: applications/$(NAME)/"
	@echo ""
	@echo "📏 Page check:"
	@PASS=true; \
	find "applications/$(NAME)" -name "*.pdf" | while IFS= read -r f; do \
		PAGES=$$(pdfinfo "$$f" 2>/dev/null | awk '/^Pages:/{print $$2}'); \
		BASE=$$(basename "$$f"); \
		echo "$$BASE" | grep -qi "coverletter" && LIMIT=1 || LIMIT=2; \
		if [ "$${PAGES:-0}" -le "$$LIMIT" ] 2>/dev/null; then \
			echo "   ✅ $$BASE: $$PAGES page(s)"; \
		else \
			echo "   ❌ $$BASE: $$PAGES page(s) — exceeds $$LIMIT-page limit"; \
			echo "   💡 Trim content in cv-tailored.yml or coverletter.yml"; \
		fi; \
	done

# Scaffold a new application (local only, no git operations)
# Usage: make new COMPANY=Snowflake POSITION="Senior Director SE"
new:
	@test -n "$(COMPANY)" || (echo "Usage: make new COMPANY=Snowflake POSITION=\"Senior Director SE\"" && exit 1)
	@test -n "$(POSITION)" || (echo "Usage: make new COMPANY=Snowflake POSITION=\"Senior Director SE\"" && exit 1)
	@{ \
		set -e; \
		COMPANY="$(COMPANY)"; \
		POSITION="$(POSITION)"; \
		SLUG=$$(printf '%s' "$$COMPANY" | tr '[:upper:]' '[:lower:]' | tr ' ' '-'); \
		DATE=$$(date +%Y-%m); \
		DIR="applications/$$DATE-$$SLUG"; \
		test ! -d "$$DIR" || { echo "Directory $$DIR already exists"; exit 1; }; \
		mkdir -p "$$DIR"; \
		cp CV.tex "$$DIR/CV - $$COMPANY - $$POSITION.tex"; \
		cp CoverLetter.tex "$$DIR/CoverLetter - $$COMPANY - $$POSITION.tex"; \
		if [ -f data/coverletter.yml ]; then cp data/coverletter.yml "$$DIR/coverletter.yml"; fi; \
		printf '# Application metadata\ncompany: %s\nposition: %s\ncreated: %s\n# deadline: YYYY-MM-DD\n# outcome: applied | interview | offer | rejected | ghosted\n# response_days:\n' \
			"$$COMPANY" "$$POSITION" "$$DATE" > "$$DIR/meta.yml"; \
		ESCAPED_CO=$$(printf '%s' "$$COMPANY" | sed 's/[&/\]/\\&/g'); \
		ESCAPED_PO=$$(printf '%s' "$$POSITION" | sed 's/[&/\]/\\&/g'); \
		CL="$$DIR/CoverLetter - $$COMPANY - $$POSITION.tex"; \
		$(SED_I) "s/Hiring Manager/$$ESCAPED_CO Talent Acquisition Team/g" "$$CL"; \
		$(SED_I) "s/Company Name/$$ESCAPED_CO/g" "$$CL"; \
		$(SED_I) "s/\[Position Title\]/$$ESCAPED_PO/g" "$$CL"; \
		$(SED_I) "s/Dear Hiring Manager,/To the $$ESCAPED_CO Talent Acquisition Team,/g" "$$CL"; \
		$(SED_I) "s/Why \[Company\]?/Why $$ESCAPED_CO?/g" "$$CL"; \
		echo "Created: $$DIR/"; \
		echo "   $$DIR/CV - $$COMPANY - $$POSITION.tex"; \
		echo "   $$DIR/CoverLetter - $$COMPANY - $$POSITION.tex"; \
		if [ -f "$$DIR/coverletter.yml" ]; then echo "   $$DIR/coverletter.yml"; fi; \
		echo "   $$DIR/meta.yml"; \
		echo ""; \
		echo "Next steps:"; \
		echo "   1. Set deadline in $$DIR/meta.yml"; \
		echo "   2. Tailor the CV and cover letter content"; \
		echo "   3. Build: make app NAME=$$DATE-$$SLUG"; \
	}

# Full application workflow: scaffold + branch + PR
# Usage: make apply URL=https://...                          (auto-extract company/position)
#        make apply COMPANY=Snowflake POSITION="Sr Dir SE"  (explicit)
#        make apply COMPANY=Snowflake POSITION="Sr Dir SE" URL=https://...  (explicit + fetch)
apply:
	@{ \
		set -e; \
		COMPANY="$(COMPANY)"; POSITION="$(POSITION)"; URL="$(URL)"; \
		if [ -z "$$COMPANY" ] && [ -n "$$URL" ]; then \
			echo "🔍 Extracting company/position from URL..."; \
			INFO=$$($(PYTHON) scripts/fetch-job.py --extract "$$URL" 2>/dev/null) || INFO="{}"; \
			COMPANY=$$(printf '%s' "$$INFO" | $(PYTHON) -c "import json,sys; print(json.load(sys.stdin).get('company',''))"); \
			POSITION=$$(printf '%s' "$$INFO" | $(PYTHON) -c "import json,sys; print(json.load(sys.stdin).get('position',''))"); \
			if [ -n "$$COMPANY" ]; then echo "   Company:  $$COMPANY"; fi; \
			if [ -n "$$POSITION" ]; then echo "   Position: $$POSITION"; fi; \
		fi; \
		test -n "$$COMPANY" || { echo "❌ Cannot determine company. Use: make apply URL=... or COMPANY=X POSITION=\"Y\" URL=..."; exit 1; }; \
		test -n "$$POSITION" || { echo "❌ Cannot determine position. Add POSITION=\"...\" to the command"; exit 1; }; \
		SLUG=$$(echo "$$COMPANY" | tr '[:upper:]' '[:lower:]' | tr ' ' '-'); \
		DATE=$$(date +%Y-%m); \
		FDATE=$$(date +"%B %d, %Y"); \
		DIR="applications/$$DATE-$$SLUG"; \
		BRANCH="apply/$$DATE-$$SLUG"; \
		test ! -d "$$DIR" || { echo "❌ Directory $$DIR already exists — use: git checkout $$BRANCH"; exit 1; }; \
		git ls-remote --exit-code --heads origin "$$BRANCH" > /dev/null 2>&1 && \
			{ echo "❌ Branch $$BRANCH already exists on remote — use: git checkout $$BRANCH"; exit 1; } || true; \
		echo "🔀 Creating branch $$BRANCH..."; \
		git checkout -b "$$BRANCH"; \
		mkdir -p "$$DIR"; \
		cp CV.tex "$$DIR/CV - $$COMPANY - $$POSITION.tex"; \
		cp CoverLetter.tex "$$DIR/CoverLetter - $$COMPANY - $$POSITION.tex"; \
		if [ -f data/coverletter.yml ]; then cp data/coverletter.yml "$$DIR/coverletter.yml"; fi; \
		printf '# Application metadata\ncompany: %s\nposition: %s\ncreated: %s\n# deadline: YYYY-MM-DD\n# outcome: applied | interview | offer | rejected | ghosted\n# response_days:\n' \
			"$$COMPANY" "$$POSITION" "$$DATE" > "$$DIR/meta.yml"; \
		COMP="$$COMPANY" POS="$$POSITION" FDATE="$$FDATE" perl -pi -e \
			's/Hiring Manager/$ENV{COMP} Talent Acquisition Team/g; \
			 s/Company Name/$ENV{COMP}/g; \
			 s/\[Position Title\]/$ENV{POS}/g; \
			 s/Dear Hiring Manager,/To the $ENV{COMP} Talent Acquisition Team,/g; \
			 s|Why \[Company\]\?|Why $ENV{COMP}?|g; \
			 s/\\today/$ENV{FDATE}/g' \
			"$$DIR/CoverLetter - $$COMPANY - $$POSITION.tex" \
			"$$DIR/CV - $$COMPANY - $$POSITION.tex"; \
		if [ -n "$$URL" ]; then \
			printf '%s\n' "$$URL" > "$$DIR/job.url"; \
			echo "📥 Fetching job description..."; \
			$(PYTHON) scripts/fetch-job.py "$$DIR"; \
		fi; \
		git add "$$DIR"; \
		git commit -m "apply: $$COMPANY — $$POSITION"; \
		git push -u origin "$$BRANCH"; \
		printf '## 📄 Application\n\n| Field | Value |\n|-------|-------|\n| **Company** | %s |\n| **Position** | %s |\n| **Branch** | `%s` |\n| **Job URL** | %s |\n\n## ✅ Checklist\n\n- [ ] Tailor: `make tailor NAME=%s` _(+ optionally `AI=claude|openai|mistral|ollama`)_\n- [ ] Build + page check: `make app NAME=%s` _(CV ≤ 2p / CL ≤ 1p)_\n- [ ] Full review: `make review NAME=%s`\n- [ ] Mark PR as ready: `gh pr ready`\n' \
			"$$COMPANY" "$$POSITION" "$$BRANCH" "$$URL" \
			"$$DATE-$$SLUG" "$$DATE-$$SLUG" "$$DATE-$$SLUG" > /tmp/cv-pr-body.md; \
		gh pr create --draft \
			--title "📄 $$COMPANY — $$POSITION" \
			--body-file /tmp/cv-pr-body.md; \
		echo ""; \
		echo "✅ Application created!"; \
		echo "   📁 $$DIR/"; \
		echo "   🔀 Branch: $$BRANCH"; \
		echo "   📝 Draft PR created on GitHub"; \
		echo ""; \
		echo "👉 Next steps:"; \
		echo "   1. Tailor:  make tailor NAME=$$DATE-$$SLUG [AI=gemini|claude|openai|mistral|ollama]"; \
		echo "   2. Build:   make app NAME=$$DATE-$$SLUG"; \
		echo "   3. Review:  make review NAME=$$DATE-$$SLUG"; \
		echo "   4. Ready:   gh pr ready"; \
	}

# Tailor CV and/or cover letter with AI (default: Gemini)
# Runs ATS score before and after tailoring to show improvement
# Usage: make tailor NAME=2026-02-snowflake [AI=gemini|claude|openai|mistral|ollama] [TARGET=cl|cv|both] [MODEL=...]
# TARGET: cl (default) = cover letter only, cv = CV only, both = CV + cover letter
# MODEL: optional model override (e.g. MODEL=claude-opus-4-6, MODEL=gemini-2.0-flash)
# Requires: API key env var for the chosen provider (see .env.example)
TARGET ?= cl
MODEL ?=
tailor:
	@test -n "$(NAME)" || (echo "Usage: make tailor NAME=2026-02-snowflake" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@case "$(TARGET)" in cv|cl|both) ;; *) echo "❌ TARGET must be cv, cl, or both" && exit 1 ;; esac
	@case "$(AI)" in \
		gemini)  test -n "$(GEMINI_API_KEY)"    || (echo "❌ Set GEMINI_API_KEY (https://aistudio.google.com/apikey)"    && exit 1) ;; \
		claude)  test -n "$(ANTHROPIC_API_KEY)" || (echo "❌ Set ANTHROPIC_API_KEY (https://console.anthropic.com/)"     && exit 1) ;; \
		openai)  test -n "$(OPENAI_API_KEY)"    || (echo "❌ Set OPENAI_API_KEY (https://platform.openai.com/api-keys)"  && exit 1) ;; \
		mistral) test -n "$(MISTRAL_API_KEY)"   || (echo "❌ Set MISTRAL_API_KEY (https://console.mistral.ai/)"          && exit 1) ;; \
		ollama)  ;; \
		*)       echo "❌ Unknown AI provider: $(AI). Valid: gemini claude openai mistral ollama" && exit 1 ;; \
	esac
	@if [ -f "applications/$(NAME)/job.txt" ]; then \
		echo "📊 Pre-tailoring ATS score:"; \
		$(PYTHON) scripts/ats-score.py "applications/$(NAME)" --json > /tmp/ats-before.json 2>/dev/null; \
		$(PYTHON) -c "import json; d=json.load(open('/tmp/ats-before.json')); print(f\"   Score: {d['score']:.0f}%\"); print(f\"   Missing: {', '.join(m['keyword'] for m in d['missing'][:15])}\")" 2>/dev/null || true; \
		echo ""; \
		echo "═══════════════════════════════════════════════════════════════"; \
	fi
	@TAILOR_FLAGS="--auto-trim"; \
	case "$(TARGET)" in \
		cv)  TAILOR_FLAGS="$$TAILOR_FLAGS --cv-only" ;; \
		cl)  TAILOR_FLAGS="$$TAILOR_FLAGS --cl-only" ;; \
	esac; \
	if [ -n "$(MODEL)" ]; then TAILOR_FLAGS="$$TAILOR_FLAGS --model $(MODEL)"; fi; \
	$(PYTHON) scripts/ai-tailor.py "applications/$(NAME)" --provider "$(AI)" $$TAILOR_FLAGS
	@# Render tailored YAML → LaTeX
	@if [ "$(TARGET)" != "cl" ] && [ -f "applications/$(NAME)/cv-tailored.yml" ]; then \
		echo ""; \
		echo "🔧 Rendering tailored CV..."; \
		CV_TEX=$$(ls "applications/$(NAME)/CV "*.tex 2>/dev/null | head -1); \
		if [ -n "$$CV_TEX" ]; then \
			$(PYTHON) scripts/render.py -d "applications/$(NAME)/cv-tailored.yml" -o "$$CV_TEX"; \
		fi; \
	fi
	@if [ "$(TARGET)" != "cv" ] && [ -f "applications/$(NAME)/coverletter.yml" ]; then \
		echo "🔧 Rendering cover letter..."; \
		CL_TEX=$$(ls "applications/$(NAME)/CoverLetter "*.tex 2>/dev/null | head -1); \
		if [ -n "$$CL_TEX" ]; then \
			CV_DATA=$$([ "$(TARGET)" = "both" ] && [ -f "applications/$(NAME)/cv-tailored.yml" ] && echo "applications/$(NAME)/cv-tailored.yml" || echo "data/cv.yml"); \
			$(PYTHON) scripts/render.py -d "applications/$(NAME)/coverletter.yml" -o "$$CL_TEX" --cv-data "$$CV_DATA"; \
		fi; \
	fi
	@if [ -f "applications/$(NAME)/job.txt" ] && [ -f /tmp/ats-before.json ]; then \
		echo ""; \
		echo "═══════════════════════════════════════════════════════════════"; \
		echo "📊 Post-tailoring ATS score:"; \
		$(PYTHON) scripts/ats-score.py "applications/$(NAME)" --json > /tmp/ats-after.json 2>/dev/null; \
		$(PYTHON) -c "\
import json; \
b=json.load(open('/tmp/ats-before.json'))['score']; \
a=json.load(open('/tmp/ats-after.json'))['score']; \
d=a-b; sign='+' if d>0 else ''; \
print(f'   Score: {a:.0f}% ({sign}{d:.0f}%)')" 2>/dev/null || true; \
		rm -f /tmp/ats-before.json /tmp/ats-after.json; \
	fi
	@echo ""
	@git add "applications/$(NAME)/" && \
		git diff --cached --quiet || \
		(git commit -m "tailor: $(NAME)" && git push)

# Full pipeline: AI tailor → review (render + compile + validate + ATS score)
# NAME is auto-detected from the current apply/* branch when not provided.
# Usage: make pipeline [NAME=2026-02-company] [AI=gemini] [TARGET=cl]
pipeline:
	@test -n "$(NAME)" || (echo "Usage: make pipeline [NAME=2026-02-company] [AI=gemini]" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@echo "╔═══════════════════════════════════════════════════════════════╗"
	@printf "║  Pipeline: %-51s║\n" "$(NAME)"
	@echo "╚═══════════════════════════════════════════════════════════════╝"
	@echo ""
	@if [ ! -f "applications/$(NAME)/job.txt" ]; then \
		echo "⚠️  No job.txt — ATS scoring will be skipped"; \
		echo "   Tip: make fetch NAME=$(NAME)  to download the job description first"; \
		echo ""; \
	fi
	@echo "━━━ 1/2  Tailor ($(AI)) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@$(MAKE) --no-print-directory tailor NAME=$(NAME) AI=$(AI) $(if $(MODEL),MODEL=$(MODEL)) TARGET=$(TARGET)
	@echo ""
	@echo "━━━ 2/2  Review ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@$(MAKE) --no-print-directory review NAME=$(NAME)
	@echo ""
	@echo "✅ Pipeline complete — applications/$(NAME)"
	@echo "   Next: make open NAME=$(NAME)"

# Render CV.tex + CoverLetter.tex from YAML source of truth
# Usage: make render  /  make render LANG=fr  /  make render PDFA=true  /  make render DRAFT=true
render:
	@ARGS="-d data/cv.yml -o CV.tex"; \
	if [ -n "$(LANG)" ]; then ARGS="$$ARGS -l $(LANG)"; fi; \
	if [ "$(PDFA)" = "true" ]; then ARGS="$$ARGS --pdfa"; fi; \
	if [ "$(DRAFT)" = "true" ]; then ARGS="$$ARGS --draft"; fi; \
	$(PYTHON) scripts/render.py $$ARGS
	@CL_FILE="data/coverletter.yml"; \
	if [ -n "$(LANG)" ]; then CL_FILE="data/coverletter-$(LANG).yml"; fi; \
	if [ -f "$$CL_FILE" ]; then \
		ARGS="-d data/coverletter.yml -o CoverLetter.tex"; \
		if [ -n "$(LANG)" ]; then ARGS="$$ARGS -l $(LANG)"; fi; \
		if [ "$(PDFA)" = "true" ]; then ARGS="$$ARGS --pdfa"; fi; \
		if [ "$(DRAFT)" = "true" ]; then ARGS="$$ARGS --draft"; fi; \
		$(PYTHON) scripts/render.py $$ARGS; \
	fi
	@echo "👉 Next: make (to compile PDFs)"

# ATS keyword score for an application
# Usage: make score NAME=2026-02-databricks
# Requires: job.txt in the application directory
score:
	@test -n "$(NAME)" || (echo "Usage: make score NAME=2026-02-databricks" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/ats-score.py "applications/$(NAME)" || true

# Quick application overview: stage, days since creation, ATS score, provider
status:              ## Quick overview of all applications
	@$(PYTHON) scripts/status.py

# Active applications only (applied/interview/offer — skip rejected/ghosted)
status-active:       ## Active applications only (no rejected/ghosted)
	@$(PYTHON) scripts/status.py --active

# LaTeX lint check
# Usage: make lint  or  make lint NAME=2026-02-databricks
lint:
	@if [ -n "$(NAME)" ]; then \
		echo "🔍 Linting applications/$(NAME)/"; \
		for f in "applications/$(NAME)/"*.tex; do \
			[ -f "$$f" ] || continue; \
			echo "  $$f:"; \
			chktex -q -n1 -n2 -n8 -n24 -n36 -n44 "$$f" 2>&1 || true; \
		done; \
	else \
		echo "🔍 Linting all .tex files"; \
		for f in CV.tex CoverLetter.tex; do \
			echo "  $$f:"; \
			chktex -q -n1 -n2 -n8 -n24 -n36 -n44 "$$f" 2>&1 || true; \
		done; \
		for f in applications/*/*.tex; do \
			[ -f "$$f" ] || continue; \
			echo "  $$f:"; \
			chktex -q -n1 -n2 -n8 -n24 -n36 -n44 "$$f" 2>&1 || true; \
		done; \
	fi
	@echo "✅ Lint complete"

# Diff between master CV and tailored application CV
# Usage: make diff NAME=2026-02-databricks
diff:
	@test -n "$(NAME)" || (echo "Usage: make diff NAME=2026-02-databricks" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@CV_FILE=$$(ls "applications/$(NAME)/CV "*.tex 2>/dev/null | head -1); \
	if [ -z "$$CV_FILE" ]; then \
		echo "❌ No CV .tex file found in applications/$(NAME)/"; \
		exit 1; \
	fi; \
	echo "📊 Diff: CV.tex ↔ $$CV_FILE"; \
	echo ""; \
	diff --color=always -u CV.tex "$$CV_FILE" || true; \
	echo ""; \
	CL_FILE=$$(ls "applications/$(NAME)/CoverLetter "*.tex 2>/dev/null | head -1); \
	if [ -n "$$CL_FILE" ]; then \
		echo "📊 Diff: CoverLetter.tex ↔ $$CL_FILE"; \
		echo ""; \
		diff --color=always -u CoverLetter.tex "$$CL_FILE" || true; \
	fi

# Aggregate keyword gap analysis: cv.yml vs all job.txt files (no AI)
# Usage: make cv-keywords [MIN=2] [CV=app-name]
cv-keywords:
	@$(PYTHON) scripts/cv-keywords.py \
		$(if $(MIN),--min-count "$(MIN)") \
		$(if $(CV),--cv "$(CV)")

# AI blind spot analysis — gaps and silent objections the panel has about you
# Usage: make blind-spots NAME=2026-02-databricks [AI=gemini]
blind-spots:
	@test -n "$(NAME)" || (echo "Usage: make blind-spots NAME=2026-02-company" && exit 1)
	@$(PYTHON) scripts/blind-spots.py "applications/$(NAME)" \
		$(if $(AI),--ai "$(AI)")

# Generate interview-day brief (company snapshot, talking points, STAR stories, questions) (AI)
# Usage: make interview-brief NAME=2026-02-databricks [STAGE=phone-screen|technical|panel|final] [AI=gemini]
interview-brief:
	@test -n "$(NAME)" || (echo "Usage: make interview-brief NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/interview-brief.py "applications/$(NAME)" \
		$(if $(STAGE),--stage "$(STAGE)") \
		$(if $(AI),--ai "$(AI)")

# Generate structured STAR stories from CV achievements (AI)
# Usage: make prep-star NAME=2026-02-databricks [COUNT=5] [AI=gemini]
prep-star:
	@test -n "$(NAME)" || (echo "Usage: make prep-star NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/prep-star.py "applications/$(NAME)" \
		$(if $(COUNT),--count "$(COUNT)") \
		$(if $(AI),--ai "$(AI)")

# Post-interview AI debrief (what went well, improvements, next steps)
# Usage: make interview-debrief NAME=2026-02-databricks [STAGE=technical] [NOTES="..."] [AI=gemini]
interview-debrief:
	@test -n "$(NAME)" || (echo "Usage: make interview-debrief NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/interview-debrief.py "applications/$(NAME)" \
		$(if $(STAGE),--stage "$(STAGE)") \
		$(if $(NOTES),--notes "$(NOTES)") \
		$(if $(AI),--ai "$(AI)")

# Generate a LinkedIn post (open-to-work / transition / achievement / insight) (AI)
# Usage: make linkedin-post [NAME=...] [TYPE=open-to-work|transition|achievement|insight] [TOPIC="..."] [AI=gemini]
linkedin-post:
	@$(PYTHON) scripts/linkedin-post.py \
		$(if $(NAME),"applications/$(NAME)") \
		$(if $(TYPE),--type "$(TYPE)") \
		$(if $(TOPIC),--topic "$(TOPIC)") \
		$(if $(AI),--ai "$(AI)")

# Export all application data to CSV (for Excel / Notion / Airtable)
# Usage: make export-csv [OUTPUT=path.csv] [NO_ATS=true]
export-csv:
	@$(PYTHON) scripts/export-csv.py \
		$(if $(OUTPUT),--output "$(OUTPUT)") \
		$(if $(filter true,$(NO_ATS)),--no-ats) \
		$(if $(filter true,$(JSON)),--json)

# Generate elevator pitches (30s / 60s / 90s) using AI
# Usage: make elevator-pitch [NAME=2026-02-databricks] [CONTEXT=recruiter|networking|interview|cold-call] [AI=gemini]
elevator-pitch:
	@$(PYTHON) scripts/elevator-pitch.py \
		$(if $(NAME),"applications/$(NAME)") \
		$(if $(CONTEXT),--context "$(CONTEXT)") \
		$(if $(AI),--ai "$(AI)")

# Generate 30/60/90-day onboarding plan using AI
# Usage: make onboarding-plan NAME=2026-02-databricks [AI=gemini]
onboarding-plan:
	@test -n "$(NAME)" || (echo "Usage: make onboarding-plan NAME=2026-02-company" && exit 1)
	@$(PYTHON) scripts/onboarding-plan.py "applications/$(NAME)" \
		$(if $(AI),--ai "$(AI)")

# AI cover letter critique vs job description (score + rewrite suggestions)
# Usage: make cover-critique NAME=2026-02-databricks [AI=gemini]
cover-critique:
	@test -n "$(NAME)" || (echo "Usage: make cover-critique NAME=2026-02-company" && exit 1)
	@$(PYTHON) scripts/cover-critique.py "applications/$(NAME)" \
		$(if $(AI),--ai "$(AI)")

# Interactive AI interview simulator (Q&A + evaluation)
# Usage: make interview-sim NAME=2026-02-databricks [ROUNDS=5] [TYPE=behavioral|technical|mixed|pressure] [AI=gemini]
interview-sim:
	@test -n "$(NAME)" || (echo "Usage: make interview-sim NAME=2026-02-company" && exit 1)
	@$(PYTHON) scripts/interview-sim.py "applications/$(NAME)" \
		$(if $(ROUNDS),--rounds "$(ROUNDS)") \
		$(if $(TYPE),--type "$(TYPE)") \
		$(if $(AI),--ai "$(AI)")

# Enhanced archive with summary, git tag, and ARCHIVE.md report
# Usage: make archive-app NAME=2026-02-databricks [OUTCOME=rejected|offer|ghosted] [NO_COMMIT=true]
archive-app:
	@test -n "$(NAME)" || (echo "Usage: make archive-app NAME=2026-02-company [OUTCOME=...]" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/archive-app.py "applications/$(NAME)" \
		$(if $(OUTCOME),--outcome "$(OUTCOME)") \
		$(if $(filter true,$(NO_COMMIT)),--no-commit) \
		$(if $(filter true,$(NO_TAG)),--no-tag)

# Archive a completed application
# Usage: make archive NAME=2026-02-databricks
archive:
	@test -n "$(NAME)" || (echo "Usage: make archive NAME=2026-02-databricks" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@mkdir -p archive
	@mv "applications/$(NAME)" "archive/$(NAME)"
	@echo "📦 Archived: applications/$(NAME) → archive/$(NAME)"
	@BRANCH="apply/$(NAME)"; \
	if git show-ref --quiet "refs/heads/$$BRANCH" 2>/dev/null; then \
		echo "🔀 Deleting local branch $$BRANCH"; \
		git branch -d "$$BRANCH" 2>/dev/null || true; \
	fi; \
	if git ls-remote --heads origin "$$BRANCH" 2>/dev/null | grep -q "$$BRANCH"; then \
		echo "🔀 Deleting remote branch $$BRANCH"; \
		git push origin --delete "$$BRANCH" 2>/dev/null || true; \
	fi
	@echo "✅ Archive complete"

# Export CV data to other formats
# Usage: make export FORMAT=json  (or: markdown, text)
export:
	@test -n "$(FORMAT)" || (echo "Usage: make export FORMAT=json  (json, markdown, text)" && exit 1)
	@$(PYTHON) scripts/export.py "$(FORMAT)" -d data/cv.yml

# Convert CV to DOCX using Pandoc
# Usage: make docx  or  make docx NAME=2026-02-databricks
docx:
	@if [ -n "$(NAME)" ]; then \
		CV_FILE=$$(ls "applications/$(NAME)/CV "*.tex 2>/dev/null | head -1); \
		OUTPUT="applications/$(NAME)/CV - $(NAME).docx"; \
		if [ -z "$$CV_FILE" ]; then \
			echo "❌ No CV .tex file found in applications/$(NAME)/"; \
			exit 1; \
		fi; \
		echo "📄 Converting $$CV_FILE to DOCX..."; \
		pandoc "$$CV_FILE" -o "$$OUTPUT" --wrap=none; \
		echo "✅ Created: $$OUTPUT"; \
	else \
		echo "📄 Converting CV.tex to CV.docx..."; \
		pandoc CV.tex -o CV.docx --wrap=none; \
		echo "✅ Created: CV.docx"; \
	fi

# Compare two tailored application CVs
# Usage: make compare NAME1=2026-02-databricks NAME2=2026-02-snowflake
compare:
	@test -n "$(NAME1)" || (echo "Usage: make compare NAME1=2026-02-databricks NAME2=2026-02-snowflake" && exit 1)
	@test -n "$(NAME2)" || (echo "Usage: make compare NAME1=2026-02-databricks NAME2=2026-02-snowflake" && exit 1)
	@test -d "applications/$(NAME1)" || (echo "Directory applications/$(NAME1) not found" && exit 1)
	@test -d "applications/$(NAME2)" || (echo "Directory applications/$(NAME2) not found" && exit 1)
	@CV1=$$(ls "applications/$(NAME1)/CV "*.tex 2>/dev/null | head -1); \
	CV2=$$(ls "applications/$(NAME2)/CV "*.tex 2>/dev/null | head -1); \
	if [ -z "$$CV1" ] || [ -z "$$CV2" ]; then \
		echo "❌ CV .tex file not found in one of the directories"; \
		exit 1; \
	fi; \
	echo "📊 Compare CVs: $(NAME1) ↔ $(NAME2)"; \
	echo "   $$CV1"; \
	echo "   $$CV2"; \
	echo ""; \
	diff --color=always -u "$$CV1" "$$CV2" || true; \
	echo ""; \
	CL1=$$(ls "applications/$(NAME1)/CoverLetter "*.tex 2>/dev/null | head -1); \
	CL2=$$(ls "applications/$(NAME2)/CoverLetter "*.tex 2>/dev/null | head -1); \
	if [ -n "$$CL1" ] && [ -n "$$CL2" ]; then \
		echo "📊 Compare Cover Letters: $(NAME1) ↔ $(NAME2)"; \
		echo ""; \
		diff --color=always -u "$$CL1" "$$CL2" || true; \
	fi

# LinkedIn sync — dry-run by default, set LINKEDIN_PUSH=true in .env to push
# Usage: make linkedin  or  make linkedin PUSH=true
linkedin:
	@if [ "$(PUSH)" = "true" ]; then \
		$(PYTHON) scripts/linkedin-sync.py -d data/cv.yml --push; \
	else \
		$(PYTHON) scripts/linkedin-sync.py -d data/cv.yml; \
	fi

# Install git hooks (pre-commit: lint + placeholder check)
hooks:
	@bash scripts/install-hooks.sh

# Run all validations for an application
# Usage: make check NAME=2026-02-databricks
check:
	@echo "🔍 Running all validations..."
	@echo ""
	@echo "📋 YAML schema validation..."
	@$(PYTHON) -c "\
import json, yaml, sys; \
schema=json.load(open('data/cv-schema.json')); \
data=yaml.safe_load(open('data/cv.yml')); \
missing=[k for k in schema.get('required',[]) if k not in data]; \
print('✅ YAML valid' if not missing else f'❌ Missing keys: {missing}'); \
sys.exit(1 if missing else 0)" || exit 1
	@echo ""
	@if [ -n "$(NAME)" ]; then \
		echo "📋 Application: $(NAME)"; \
		echo ""; \
		$(MAKE) --no-print-directory lint NAME=$(NAME); \
		echo ""; \
		echo "🔍 Placeholder check..."; \
		if grep -rn '\[Company\]\|\[Position Title\]\|Hiring Manager\|Company Name' "applications/$(NAME)/"*.tex 2>/dev/null; then \
			echo "⚠️  Placeholders found — customize the templates"; \
		else \
			echo "✅ No placeholders found"; \
		fi; \
		echo ""; \
		if [ -f "applications/$(NAME)/job.txt" ]; then \
			$(MAKE) --no-print-directory score NAME=$(NAME); \
		else \
			echo "⚠️  No job.txt — skipping ATS score"; \
		fi; \
	else \
		$(MAKE) --no-print-directory lint; \
	fi
	@echo ""
	@echo "✅ All checks complete"

# Generate application report
# Usage: make report  or  make report FORMAT=markdown
report:
	@$(PYTHON) scripts/report.py $(if $(FORMAT),--format $(FORMAT))

# Fetch job description from URL
# Usage: make fetch NAME=2026-02-databricks
fetch:
	@test -n "$(NAME)" || (echo "Usage: make fetch NAME=2026-02-databricks" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/fetch-job.py "applications/$(NAME)"

# Generate interview preparation notes
# Usage: make prep NAME=2026-02-databricks
prep:
	@test -n "$(NAME)" || (echo "Usage: make prep NAME=2026-02-databricks" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/interview-prep.py "applications/$(NAME)"

# Generate CV changelog across applications
# Usage: make changelog  or  make changelog FORMAT=markdown
changelog:
	@$(PYTHON) scripts/changelog.py $(if $(filter markdown,$(FORMAT)),--markdown)

# Skills gap analysis across all job postings
# Usage: make skills
skills:
	@$(PYTHON) scripts/skills-gap.py

# PDF visual regression — compare master vs application PDF
# Usage: make visual-diff NAME=2026-02-databricks
# Requires: ImageMagick (brew install imagemagick)
visual-diff:
	@test -n "$(NAME)" || (echo "Usage: make visual-diff NAME=2026-02-databricks" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/visual-diff.py "applications/$(NAME)"

# Application statistics and metrics
# Usage: make stats
stats:
	@$(PYTHON) scripts/stats.py

clean:
	rm -f *.pdf *.aux *.log *.out
	rm -rf .visual-diff
	rm -f applications/*/*.pdf applications/*/*.aux applications/*/*.log applications/*/*.out
	rm -f applications/*/*-suggestions.tex

# Check all dependencies
doctor:
	@$(PYTHON) scripts/doctor.py

# Generate Mermaid Gantt chart of applications
timeline:
	@$(PYTHON) scripts/timeline.py

# Analyze CV section lengths vs 2-page constraint
length:
	@$(PYTHON) scripts/length-optimizer.py

# Reverse ATS - Score master CV against job without creating application
# Usage: make match SOURCE="job.txt"  or  make match SOURCE=https://...
match:
	@$(PYTHON) scripts/match.py "$(SOURCE)"

# Generate follow-up email templates
# Usage: make follow-up              (all stale applications > 14 days)
#        make follow-up NAME=...     (specific application → applications/NAME/followup.md)
#        make follow-up DAYS=7       (lower threshold)
follow-up followup:
	@if [ -n "$(NAME)" ]; then \
		$(PYTHON) scripts/followup.py --name "$(NAME)"; \
	elif [ -n "$(DAYS)" ]; then \
		$(PYTHON) scripts/followup.py --days "$(DAYS)"; \
	else \
		$(PYTHON) scripts/followup.py; \
	fi

# Application effectiveness analysis (outcomes vs ATS scores)
effectiveness:
	@$(PYTHON) scripts/effectiveness.py

# Keyword trend analysis across all job postings
# Usage: make trends [SINCE=2026-01] [TOP=30]
trends:
	@$(PYTHON) scripts/keyword-trends.py $(if $(TOP),--top $(TOP)) $(if $(SINCE),--since $(SINCE))

# Generate thank-you email after interview using AI
# Usage: make thankyou NAME=2026-02-databricks [STAGE=interview] [AI=gemini]
thankyou:
	@test -n "$(NAME)" || (echo "Usage: make thankyou NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/thankyou.py "applications/$(NAME)" $(if $(STAGE),--stage $(STAGE)) --ai "$(AI)"

# Generate negotiation script and counter-offer email using AI
# Usage: make negotiate NAME=2026-02-databricks [OFFER="€120k + 10% bonus"] [AI=gemini]
negotiate:
	@test -n "$(NAME)" || (echo "Usage: make negotiate NAME=2026-02-company [OFFER=\"€120k\"]" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/negotiate.py "applications/$(NAME)" $(if $(OFFER),--offer "$(OFFER)") --ai "$(AI)"

# Update application status across all tracking systems
# Usage: make notify NAME=2026-02-databricks STATUS=interview [MESSAGE="..."]
notify:
	@test -n "$(NAME)" || (echo "Usage: make notify NAME=2026-02-company STATUS=interview|offer|rejected|ghosted" && exit 1)
	@test -n "$(STATUS)" || (echo "❌ STATUS is required. Values: applied interview offer rejected ghosted" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/notify.py "applications/$(NAME)" --status "$(STATUS)" $(if $(MESSAGE),--message "$(MESSAGE)")

# Watch mode — auto-recompile when YAML files change
# Usage: make watch NAME=2026-02-databricks  (watch specific app)
#        make watch                           (watch all applications)
watch:
	@if [ -n "$(NAME)" ]; then \
		test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1); \
		$(PYTHON) scripts/watch.py "applications/$(NAME)"; \
	else \
		$(PYTHON) scripts/watch.py; \
	fi

# Tone consistency check — formality, action verbs, passive voice, filler words
# Usage: make tone NAME=2026-02-databricks
tone:
	@test -n "$(NAME)" || (echo "Usage: make tone NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/tone-check.py "applications/$(NAME)"

# Cover letter ATS-style score
# Usage: make cl-score NAME=2026-02-databricks
cl-score:
	@test -n "$(NAME)" || (echo "Usage: make cl-score NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/cl-score.py "applications/$(NAME)"

# Fetch company intel (description, size, tech stack, news, funding)
# Usage: make research NAME=2026-02-databricks
research:
	@test -n "$(NAME)" || (echo "Usage: make research NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/company-research.py "applications/$(NAME)"

# Discover new job postings from configured sources (data/job-discovery.yml)
# Usage: make discover
discover:
	@$(PYTHON) scripts/job-discovery.py

# Discover jobs + auto-create apply branches for each new match
discover-apply:
	@$(PYTHON) scripts/job-discovery.py --auto-apply

# Apply to multiple jobs from a CSV file (columns: company, position, url)
# Usage: make batch CSV=batch.csv [AI=gemini]
batch:
	@test -n "$(CSV)" || (echo "Usage: make batch CSV=batch.csv [AI=gemini]" && exit 1)
	@test -f "$(CSV)" || (echo "File not found: $(CSV)" && exit 1)
	@$(PYTHON) scripts/batch-apply.py "$(CSV)" --ai "$(AI)"

# Preview batch apply without executing
# Usage: make batch-dry CSV=batch.csv
batch-dry:
	@test -n "$(CSV)" || (echo "Usage: make batch-dry CSV=batch.csv" && exit 1)
	@test -f "$(CSV)" || (echo "File not found: $(CSV)" && exit 1)
	@$(PYTHON) scripts/batch-apply.py "$(CSV)" --dry-run

# Generate HTML dashboard and open in browser
dashboard:
	@$(PYTHON) scripts/generate-dashboard.py --output-dir /tmp/cv-dashboard --no-gh
	@$(OPEN_CMD) /tmp/cv-dashboard/index.html 2>/dev/null || true

# Full application review: render + compile + validate + score
# Usage: make review NAME=2026-02-databricks
review:
	@test -n "$(NAME)" || (echo "Usage: make review NAME=2026-02-databricks" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@echo "🔍 Reviewing: applications/$(NAME)"
	@echo "═══════════════════════════════════════════════════════════════"
	@echo ""
	@# 1. Render from YAML if tailored files exist
	@if [ -f "applications/$(NAME)/cv-tailored.yml" ]; then \
		echo "📄 Rendering tailored CV from YAML..."; \
		CV_TEX=$$(ls "applications/$(NAME)/CV "*.tex 2>/dev/null | head -1); \
		if [ -n "$$CV_TEX" ]; then \
			$(PYTHON) scripts/render.py -d "applications/$(NAME)/cv-tailored.yml" -o "$$CV_TEX"; \
		fi; \
	fi
	@if [ -f "applications/$(NAME)/coverletter.yml" ]; then \
		echo "📨 Rendering cover letter from YAML..."; \
		CL_TEX=$$(ls "applications/$(NAME)/CoverLetter "*.tex 2>/dev/null | head -1); \
		if [ -n "$$CL_TEX" ]; then \
			CV_DATA=$$([ -f "applications/$(NAME)/cv-tailored.yml" ] && echo "applications/$(NAME)/cv-tailored.yml" || echo "data/cv.yml"); \
			$(PYTHON) scripts/render.py -d "applications/$(NAME)/coverletter.yml" -o "$$CL_TEX" --cv-data "$$CV_DATA"; \
		fi; \
	fi
	@echo ""
	@# 2. Compile PDFs
	@echo "🔨 Compiling PDFs..."
	@for f in "applications/$(NAME)/"*.tex; do \
		$(XELATEX) -output-directory="applications/$(NAME)" "$$f" > /dev/null 2>&1 && \
		echo "   ✅ $$(basename $$f .tex).pdf" || \
		echo "   ❌ $$(basename $$f) — compilation failed"; \
	done
	@echo ""
	@# 3. Page count validation
	@echo "📏 Page count:"
	@for f in "applications/$(NAME)/"*.pdf; do \
		[ -f "$$f" ] || continue; \
		PAGES=$$($(PYTHON) -c "import re; d=open('$$f','rb').read(); m=re.search(rb'/Type\s*/Pages\b[^>]*/Count\s+(\d+)',d); print(m.group(1).decode() if m else '?')"); \
		BASENAME=$$(basename "$$f"); \
		if echo "$$BASENAME" | grep -q "^CoverLetter"; then \
			LIMIT=1; \
		else \
			LIMIT=2; \
		fi; \
		if [ "$$PAGES" -le "$$LIMIT" ] 2>/dev/null; then \
			echo "   ✅ $$BASENAME: $$PAGES page(s) (max $$LIMIT)"; \
		else \
			echo "   ❌ $$BASENAME: $$PAGES page(s) (max $$LIMIT)"; \
		fi; \
	done
	@echo ""
	@# 4. Placeholder check
	@echo "🔍 Placeholder check:"
	@if grep -rn '\[Company\]\|\[Position Title\]\|Hiring Manager\|Company Name' "applications/$(NAME)/"*.tex 2>/dev/null; then \
		echo "   ⚠️  Placeholders found — customize the templates"; \
	else \
		echo "   ✅ No placeholders found"; \
	fi
	@echo ""
	@# 5. ATS score
	@if [ -f "applications/$(NAME)/job.txt" ]; then \
		echo "📊 ATS Score:"; \
		$(PYTHON) scripts/ats-score.py "applications/$(NAME)"; \
	else \
		echo "⚠️  No job.txt — skipping ATS score"; \
	fi
	@echo ""
	@echo "═══════════════════════════════════════════════════════════════"
	@echo "✅ Review complete"

# Score how well a job posting matches your personal preferences (data/preferences.yml)
# Usage: make job-fit NAME=2026-02-databricks [JSON=true]
job-fit:
	@test -n "$(NAME)" || (echo "Usage: make job-fit NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/job-fit.py "applications/$(NAME)" $(if $(filter true,$(JSON)),--json)

# Generate personalised LinkedIn outreach message using AI
# Usage: make linkedin-message NAME=2026-02-databricks [TYPE=recruiter|hm|referral] [CONTACT="..."] [AI=gemini]
linkedin-message:
	@test -n "$(NAME)" || (echo "Usage: make linkedin-message NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/linkedin-message.py "applications/$(NAME)" \
		$(if $(TYPE),--type "$(TYPE)") \
		$(if $(CONTACT),--contact "$(CONTACT)") \
		--ai "$(AI)"

# Advanced CV health check (quantification, action verbs, bullet length, completeness)
# Usage: make cv-health [NAME=2026-02-databricks]
cv-health:
	@if [ -n "$(NAME)" ]; then \
		test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1); \
		$(PYTHON) scripts/cv-health.py --name "$(NAME)"; \
	else \
		$(PYTHON) scripts/cv-health.py; \
	fi

# Manage named CV versions (snapshots for different role targets)
# Usage: make cv-versions                         (list)
#        make cv-versions ACTION=save VERSION=vp-se
#        make cv-versions ACTION=activate VERSION=director-sales
#        make cv-versions ACTION=diff VERSION=vp-se
cv-versions:
	@$(PYTHON) scripts/cv-versions.py \
		$(if $(ACTION),$(ACTION)) \
		$(if $(VERSION),"$(VERSION)")

# Log or display interview milestones for an application
# Usage: make milestone NAME=... STAGE=phone-screen [DATE=...] [INTERVIEWER="..."] [NOTES="..."] [OUTCOME=passed]
#        make milestone NAME=...   (show timeline)
#        make milestone            (show all apps with milestones)
milestone:
	@if [ -n "$(NAME)" ]; then \
		test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1); \
		$(PYTHON) scripts/milestone.py "applications/$(NAME)" \
			$(if $(STAGE),--stage "$(STAGE)") \
			$(if $(DATE),--date "$(DATE)") \
			$(if $(INTERVIEWER),--interviewer "$(INTERVIEWER)") \
			$(if $(NOTES),--notes "$(NOTES)") \
			$(if $(OUTCOME),--outcome "$(OUTCOME)"); \
	else \
		$(PYTHON) scripts/milestone.py; \
	fi

# Cron-friendly deadline and stale-application alert (Slack/Discord)
# Usage: make deadline-alert [DAYS=3] [STALE=14] [DRY=true]
deadline-alert:
	@$(PYTHON) scripts/deadline-alert.py \
		$(if $(DAYS),--days "$(DAYS)") \
		$(if $(STALE),--stale "$(STALE)") \
		$(if $(filter true,$(DRY)),--dry-run)

# Generate 3 cover letter variants with different persuasion angles (AI)
# Usage: make cover-angles NAME=2026-02-databricks [ANGLES=business,technical,culture] [AI=gemini]
cover-angles:
	@test -n "$(NAME)" || (echo "Usage: make cover-angles NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/cover-angles.py "applications/$(NAME)" \
		$(if $(ANGLES),--angles "$(ANGLES)") \
		--ai "$(AI)"

# Generate optimised LinkedIn Headline + About + Banner + Experience entry (AI)
# Usage: make linkedin-profile [NAME=2026-02-databricks] [LANG=fr] [AI=gemini]
linkedin-profile:
	@$(PYTHON) scripts/linkedin-profile.py \
		$(if $(NAME),"applications/$(NAME)") \
		$(if $(LANG),--lang "$(LANG)") \
		$(if $(AI),--ai "$(AI)")

# Generate personalised cold recruiter/HM outreach email (AI)
# Usage: make recruiter-email NAME=2026-02-databricks [TYPE=cold|follow-up|post-apply] [CONTACT=name] [AI=gemini]
recruiter-email:
	@test -n "$(NAME)" || (echo "Usage: make recruiter-email NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/recruiter-email.py "applications/$(NAME)" \
		$(if $(TYPE),--type "$(TYPE)") \
		$(if $(CONTACT),--contact "$(CONTACT)") \
		$(if $(AI),--ai "$(AI)")

# Manage professional references + generate reference request emails
# Usage: make references [ACTION=list|add|show|request] [NAME=...] [REF=name]
references:
	@if [ "$(ACTION)" = "add" ]; then \
		$(PYTHON) scripts/references.py add \
			$(if $(RNAME),--name "$(RNAME)") \
			$(if $(TITLE),--title "$(TITLE)") \
			$(if $(COMPANY),--company "$(COMPANY)") \
			$(if $(EMAIL),--email "$(EMAIL)") \
			$(if $(PHONE),--phone "$(PHONE)") \
			$(if $(REL),--relationship "$(REL)"); \
	elif [ "$(ACTION)" = "request" ]; then \
		test -n "$(NAME)" || (echo "Usage: make references ACTION=request NAME=2026-02-company" && exit 1); \
		$(PYTHON) scripts/references.py request "applications/$(NAME)" $(if $(REF),--ref "$(REF)"); \
	elif [ "$(ACTION)" = "show" ]; then \
		$(PYTHON) scripts/references.py show $(if $(REF),"$(REF)"); \
	else \
		$(PYTHON) scripts/references.py list; \
	fi

# Generate network map (Mermaid + table) from contacts.md across all applications
# Usage: make network-map [NAME=2026-02-databricks]
network-map:
	@$(PYTHON) scripts/network-map.py $(if $(NAME),--name "$(NAME)") $(if $(filter true,$(JSON)),--json)

# Terminal flashcard quiz from interview prep notes
# Usage: make prep-quiz [NAME=2026-02-databricks] [CAT=behavioral|technical|company|to-ask]
prep-quiz:
	@$(PYTHON) scripts/prep-quiz.py \
		$(if $(NAME),"applications/$(NAME)") \
		$(if $(CAT),--category "$(CAT)") \
		$(if $(filter true,$(LIST)),--list) \
		$(if $(filter true,$(NO_SHUFFLE)),--no-shuffle)

# Generate competitor landscape map for a target company (AI)
# Usage: make competitor-map NAME=2026-02-databricks [AI=gemini]
competitor-map:
	@test -n "$(NAME)" || (echo "Usage: make competitor-map NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/competitor-map.py "applications/$(NAME)" $(if $(AI),--ai "$(AI)")

# AI-powered salary benchmarking + negotiation strategy
# Usage: make salary-bench NAME=2026-02-databricks [AI=gemini]
salary-bench:
	@test -n "$(NAME)" || (echo "Usage: make salary-bench NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/salary-bench.py "applications/$(NAME)" $(if $(AI),--ai "$(AI)")

# AI-translate tailored CV (+ Cover Letter) to French
# Usage: make cv-fr-tailor NAME=2026-02-databricks [NO_CL=true] [AI=gemini]
cv-fr-tailor:
	@test -n "$(NAME)" || (echo "Usage: make cv-fr-tailor NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/cv-fr-tailor.py "applications/$(NAME)" \
		$(if $(filter true,$(NO_CL)),--no-cl) \
		$(if $(AI),--ai "$(AI)")

# Terminal Kanban board — applications grouped by stage
# Usage: make apply-board [STAGE=applied|phone-screen|interview|final|offer|rejected|ghosted]
apply-board:
	@$(PYTHON) scripts/apply-board.py \
		$(if $(STAGE),--stage "$(STAGE)") \
		$(if $(filter true,$(JSON)),--json)

# Find recruiter/hiring manager contacts for an application
# Usage: make contacts NAME=2026-02-databricks [JSON=true]
contacts:
	@test -n "$(NAME)" || (echo "Usage: make contacts NAME=2026-02-company" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	@$(PYTHON) scripts/contacts.py "applications/$(NAME)" $(if $(filter true,$(JSON)),--json)

# Check if job posting URLs are still live
# Usage: make url-check [NAME=2026-02-databricks]
url-check:
	@$(PYTHON) scripts/url-check.py $(if $(NAME),--name "$(NAME)") $(if $(filter true,$(JSON)),--json)

# Generate weekly pipeline digest (Markdown + Slack/Discord if configured)
# Usage: make digest [NO_SEND=true] [DAYS=14]
digest:
	@$(PYTHON) scripts/digest.py \
		$(if $(filter true,$(NO_SEND)),--no-send) \
		$(if $(DAYS),--days "$(DAYS)")

# Export cv.yml to JSON Resume v1.0.0 format
# Usage: make json-resume [DATA=data/cv.yml] [OUTPUT=cv.json]
json-resume:
	@$(PYTHON) scripts/json-resume.py \
		$(if $(DATA),-d "$(DATA)") \
		$(if $(OUTPUT),-o "$(OUTPUT)")

# Aggregate interview Q&A from all prep.md files into question-bank.md
# Usage: make question-bank [NAME=2026-02-databricks]
question-bank:
	@$(PYTHON) scripts/question-bank.py $(if $(NAME),--name "$(NAME)")

# Rank all applications by ATS score (requires job.txt)
# Usage: make ats-rank [MIN=70]
ats-rank:
	@$(PYTHON) scripts/ats-rank.py $(if $(MIN),--min-score "$(MIN)")

# Export CV (+ Cover Letter) as ATS-safe plain text
# Usage: make ats-text [NAME=2026-02-databricks] [NO_CL=true]
ats-text:
	@if [ -n "$(NAME)" ]; then \
		test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1); \
		$(PYTHON) scripts/ats-text.py "applications/$(NAME)" $(if $(filter true,$(NO_CL)),--no-cl); \
	else \
		$(PYTHON) scripts/ats-text.py $(if $(filter true,$(NO_CL)),--no-cl); \
	fi

# Launch the Textual TUI (Terminal User Interface)
# Usage: make tui
tui:
	@$(PYTHON) scripts/tui.py

# ---------------------------------------------------------------------------
# Shell completions
# ---------------------------------------------------------------------------

# Bash: source scripts/completions.bash  (or add to ~/.bashrc)
completions-bash:
	@echo "# Add to ~/.bashrc:"
	@echo "source $(CURDIR)/scripts/completions.bash"
	@echo ""
	@echo "# Or install to bash-completion dir:"
	@if [ -d /usr/share/bash-completion/completions ]; then \
		cp scripts/completions.bash /usr/share/bash-completion/completions/cv-make; \
		echo "✅ Installed: /usr/share/bash-completion/completions/cv-make"; \
	else \
		echo "ℹ️  No bash-completion dir found — source manually"; \
	fi

# Fish: install to ~/.config/fish/completions/
completions-fish:
	@mkdir -p ~/.config/fish/completions
	@cp scripts/completions.fish ~/.config/fish/completions/cv-make.fish
	@echo "✅ Installed: ~/.config/fish/completions/cv-make.fish"

# PowerShell: print install instructions
completions-ps1:
	@echo "# Add to your PowerShell \$$PROFILE:"
	@echo ". $(CURDIR)/scripts/completions.ps1"
	@echo ""
	@echo "# Or copy to your profile directory:"
	@echo "cp scripts/completions.ps1 \$$HOME/Documents/PowerShell/cv-completions.ps1"

# Nushell: print install instructions
completions-nu:
	@echo "# Add to your config.nu (~/.config/nushell/config.nu):"
	@echo "source $(CURDIR)/scripts/completions.nu"
	@echo ""
	@echo "# Or copy to your nushell config dir:"
	@echo "cp scripts/completions.nu \$$HOME/.config/nushell/cv-completions.nu"

# Run unit tests
test:
	@$(PYTHON) -m pytest tests/ -v --tb=short

# Run tests with coverage + open HTML report
coverage:
	@$(PYTHON) -m pytest tests/ --cov=scripts --cov-report=html --cov-report=term-missing -q
	@echo "📊 HTML report: htmlcov/index.html"
	@open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || true

# Preview all theme variants from a single YAML
preview:
	@echo "Generating theme previews..."
	@for theme in data/themes/*.yml; do \
		name=$$(basename "$$theme" .yml); \
		echo "  Theme: $$name"; \
		$(PYTHON) scripts/render.py -d data/cv.yml -o "CV-$$name.tex" -t "$$theme"; \
		$(XELATEX) -interaction=nonstopmode -output-directory=. "CV-$$name.tex" > /dev/null 2>&1; \
	done
	@echo "Done! Open with: open CV-*.pdf"

# Deep clean: remove all generated files (PDFs, .tex, LaTeX aux)
clean-all: clean
	rm -f *.tex
	rm -f applications/*/*.tex

# One-command dev environment setup
dev-setup:
	@echo "Setting up development environment..."
	@test -d venv || python3 -m venv venv
	@venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt
	@venv/bin/pip install -q mypy ruff types-PyYAML types-requests jsonschema
	@echo "Installing git hooks..."
	@$(PYTHON) scripts/install-hooks.sh 2>/dev/null || true
	@echo ""
	@echo "Done! Activate with: source venv/bin/activate"
	@echo "Run tests:  make test"
	@echo "Run checks: make check"

# Validate all cv*.yml files against the JSON schema
validate-all:
	@$(PYTHON) -c "\
import json, yaml, sys; \
from jsonschema import validate, ValidationError; \
schema = json.load(open('data/cv-schema.json')); \
errors = 0; \
import glob; \
for path in sorted(glob.glob('data/cv*.yml')): \
    try: \
        data = yaml.safe_load(open(path)); \
        validate(instance=data, schema=schema); \
        print(f'  ok {path}'); \
    except ValidationError as e: \
        print(f'  FAIL {path}: {e.message}'); \
        errors += 1; \
    except Exception as e: \
        print(f'  SKIP {path}: {e}'); \
print(); \
print('All valid' if not errors else f'{errors} validation error(s)'); \
sys.exit(1 if errors else 0)"

# Interview probability predictor (logistic regression on historical ATS scores)
# Usage: make predict              — show model summary + all predictions
#        make predict NAME=...     — predict for one application
#        make predict TOP=10       — show top 10 by predicted probability
predict:
	@$(PYTHON) scripts/interview-predictor.py \
		$(if $(NAME),--predict applications/$(NAME),) \
		$(if $(TOP),--top $(TOP),)

# ---------------------------------------------------------------------------
# AI provider intelligence
# ---------------------------------------------------------------------------

# Compare all configured providers on the same job (requires job.txt)
# Usage: make compare-providers NAME=2026-02-acme
#        make compare-providers NAME=... PROVIDERS=gemini,claude
compare-providers:
	@test -n "$(NAME)" || (echo "Usage: make compare-providers NAME=2026-02-acme" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	$(PYTHON) scripts/compare-providers.py "applications/$(NAME)" \
		$(if $(PROVIDERS),--providers $(PROVIDERS),)

# Auto-detect company accent color and create theme file
# Usage: make accent NAME=2026-02-acme
accent:
	@test -n "$(NAME)" || (echo "Usage: make accent NAME=2026-02-acme" && exit 1)
	@test -d "applications/$(NAME)" || (echo "Directory applications/$(NAME) not found" && exit 1)
	$(PYTHON) scripts/accent-color.py "applications/$(NAME)"

# Show AI response cache statistics
cache-stats:
	@$(PYTHON) -c "import sys; sys.path.insert(0, 'scripts'); from lib.cache import cache_stats; s = cache_stats(); print(f'Cache: {s[\"entries\"]} entries, {s[\"size_bytes\"]//1024}KB — {s[\"dir\"]}')"

# Clear expired AI cache entries (older than 7 days)
# Usage: make cache-clear  or  make cache-clear MAX_AGE=86400 (1 day)
cache-clear:
	@$(PYTHON) -c "import sys; sys.path.insert(0, 'scripts'); from lib.cache import cache_clear; n = cache_clear($(if $(MAX_AGE),$(MAX_AGE),604800)); print(f'Cleared {n} expired cache entries')"

# ---------------------------------------------------------------------------
# Application analytics
# ---------------------------------------------------------------------------

# ATS score trend per application (reads ats_history[] from meta.yml)
# Usage: make ats-history [NAME=2026-02-company]
ats-history:
	@cd scripts && $(PYTHON) ats-history.py $(if $(NAME),--app $(NAME),)

# Funnel conversion rates + ATS correlation + provider breakdown
# Usage: make funnel [PROVIDER=gemini]
funnel:
	@cd scripts && $(PYTHON) funnel-analytics.py $(if $(PROVIDER),--provider $(PROVIDER),)

# Combined analytics report (ATS history + funnel)
analytics:
	@echo ""
	@echo "=== ATS Score History ==="
	@cd scripts && $(PYTHON) ats-history.py
	@echo ""
	@echo "=== Funnel Analytics ==="
	@cd scripts && $(PYTHON) funnel-analytics.py

# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

# Notion two-way sync
# Usage: make notion-pull / make notion-push / make notion-diff
notion-pull:
	@cd scripts && $(PYTHON) notion-twoway.py pull

notion-push:
	@cd scripts && $(PYTHON) notion-twoway.py push

notion-diff:
	@cd scripts && $(PYTHON) notion-twoway.py diff

# Job board integration — Greenhouse + Lever public APIs
# Usage: make boards BOARD=greenhouse COMPANY=stripe [KEYWORDS="python,api"] [MIN_SCORE=40] [CREATE=1]
boards:
	@cd scripts && $(PYTHON) job-boards.py \
		--board $(if $(BOARD),$(BOARD),greenhouse) \
		--company $(COMPANY) \
		$(if $(KEYWORDS),--keywords "$(KEYWORDS)",) \
		$(if $(MIN_SCORE),--min-score $(MIN_SCORE),) \
		$(if $(CREATE),--create,)

# Batch job board fetch from data/job-boards.yml
# Usage: make boards-file [CREATE=1]
boards-file:
	@cd scripts && $(PYTHON) job-boards.py \
		$(if $(CREATE),--create,) \
		$(if $(DRY_RUN),--dry-run,)

# CV Pipeline API server (webhook for external integrations / userscript)
# Usage: make cv-api [PORT=8765] [HOST=127.0.0.1]
cv-api:
	@$(PYTHON) scripts/cv-api.py --port $(if $(PORT),$(PORT),8765) --host $(if $(HOST),$(HOST),127.0.0.1)

# ---------------------------------------------------------------------------
# Smart automation
# ---------------------------------------------------------------------------

# Auto-fix common issues: pip install missing modules, init submodule, create .env
doctor-fix:
	@cd scripts && $(PYTHON) doctor.py --fix

# Semantic search across CV bullets and past applications (TF-IDF, no API key)
# Usage: make semantic MODE=bullets QUERY="led cross-functional team"
#        make semantic MODE=jobs NAME=2026-03-company
#        make semantic MODE=keywords QUERY="python kubernetes api"
semantic:
	@cd scripts && $(PYTHON) semantic-search.py \
		$(if $(MODE),$(MODE),bullets) \
		"$(if $(NAME),$(REPO_ROOT)/applications/$(NAME)/job.txt,$(QUERY))"

# Smart follow-up scheduler — flag stale applications, optionally create GitHub Issues
# Usage: make smart-followup           — report only
#        make smart-followup CREATE=1  — create GitHub Issues for new stale apps
#        make smart-followup DRY=1     — dry-run (show issues without creating)
smart-followup:
	@cd scripts && $(PYTHON) smart-followup.py \
		$(if $(CREATE),--create-issues,) \
		$(if $(DRY),--dry-run,) \
		$(if $(DAYS),--threshold $(DAYS),)

# Normalize YAML formatting (consistent key ordering, indentation)
# Usage: make beautify            — beautify data/cv.yml in-place
#        make beautify DRY=1     — show diff without writing
#        make beautify CHECK=1   — exit 1 if file would change (CI)
beautify:
	@$(PYTHON) scripts/yaml-beautify.py \
		$(if $(DRY),--dry-run,) \
		$(if $(CHECK),--check,) \
		$(if $(FILE),$(FILE),data/cv.yml)

# Schema migration — add missing fields to meta.yml / cv.yml
# Usage: make migrate                        — migrate all (cv + apps)
#        make migrate MIGRATE_TARGET=apps    — only meta.yml files
#        make migrate MIGRATE_TARGET=cv      — only data/cv.yml
#        make migrate DRYRUN=1              — dry-run preview
#        make migrate VERBOSE=1             — show per-field details
migrate:
	@$(PYTHON) scripts/schema-migrate.py \
		$(if $(MIGRATE_TARGET),--target $(MIGRATE_TARGET),) \
		$(if $(DRYRUN),--dry-run,) \
		$(if $(VERBOSE),--verbose,)

# ---------------------------------------------------------------------------
# Template Marketplace
# ---------------------------------------------------------------------------

market-list:         ## List available templates from marketplace
	@$(PYTHON) scripts/template-market.py list

market-search:       ## Search templates: make market-search QUERY=...
	@$(PYTHON) scripts/template-market.py search $(QUERY)

market-install:      ## Install a template: make market-install NAME=...
	@$(PYTHON) scripts/template-market.py install $(NAME)

market-installed:    ## List locally installed templates
	@$(PYTHON) scripts/template-market.py installed

# ---------------------------------------------------------------------------
# Portfolio — static HTML from data/cv.yml → portfolio/index.html
# ---------------------------------------------------------------------------

# Generate English portfolio
# Usage: make portfolio
portfolio:
	@mkdir -p portfolio
	@$(PYTHON) scripts/portfolio.py -o portfolio/index.html
	@echo "Portfolio generated: portfolio/index.html"

# Generate French portfolio
# Usage: make portfolio-fr
portfolio-fr:
	@mkdir -p portfolio
	@$(PYTHON) scripts/portfolio.py -o portfolio/index-fr.html --lang fr
	@echo "Portfolio (FR) generated: portfolio/index-fr.html"

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

# Build Docker image
# Usage: make docker-build
#        make docker-build DOCKER_IMAGE=myrepo/cv-pipeline
docker-build:
	docker build -t $(DOCKER_IMAGE):latest .

# Run any make target inside the container
# Usage: make docker-run TARGET=render
#        make docker-run TARGET="app NAME=2026-02-acme"
docker-run:
	@test -n "$(TARGET)" || (echo "Usage: make docker-run TARGET=render" && exit 1)
	docker run --rm \
		-v "$(CURDIR)/data:/cv/data" \
		-v "$(CURDIR)/applications:/cv/applications" \
		--env-file .env \
		$(DOCKER_IMAGE):latest \
		make $(TARGET)

help:
	@echo "📄 CV Build System"
	@echo ""
	@echo "Build:"
	@echo "  make                              Build master CV + Cover Letter PDFs"
	@echo "  make open [NAME=...]              Build + open PDFs in Preview"
	@echo "  make app NAME=...                 Build specific application PDFs"
	@echo "  make render [LANG=fr] [PDFA=true] Render CV.tex from YAML"
	@echo "  make docx [NAME=...]              Convert CV to DOCX (Pandoc)"
	@echo ""
	@echo "Application workflow:"
	@echo "  make new COMPANY=X POSITION=\"Y\"   Scaffold locally (no git)"
	@echo "  make apply URL=...                Full workflow: branch + scaffold + PR (auto-extract company/position)"
	@echo "  make current                      Print current application name (from apply/* branch)"
	@echo "  make pipeline [AI=gemini]         Tailor + review in one step (NAME auto-detected from branch)"
	@echo "  make tailor [NAME=...] [AI=gemini] Tailor with AI — NAME auto-detected from branch"
	@echo "  make fetch NAME=...               Fetch job description from URL"
	@echo "  make archive NAME=...             Archive completed application"
	@echo ""
	@echo "Analysis:"
	@echo "  make cv-keywords [MIN=2] [CV=app] CV keyword gap vs all job postings (no AI)"
	@echo "  make blind-spots NAME=... [AI=]   Silent objections + gaps the panel will notice"
	@echo "  make score NAME=...               ATS keyword score vs job description"
	@echo "  make match SOURCE=...             Reverse ATS (score CV vs job)"
	@echo "  make skills                       Skills gap analysis (all postings)"
	@echo "  make length                       Analyze CV length vs 2 pages"
	@echo ""
	@echo "Reporting:"
	@echo "  make apply-board [STAGE=...]      Kanban board by pipeline stage"
	@echo "  make status                       Quick overview: stage, days, ATS, provider"
	@echo "  make status-active                Active applications only (no rejected/ghosted)"
	@echo "  make stats                        Application statistics & metrics"
	@echo "  make effectiveness                Outcome vs ATS score analysis"
	@echo "  make report [FORMAT=markdown]     Application report + funnel analytics"
	@echo "  make changelog [FORMAT=markdown]  CV diff changelog"
	@echo "  make timeline                     Mermaid Gantt chart"
	@echo ""
	@echo "Quality:"
	@echo "  make lint [NAME=...]              LaTeX lint check (chktex)"
	@echo "  make check [NAME=...]             Run all validations"
	@echo "  make review NAME=...              Full review (render+build+validate+score)"
	@echo "  make diff NAME=...                Diff master vs tailored CV"
	@echo "  make compare NAME1=... NAME2=...  Compare two tailored CVs"
	@echo "  make visual-diff NAME=...         PDF visual regression"
	@echo ""
	@echo "Tone & Style:"
	@echo "  make tone NAME=...                Tone consistency check (formality, action verbs)"
	@echo "  make cl-score NAME=...            Cover letter score vs job description"
	@echo ""
	@echo "Intelligence:"
	@echo "  make compare-providers NAME=... [PROVIDERS=gemini,claude]  Side-by-side AI diff"
	@echo "  make accent NAME=...              Auto-detect company accent color"
	@echo "  make cache-stats                  Show AI response cache size"
	@echo "  make cache-clear [MAX_AGE=]       Clear expired cache entries"
	@echo "  make predict [NAME=...] [TOP=N]   Interview probability (logistic regression)"
	@echo "  make trends [SINCE=YYYY-MM]       Keyword trend analysis across job postings"
	@echo "  make research NAME=...            Company intel (description, stack, news, funding)"
	@echo "  make discover                     Discover new jobs from configured sources"
	@echo "  make discover-apply               Discover + auto-create apply branches"
	@echo "  make contacts NAME=...            Find recruiter/hiring manager contacts"
	@echo "  make url-check [NAME=...]         Check if job posting URLs are still live"
	@echo "  make ats-rank [MIN=70]            Rank all applications by ATS score"
	@echo "  make question-bank [NAME=...]     Aggregate interview Q&A from all prep.md files"
	@echo "  make job-fit NAME=...             Personal fit score (salary, remote, location, industry)"
	@echo ""
	@echo "Analytics:"
	@echo "  make ats-history [NAME=...]       ATS score trend per application"
	@echo "  make funnel [PROVIDER=]           Funnel rates + ATS correlation"
	@echo "  make analytics                    Full analytics report"
	@echo ""
	@echo "Integrations:"
	@echo "  make notion-diff                  Show Notion ↔ local diff"
	@echo "  make notion-pull                  Pull Notion status → meta.yml"
	@echo "  make notion-push                  Push meta.yml → Notion"
	@echo "  make boards BOARD=gh COMPANY=...  Fetch jobs from Greenhouse/Lever"
	@echo "  make boards-file                  Batch fetch from data/job-boards.yml"
	@echo "  make cv-api [PORT=8765]           HTTP API server for external triggers"
	@echo ""
	@echo "Smart Automation:"
	@echo "  make doctor-fix                   Auto-fix common setup issues"
	@echo "  make semantic MODE=bullets QUERY=...  Semantic bullet/job search (TF-IDF)"
	@echo "  make smart-followup [CREATE=1] [DAYS=] Stale app follow-up + GitHub Issues"
	@echo "  make beautify [DRY=1] [CHECK=1]   Normalize YAML formatting"
	@echo "  make migrate [MIGRATE_TARGET=apps|cv] [DRYRUN=1]  Schema migration"
	@echo ""
	@echo "Interview Prep:"
	@echo "  make elevator-pitch [NAME=...] [CONTEXT=recruiter|networking|interview|cold-call] [AI=]"
	@echo "  make interview-sim NAME=... [ROUNDS=5] [TYPE=behavioral|technical|mixed|pressure] [AI=]"
	@echo "  make interview-brief NAME=... [STAGE=] [AI=]  Morning-of brief: snapshot, talking pts, STAR, Q&A"
	@echo "  make prep-star NAME=... [COUNT=5] [AI=]       Generate N STAR stories from CV achievements"
	@echo ""
	@echo "Post-Interview:"
	@echo "  make interview-debrief NAME=... [STAGE=] [NOTES=\"...\"] [AI=]  Post-interview debrief"
	@echo "  make cover-critique NAME=... [AI=]            AI critique of cover letter vs job description"
	@echo "  make onboarding-plan NAME=... [AI=]           30/60/90-day plan once offer accepted"
	@echo "  make linkedin-post [NAME=...] [TYPE=open-to-work|transition|achievement|insight] [TOPIC=\"...\"] [AI=]"
	@echo "  make thankyou NAME=... [STAGE=]   Thank-you email after interview (AI)"
	@echo "  make negotiate NAME=... [OFFER=]  Negotiation script + counter-offer (AI)"
	@echo "  make notify NAME=... STATUS=...   Update status (meta.yml + Slack/Discord/Notion/GitHub)"
	@echo "  make linkedin-message NAME=... [TYPE=recruiter|hm|referral]  LinkedIn cold outreach (AI)"
	@echo "  make cover-angles NAME=... [ANGLES=...] [AI=gemini]   3 CL variants (business/technical/culture)"
	@echo "  make milestone NAME=... [STAGE=...] [OUTCOME=...]     Log interview milestone"
	@echo "  make linkedin-profile [NAME=...] [LANG=fr]  LinkedIn Headline + About + Banner + Experience (AI)"
	@echo "  make recruiter-email NAME=... [TYPE=cold|follow-up|post-apply]  Cold email outreach (AI)"
	@echo "  make salary-bench NAME=... [AI=gemini]               Salary benchmark + negotiation strategy (AI)"
	@echo "  make competitor-map NAME=... [AI=gemini]             Competitor landscape + why-us talking points (AI)"
	@echo "  make cv-fr-tailor NAME=... [NO_CL=true] [AI=gemini]  Translate tailored CV+CL to French (AI)"
	@echo ""
	@echo "Batch & Automation:"
	@echo "  make batch CSV=... [AI=gemini]    Apply to multiple jobs from CSV"
	@echo "  make batch-dry CSV=...            Preview batch apply (dry run)"
	@echo "  make dashboard                    Generate HTML dashboard (open in browser)"
	@echo "  make watch [NAME=...]             Auto-recompile on YAML changes"
	@echo "  make digest [NO_SEND=true]        Weekly pipeline digest (Markdown + Slack/Discord)"
	@echo ""
	@echo "Utilities:"
	@echo "  make follow-up [NAME=...] [DAYS=] Generate follow-up email templates"
	@echo "  make prep NAME=...                Generate interview prep notes"
	@echo "  make export FORMAT=json           Export CV data (json/markdown/text)"
	@echo "  make export-csv [OUTPUT=...] [NO_ATS=true]  Export all applications to CSV"
	@echo "  make json-resume                  Export cv.yml to JSON Resume v1.0.0"
	@echo "  make ats-text [NAME=...]          Export CV (+ Cover Letter) as ATS-safe plain text"
	@echo "  make cv-health [NAME=...]         Advanced CV audit (quantification, verbs, length)"
	@echo "  make cv-versions [ACTION=...] [VERSION=...]  Manage named CV snapshots"
	@echo "  make deadline-alert [DAYS=3]      Cron-friendly deadline + stale alerts (Slack/Discord)"
	@echo "  make references [ACTION=list|add|request] [NAME=...]  Manage professional references"
	@echo "  make network-map [NAME=...]       Network map (Mermaid) from all contacts.md files"
	@echo "  make prep-quiz [NAME=...] [CAT=]  Terminal flashcard quiz from prep.md files"
	@echo "  make apply-board [STAGE=...]      Terminal Kanban board — applications by stage"
	@echo "  make archive-app NAME=... [OUTCOME=...]  Enhanced archive with summary + git tag"
	@echo "  make linkedin [PUSH=true]         LinkedIn sync (dry-run default)"
	@echo "  make tui                          Interactive terminal UI (Textual)"
	@echo "  make doctor                       Check all dependencies + API keys"
	@echo "  make hooks                        Install git pre-commit hooks"
	@echo "  make clean                        Remove generated files"
	@echo "  make clean-all                    Remove all generated files (incl. .tex)"
	@echo "  make preview                      Generate all theme variant PDFs"
	@echo "  make validate-all                 Validate all cv*.yml against schema"
	@echo "  make dev-setup                    One-command env setup (venv + deps)"
	@echo "  make test                         Run unit tests"
	@echo "  make coverage                     Run tests with HTML coverage report"
	@echo ""
	@echo "Template Marketplace:"
	@echo "  make market-list                  List available templates"
	@echo "  make market-search QUERY=...      Search templates"
	@echo "  make market-install NAME=...      Install a template"
	@echo "  make market-installed             List locally installed templates"
	@echo ""
	@echo "Portfolio:"
	@echo "  make portfolio                    Generate static HTML portfolio (EN)"
	@echo "  make portfolio-fr                 Generate static HTML portfolio (FR)"
	@echo ""
	@echo "Shell Completions:"
	@echo "  make completions-bash             Install bash tab-completion"
	@echo "  make completions-fish             Install fish tab-completion"
	@echo "  make completions-ps1              Show PowerShell install instructions"
	@echo "  make completions-nu               Show Nushell install instructions"
	@echo "  (zsh: source scripts/completions.zsh)"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build [DOCKER_IMAGE=...]   Build Docker image (XeLaTeX + Python)"
	@echo "  make docker-run TARGET=render          Run make target inside container"
