# Nushell completion for CV Makefile
# Install: Add to your config.nu:
#   source /path/to/CV/scripts/completions.nu
# Or source in current session:
#   source scripts/completions.nu

# Helper: list application directories
def cv-apps [] {
    if ("applications" | path exists) {
        ls applications/ | where type == dir | get name | path basename
    } else {
        []
    }
}

# Helper: list AI providers
def cv-providers [] {
    ["gemini", "claude", "openai", "mistral", "ollama"]
}

# Helper: list export formats
def cv-formats [] {
    ["json", "markdown", "text"]
}

# Helper: list LANG values
def cv-langs [] {
    if ("data" | path exists) {
        ls data/cv-*.yml | get name | path basename | str replace "cv-" "" | str replace ".yml" ""
    } else {
        ["fr"]
    }
}

# All make targets with descriptions
def cv-targets [] {
    [
        {value: "all",               description: "Build master CV + Cover Letter"},
        {value: "app",               description: "Build application PDFs (NAME=...)"},
        {value: "new",               description: "Scaffold new application (COMPANY= POSITION=)"},
        {value: "apply",             description: "Full workflow: branch + scaffold + PR"},
        {value: "tailor",            description: "AI tailor (NAME=... AI=gemini|claude|openai|mistral|ollama)"},
        {value: "render",            description: "Render CV.tex from YAML (LANG= PDFA= DRAFT=)"},
        {value: "score",             description: "ATS keyword score (NAME=...)"},
        {value: "status",            description: "Kanban dashboard of all applications"},
        {value: "pipeline",          description: "Tailor + review in one step (NAME= AI=)"},
        {value: "current",           description: "Print current application name from branch"},
        {value: "lint",              description: "LaTeX lint check (NAME=...)"},
        {value: "diff",              description: "Diff master vs tailored CV (NAME=...)"},
        {value: "compare",           description: "Compare two tailored CVs (NAME1= NAME2=)"},
        {value: "archive",           description: "Archive completed application (NAME=...)"},
        {value: "export",            description: "Export CV data (FORMAT=json|markdown|text)"},
        {value: "linkedin",          description: "LinkedIn profile sync (PUSH=true)"},
        {value: "hooks",             description: "Install git pre-commit hooks"},
        {value: "check",             description: "Run all validations (NAME=...)"},
        {value: "open",              description: "Build + open PDFs (NAME=...)"},
        {value: "report",            description: "Application report (FORMAT=markdown)"},
        {value: "fetch",             description: "Fetch job description from URL (NAME=...)"},
        {value: "prep",              description: "Interview prep notes (NAME=...)"},
        {value: "changelog",         description: "CV diff changelog"},
        {value: "skills",            description: "Skills gap analysis across postings"},
        {value: "visual-diff",       description: "PDF visual regression (NAME=...)"},
        {value: "stats",             description: "Application statistics & metrics"},
        {value: "doctor",            description: "Check all dependencies + API keys"},
        {value: "effectiveness",     description: "Outcome vs ATS score analysis"},
        {value: "review",            description: "Full review: render+build+validate+score (NAME=...)"},
        {value: "docx",              description: "Convert CV to DOCX (NAME=...)"},
        {value: "timeline",          description: "Mermaid Gantt chart"},
        {value: "length",            description: "CV length vs 2-page constraint"},
        {value: "match",             description: "Reverse ATS score (SOURCE=...)"},
        {value: "followup",          description: "Follow-up email templates (NAME=...)"},
        {value: "follow-up",         description: "Follow-up alerts (NAME= DAYS=)"},
        {value: "clean",             description: "Remove generated files"},
        {value: "clean-all",         description: "Remove all generated files incl. .tex"},
        {value: "help",              description: "Show all available commands"},
        {value: "tone",              description: "Tone check (NAME=...)"},
        {value: "cl-score",          description: "Cover letter score (NAME=...)"},
        {value: "research",          description: "Company intel (NAME=...)"},
        {value: "discover",          description: "Discover new jobs from sources"},
        {value: "discover-apply",    description: "Discover + auto-create branches"},
        {value: "batch",             description: "Apply to multiple jobs from CSV (CSV=...)"},
        {value: "batch-dry",         description: "Preview batch apply (dry run)"},
        {value: "watch",             description: "Auto-recompile on YAML changes (NAME=...)"},
        {value: "digest",            description: "Weekly pipeline digest (NO_SEND=true)"},
        {value: "deadline-alert",    description: "Deadline + stale alerts (DAYS=3)"},
        {value: "notify",            description: "Status update notifications (NAME= STATUS=)"},
        {value: "contacts",          description: "Find recruiter/HM contacts (NAME=...)"},
        {value: "url-check",         description: "Check if job URLs are live (NAME=...)"},
        {value: "json-resume",       description: "Export to JSON Resume v1.0.0"},
        {value: "question-bank",     description: "Aggregate Q&A from all prep.md"},
        {value: "ats-rank",          description: "Rank applications by ATS score (MIN=70)"},
        {value: "ats-text",          description: "Export as ATS-safe plain text (NAME=...)"},
        {value: "job-fit",           description: "Fit score: salary, remote, culture (NAME=...)"},
        {value: "linkedin-message",  description: "LinkedIn cold outreach (NAME=...)"},
        {value: "cv-health",         description: "CV audit: verbs, length, repetition (NAME=...)"},
        {value: "cv-versions",       description: "Manage named CV snapshots (ACTION=...)"},
        {value: "milestone",         description: "Log interview stage (NAME= STAGE=)"},
        {value: "cover-angles",      description: "3 CL variants: biz/tech/culture (NAME=...)"},
        {value: "recruiter-email",   description: "Cold email outreach (NAME=...)"},
        {value: "references",        description: "Manage references (ACTION=list|add)"},
        {value: "network-map",       description: "Mermaid network map (NAME=...)"},
        {value: "prep-quiz",         description: "Terminal flashcard quiz (NAME= CAT=)"},
        {value: "competitor-map",    description: "Competitor landscape (NAME=...)"},
        {value: "salary-bench",      description: "Salary benchmark (NAME=...)"},
        {value: "cv-fr-tailor",      description: "Translate CV+CL to French (NAME=...)"},
        {value: "apply-board",       description: "Kanban board by stage (STAGE=...)"},
        {value: "archive-app",       description: "Archive with summary + git tag (NAME=...)"},
        {value: "linkedin-profile",  description: "LinkedIn Headline/About/Exp (NAME=...)"},
        {value: "interview-brief",   description: "Morning-of cheat sheet (NAME=...)"},
        {value: "prep-star",         description: "STAR stories from CV (NAME= COUNT=5)"},
        {value: "interview-debrief", description: "Post-interview debrief (NAME=...)"},
        {value: "linkedin-post",     description: "LinkedIn post (TYPE=...)"},
        {value: "export-csv",        description: "Export applications to CSV"},
        {value: "elevator-pitch",    description: "30s/60s/90s pitches (NAME=...)"},
        {value: "onboarding-plan",   description: "30/60/90-day plan (NAME=...)"},
        {value: "cover-critique",    description: "AI critique + rewrite suggestions (NAME=...)"},
        {value: "interview-sim",     description: "Interactive interview simulator (NAME=...)"},
        {value: "cv-keywords",       description: "Keyword gap: CV vs all job postings (MIN=2)"},
        {value: "blind-spots",       description: "Silent objections + gap analysis (NAME=...)"},
        {value: "validate-all",      description: "Validate all cv*.yml against schema"},
        {value: "test",              description: "Run unit tests"},
        {value: "dev-setup",         description: "One-command env setup (venv + deps)"},
        {value: "preview",           description: "Generate all theme variant PDFs"},
        {value: "dashboard",         description: "HTML pipeline dashboard"},
        {value: "trends",            description: "Keyword trend analysis (SINCE=YYYY-MM)"},
        {value: "thankyou",          description: "Thank-you email after interview (NAME= STAGE=)"},
        {value: "negotiate",         description: "Negotiation script (NAME= OFFER=)"},
        {value: "docker-build",      description: "Build Docker image (DOCKER_IMAGE=...)"},
        {value: "docker-run",        description: "Run make target in container (TARGET=...)"},
    ]
}

