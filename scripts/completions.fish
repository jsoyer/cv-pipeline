# Fish completion for CV Makefile
# Install: cp scripts/completions.fish ~/.config/fish/completions/make.fish
# Or source: source scripts/completions.fish

# Helper: list application directories
function __cv_apps
    if test -d applications
        ls -1 applications/ 2>/dev/null
    end
end

# Helper: are we in the CV repo?
function __cv_in_repo
    test -f Makefile; and grep -q "CV Build System" Makefile 2>/dev/null
end

# Disable default file completions for make when in CV repo
complete -c make -n '__cv_in_repo' --no-files

# ── Targets ──────────────────────────────────────────────────────────────────

set -l cv_targets \
    "all\tBuild master CV + Cover Letter" \
    "app\tBuild application PDFs (NAME=...)" \
    "new\tScaffold new application (COMPANY= POSITION=)" \
    "apply\tFull workflow: branch + scaffold + PR" \
    "tailor\tAI tailor (NAME=... AI=gemini|claude|openai|mistral|ollama)" \
    "render\tRender CV.tex from YAML (LANG= PDFA= DRAFT=)" \
    "score\tATS keyword score (NAME=...)" \
    "status\tKanban dashboard of all applications" \
    "pipeline\tTailor + review in one step" \
    "current\tPrint current application name from branch" \
    "lint\tLaTeX lint check (NAME=...)" \
    "diff\tDiff master vs tailored CV (NAME=...)" \
    "compare\tCompare two tailored CVs (NAME1= NAME2=)" \
    "archive\tArchive completed application (NAME=...)" \
    "export\tExport CV data (FORMAT=json|markdown|text)" \
    "linkedin\tLinkedIn profile sync (PUSH=true)" \
    "hooks\tInstall git pre-commit hooks" \
    "check\tRun all validations (NAME=...)" \
    "open\tBuild + open PDFs (NAME=...)" \
    "report\tApplication report (FORMAT=markdown)" \
    "fetch\tFetch job description from URL (NAME=...)" \
    "prep\tInterview prep notes (NAME=...)" \
    "changelog\tCV diff changelog" \
    "skills\tSkills gap analysis across postings" \
    "visual-diff\tPDF visual regression (NAME=...)" \
    "stats\tApplication statistics & metrics" \
    "doctor\tCheck all dependencies + API keys" \
    "effectiveness\tOutcome vs ATS score analysis" \
    "review\tFull review: render+build+validate+score (NAME=...)" \
    "docx\tConvert CV to DOCX (NAME=...)" \
    "timeline\tMermaid Gantt chart" \
    "length\tCV length vs 2-page constraint" \
    "match\tReverse ATS score (SOURCE=...)" \
    "followup\tFollow-up email templates (NAME=...)" \
    "follow-up\tFollow-up alerts (NAME= DAYS=)" \
    "clean\tRemove generated files" \
    "clean-all\tRemove all generated files incl. .tex" \
    "help\tShow all available commands" \
    "tone\tTone check (NAME=...)" \
    "cl-score\tCover letter score (NAME=...)" \
    "research\tCompany intel (NAME=...)" \
    "discover\tDiscover new jobs from sources" \
    "discover-apply\tDiscover + auto-create branches" \
    "batch\tApply to multiple jobs from CSV" \
    "batch-dry\tPreview batch apply (dry run)" \
    "watch\tAuto-recompile on YAML changes (NAME=...)" \
    "digest\tWeekly pipeline digest (NO_SEND=true)" \
    "deadline-alert\tDeadline + stale alerts (DAYS=3)" \
    "notify\tStatus update notifications (NAME= STATUS=)" \
    "contacts\tFind recruiter/HM contacts (NAME=...)" \
    "url-check\tCheck if job URLs are live (NAME=...)" \
    "json-resume\tExport to JSON Resume v1.0.0" \
    "question-bank\tAggregate Q&A from all prep.md" \
    "ats-rank\tRank applications by ATS score (MIN=70)" \
    "ats-text\tExport as ATS-safe plain text (NAME=...)" \
    "job-fit\tFit score: salary, remote, culture (NAME=...)" \
    "linkedin-message\tLinkedIn cold outreach (NAME=...)" \
    "cv-health\tCV audit: verbs, length, repetition (NAME=...)" \
    "cv-versions\tManage named CV snapshots (ACTION=...)" \
    "milestone\tLog interview stage (NAME= STAGE=)" \
    "cover-angles\t3 CL variants: biz/tech/culture (NAME=...)" \
    "recruiter-email\tCold email outreach (NAME=...)" \
    "references\tManage references (ACTION=list|add)" \
    "network-map\tMermaid network map (NAME=...)" \
    "prep-quiz\tTerminal flashcard quiz (NAME= CAT=)" \
    "competitor-map\tCompetitor landscape (NAME=...)" \
    "salary-bench\tSalary benchmark (NAME=...)" \
    "cv-fr-tailor\tTranslate CV+CL to French (NAME=...)" \
    "apply-board\tKanban board by stage (STAGE=...)" \
    "archive-app\tArchive with summary + git tag (NAME=...)" \
    "linkedin-profile\tLinkedIn Headline/About/Exp (NAME=...)" \
    "interview-brief\tMorning-of cheat sheet (NAME=...)" \
    "prep-star\tSTAR stories from CV (NAME= COUNT=5)" \
    "interview-debrief\tPost-interview debrief (NAME=...)" \
    "linkedin-post\tLinkedIn post (TYPE=...)" \
    "export-csv\tExport applications to CSV" \
    "elevator-pitch\t30s/60s/90s pitches (NAME=...)" \
    "onboarding-plan\t30/60/90-day plan (NAME=...)" \
    "cover-critique\tAI critique + rewrite suggestions (NAME=...)" \
    "interview-sim\tInteractive interview simulator (NAME=...)" \
    "cv-keywords\tKeyword gap: CV vs all job postings (MIN=2)" \
    "blind-spots\tSilent objections + gap analysis (NAME=...)" \
    "validate-all\tValidate all cv*.yml against schema" \
    "test\tRun unit tests" \
    "dev-setup\tOne-command env setup (venv + deps)" \
    "preview\tGenerate all theme variant PDFs" \
    "dashboard\tHTML pipeline dashboard (opens browser)" \
    "trends\tKeyword trend analysis (SINCE=YYYY-MM)" \
    "thankyou\tThank-you email after interview (NAME= STAGE=)" \
    "negotiate\tNegotiation script (NAME= OFFER=)" \
    "docker-build\tBuild Docker image (DOCKER_IMAGE=...)" \
    "docker-run\tRun make target in container (TARGET=...)"

