#!/usr/bin/env bash
# Install git hooks for the CV repository.
# Usage: scripts/install-hooks.sh  or  make hooks

set -e

HOOKS_DIR="$(git rev-parse --git-dir)/hooks"

cat > "$HOOKS_DIR/pre-commit" << 'HOOK'
#!/usr/bin/env bash
# Pre-commit hook: lint + placeholder check on staged .tex files

STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep '\.tex$' || true)
[ -z "$STAGED" ] && exit 0

ERRORS=0

# 1. Placeholder check on application files
for f in $STAGED; do
  case "$f" in applications/*)
    for pattern in '\[Company\]' '\[Position Title\]' 'Hiring Manager' 'Company Name'; do
      if grep -q "$pattern" "$f"; then
        echo "❌ $f: contains placeholder '$pattern'"
        ERRORS=1
      fi
    done
    ;;
  esac
done

# 2. LaTeX lint (if chktex is available)
if command -v chktex &>/dev/null; then
  for f in $STAGED; do
    WARNINGS=$(chktex -q -n1 -n2 -n8 -n24 -n36 -n44 "$f" 2>&1 | grep -c "Warning" || true)
    if [ "$WARNINGS" -gt 0 ]; then
      echo "⚠️  $f: $WARNINGS chktex warning(s)"
      chktex -q -n1 -n2 -n8 -n24 -n36 -n44 "$f" 2>&1 | head -5
    fi
  done
fi

if [ "$ERRORS" -ne 0 ]; then
  echo ""
  echo "🚫 Commit blocked — fix placeholders above"
  exit 1
fi

exit 0
HOOK

chmod +x "$HOOKS_DIR/pre-commit"
echo "✅ Git hooks installed"
echo "   📝 pre-commit: lint + placeholder check on .tex files"