# Custom completer for `make` in the CV repo
def cv-make-completer [context: string, position: int] {
    let words = $context | split row ' ' | filter {|w| $w != ''}
    let n = $words | length

    # First argument after 'make': suggest targets
    if $n <= 1 {
        return (cv-targets)
    }

    let current = if $n >= 2 { $words | last } else { "" }

    # NAME= → application directories
    if ($current | str starts-with "NAME=") {
        let prefix = "NAME="
        return (cv-apps | each {|d| {value: $"($prefix)($d)", description: $d}})
    }

    if ($current | str starts-with "NAME1=") {
        let prefix = "NAME1="
        return (cv-apps | each {|d| {value: $"($prefix)($d)", description: $d}})
    }

    if ($current | str starts-with "NAME2=") {
        let prefix = "NAME2="
        return (cv-apps | each {|d| {value: $"($prefix)($d)", description: $d}})
    }

    # AI= → providers
    if ($current | str starts-with "AI=") {
        return (cv-providers | each {|p| {value: $"AI=($p)", description: $p}})
    }

    # FORMAT= → formats
    if ($current | str starts-with "FORMAT=") {
        return (cv-formats | each {|f| {value: $"FORMAT=($f)", description: $f}})
    }

    # LANG= → languages
    if ($current | str starts-with "LANG=") {
        return (cv-langs | each {|l| {value: $"LANG=($l)", description: $l}})
    }

    # TARGET= → make targets (for docker-run)
    if ($current | str starts-with "TARGET=") {
        return (["render", "check", "test", "score", "app"] | each {|t|
            {value: $"TARGET=($t)", description: $"make ($t) inside container"}
        })
    }

    # Suggest param names based on target
    let target = if $n >= 2 { $words | get 1 } else { "" }
    let params = match $target {
        "app" | "score" | "lint" | "diff" | "archive" | "check" | "fetch" |
        "prep" | "open" | "visual-diff" | "review" | "tone" | "cl-score" |
        "research" | "contacts" | "url-check" | "ats-text" | "job-fit" |
        "cv-health" | "milestone" | "cover-angles" | "recruiter-email" |
        "references" | "network-map" | "prep-quiz" | "competitor-map" |
        "salary-bench" | "cv-fr-tailor" | "archive-app" | "linkedin-profile" |
        "interview-brief" | "prep-star" | "interview-debrief" | "linkedin-post" |
        "export-csv" | "elevator-pitch" | "onboarding-plan" | "cover-critique" |
        "interview-sim" | "cv-keywords" | "blind-spots" | "thankyou" |
        "negotiate" | "followup" | "follow-up" | "notify" | "ats-rank" |
        "deadline-alert" | "digest" | "linkedin-message" | "effectiveness" | "watch" => {
            ["NAME="]
        }
        "tailor" | "pipeline" => { ["NAME=", "AI="] }
        "compare"             => { ["NAME1=", "NAME2="] }
        "export" | "report"   => { ["FORMAT="] }
        "render"              => { ["LANG=", "PDFA=true", "DRAFT=true"] }
        "apply" | "new"       => { ["COMPANY=", "POSITION=", "URL="] }
        "linkedin"            => { ["PUSH=true"] }
        "batch" | "batch-dry" => { ["CSV="] }
        "docker-run"          => { ["TARGET="] }
        "docker-build"        => { ["DOCKER_IMAGE="] }
        _                     => { [] }
    }

    $params | each {|p| {value: $p, description: $p}}
}

# Register the completer for `make`
$env.config.completions.external.completer = {|spans|
    let cmd = $spans | first
    if $cmd == "make" {
        let context = $spans | str join ' '
        cv-make-completer $context ($context | str length)
    }
}