for target in $cv_targets
    complete -c make -n '__cv_in_repo; and not __fish_seen_subcommand_from (string split "\t" $target)[1]' \
        -a (string split "\t" $target)[1] \
        -d (string split "\t" $target)[2]
end

# ── Parameter completions ─────────────────────────────────────────────────────

# NAME= → application directories
complete -c make -n '__cv_in_repo' -a '(for d in (__cv_apps); echo "NAME=$d"; end)' -d 'Application directory'

# AI= → providers
complete -c make -n '__cv_in_repo' -a 'AI=gemini' -d 'Gemini (default)'
complete -c make -n '__cv_in_repo' -a 'AI=claude' -d 'Anthropic Claude'
complete -c make -n '__cv_in_repo' -a 'AI=openai' -d 'OpenAI GPT-4'
complete -c make -n '__cv_in_repo' -a 'AI=mistral' -d 'Mistral AI'
complete -c make -n '__cv_in_repo' -a 'AI=ollama' -d 'Ollama (local)'

# FORMAT=
complete -c make -n '__cv_in_repo' -a 'FORMAT=json' -d 'JSON format'
complete -c make -n '__cv_in_repo' -a 'FORMAT=markdown' -d 'Markdown format'
complete -c make -n '__cv_in_repo' -a 'FORMAT=text' -d 'Plain text format'

# LANG=
complete -c make -n '__cv_in_repo' -a 'LANG=fr' -d 'French version'

# Docker
complete -c make -n '__cv_in_repo' -a 'TARGET=render' -d 'Render CV inside container'
complete -c make -n '__cv_in_repo' -a 'TARGET=check' -d 'Check inside container'
