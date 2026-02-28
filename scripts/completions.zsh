# Zsh completion for CV Makefile
# Source this file: source scripts/completions.zsh
# Or add to ~/.zshrc: source /path/to/CV/scripts/completions.zsh

_cv_make() {
  local -a targets
  targets=(
    'all:Build master CV & cover letter'
    'app:Build a specific application (NAME=...)'
    'new:Scaffold a new application (COMPANY=... POSITION=...)'
    'apply:Full workflow: branch + scaffold + PR (COMPANY=... POSITION=... URL=...)'
    'tailor:Tailor with AI provider (NAME=... AI=gemini|claude|openai|mistral|ollama)'
    'render:Render CV.tex from data/cv.yml (LANG=... PDFA=true DRAFT=true)'
    'score:ATS keyword score (NAME=...)'
    'status:Dashboard of all applications'
    'lint:LaTeX lint check (NAME=...)'
    'diff:Diff master vs tailored CV (NAME=...)'
    'compare:Compare two tailored CVs (NAME1=... NAME2=...)'
    'archive:Archive completed application (NAME=...)'
    'export:Export CV data (FORMAT=json/markdown/text)'
    'linkedin:LinkedIn sync (PUSH=true to push)'
    'hooks:Install git pre-commit hooks'
    'check:Run all validations (NAME=...)'
    'open:Build + open PDFs in Preview (NAME=...)'
    'report:Generate application report (FORMAT=markdown)'
    'fetch:Fetch job description from URL (NAME=...)'
    'prep:Generate interview prep notes (NAME=...)'
    'changelog:CV diff changelog'
    'skills:Skills gap analysis across postings'
    'visual-diff:PDF visual regression (NAME=...)'
    'stats:Application statistics and metrics'
    'doctor:Check all dependencies'
    'effectiveness:Outcome vs ATS score analysis'
    'review:Full review: render+build+validate+score (NAME=...)'
    'docx:Convert CV to DOCX (NAME=...)'
    'timeline:Generate Mermaid Gantt chart'
    'length:Analyze CV length vs 2 pages'
    'match:Reverse ATS score (SOURCE=...)'
    'followup:Generate follow-up email templates'
    'clean:Remove generated files'
    'help:Show available commands'
  )

  local -a app_dirs
  if [[ -d applications ]]; then
    app_dirs=(${(f)"$(ls -d applications/*/ 2>/dev/null | xargs -I{} basename {})"})
  fi

  # Complete targets as first argument
  if (( CURRENT == 2 )); then
    _describe 'make targets' targets
    return
  fi

  # Complete NAME= with application directories
  local cur="${words[CURRENT]}"
  if [[ "$cur" == NAME=* ]]; then
    local prefix="NAME="
    local -a completions
    for d in $app_dirs; do
      completions+=("${prefix}${d}")
    done
    compadd -Q -- $completions
    return
  fi

  if [[ "$cur" == NAME1=* ]]; then
    local prefix="NAME1="
    local -a completions
    for d in $app_dirs; do
      completions+=("${prefix}${d}")
    done
    compadd -Q -- $completions
    return
  fi

  if [[ "$cur" == NAME2=* ]]; then
    local prefix="NAME2="
    local -a completions
    for d in $app_dirs; do
      completions+=("${prefix}${d}")
    done
    compadd -Q -- $completions
    return
  fi

  if [[ "$cur" == FORMAT=* ]]; then
    compadd -Q -- "FORMAT=json" "FORMAT=markdown" "FORMAT=text"
    return
  fi

  if [[ "$cur" == LANG=* ]]; then
    local -a langs
    langs=(${(f)"$(ls data/cv-*.yml 2>/dev/null | sed 's|data/cv-||;s|\.yml||')"})
    local -a completions
    for l in $langs; do
      completions+=("LANG=${l}")
    done
    compadd -Q -- $completions
    return
  fi

  # Complete AI= with provider names
  if [[ "$cur" == AI=* ]]; then
    compadd -Q -- "AI=gemini" "AI=claude" "AI=openai" "AI=mistral" "AI=ollama"
    return
  fi

  # Suggest common parameter names based on target
  local target="${words[2]}"
  case "$target" in
    app|score|lint|diff|archive|check|fetch|prep|open|visual-diff|review)
      compadd -S '' -- "NAME="
      ;;
    tailor)
      compadd -S '' -- "NAME=" "AI="
      ;;
    compare)
      compadd -S '' -- "NAME1=" "NAME2="
      ;;
    export|report)
      compadd -S '' -- "FORMAT="
      ;;
    render)
      compadd -S '' -- "LANG=" "PDFA=" "DRAFT="
      ;;
    apply|new)
      compadd -S '' -- "COMPANY=" "POSITION=" "URL="
      ;;
    linkedin)
      compadd -S '' -- "PUSH="
      ;;
  esac
}

# Only activate when in the CV directory or subdirectories
compdef _cv_make make
