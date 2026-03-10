# PowerShell completion for CV Makefile
# Install: Add to your $PROFILE:
#   . /path/to/CV/scripts/completions.ps1
# Or dot-source in current session:
#   . scripts/completions.ps1

$CvTargets = @(
    [PSCustomObject]@{ Name = 'all';              Description = 'Build master CV + Cover Letter' }
    [PSCustomObject]@{ Name = 'app';              Description = 'Build application PDFs (NAME=...)' }
    [PSCustomObject]@{ Name = 'new';              Description = 'Scaffold new application (COMPANY= POSITION=)' }
    [PSCustomObject]@{ Name = 'apply';            Description = 'Full workflow: branch + scaffold + PR' }
    [PSCustomObject]@{ Name = 'tailor';           Description = 'AI tailor (NAME=... AI=gemini|claude|openai|mistral|ollama)' }
    [PSCustomObject]@{ Name = 'render';           Description = 'Render CV.tex from YAML (LANG= PDFA= DRAFT=)' }
    [PSCustomObject]@{ Name = 'score';            Description = 'ATS keyword score (NAME=...)' }
    [PSCustomObject]@{ Name = 'status';           Description = 'Kanban dashboard of all applications' }
    [PSCustomObject]@{ Name = 'pipeline';         Description = 'Tailor + review in one step (NAME= AI=)' }
    [PSCustomObject]@{ Name = 'current';          Description = 'Print current application name from branch' }
    [PSCustomObject]@{ Name = 'lint';             Description = 'LaTeX lint check (NAME=...)' }
    [PSCustomObject]@{ Name = 'diff';             Description = 'Diff master vs tailored CV (NAME=...)' }
    [PSCustomObject]@{ Name = 'compare';          Description = 'Compare two tailored CVs (NAME1= NAME2=)' }
    [PSCustomObject]@{ Name = 'archive';          Description = 'Archive completed application (NAME=...)' }
    [PSCustomObject]@{ Name = 'export';           Description = 'Export CV data (FORMAT=json|markdown|text)' }
    [PSCustomObject]@{ Name = 'linkedin';         Description = 'LinkedIn profile sync (PUSH=true)' }
    [PSCustomObject]@{ Name = 'hooks';            Description = 'Install git pre-commit hooks' }
    [PSCustomObject]@{ Name = 'check';            Description = 'Run all validations (NAME=...)' }
    [PSCustomObject]@{ Name = 'open';             Description = 'Build + open PDFs (NAME=...)' }
    [PSCustomObject]@{ Name = 'report';           Description = 'Application report (FORMAT=markdown)' }
    [PSCustomObject]@{ Name = 'fetch';            Description = 'Fetch job description from URL (NAME=...)' }
    [PSCustomObject]@{ Name = 'prep';             Description = 'Interview prep notes (NAME=...)' }
    [PSCustomObject]@{ Name = 'changelog';        Description = 'CV diff changelog' }
    [PSCustomObject]@{ Name = 'skills';           Description = 'Skills gap analysis across postings' }
    [PSCustomObject]@{ Name = 'visual-diff';      Description = 'PDF visual regression (NAME=...)' }
    [PSCustomObject]@{ Name = 'stats';            Description = 'Application statistics & metrics' }
    [PSCustomObject]@{ Name = 'doctor';           Description = 'Check all dependencies + API keys' }
    [PSCustomObject]@{ Name = 'effectiveness';    Description = 'Outcome vs ATS score analysis' }
    [PSCustomObject]@{ Name = 'review';           Description = 'Full review: render+build+validate+score (NAME=...)' }
    [PSCustomObject]@{ Name = 'docx';             Description = 'Convert CV to DOCX (NAME=...)' }
    [PSCustomObject]@{ Name = 'timeline';         Description = 'Mermaid Gantt chart' }
    [PSCustomObject]@{ Name = 'length';           Description = 'CV length vs 2-page constraint' }
    [PSCustomObject]@{ Name = 'match';            Description = 'Reverse ATS score (SOURCE=...)' }
    [PSCustomObject]@{ Name = 'followup';         Description = 'Follow-up email templates (NAME=...)' }
    [PSCustomObject]@{ Name = 'follow-up';        Description = 'Follow-up alerts (NAME= DAYS=)' }
    [PSCustomObject]@{ Name = 'clean';            Description = 'Remove generated files' }
    [PSCustomObject]@{ Name = 'clean-all';        Description = 'Remove all generated files incl. .tex' }
    [PSCustomObject]@{ Name = 'help';             Description = 'Show all available commands' }
    [PSCustomObject]@{ Name = 'tone';             Description = 'Tone check (NAME=...)' }
    [PSCustomObject]@{ Name = 'cl-score';         Description = 'Cover letter score (NAME=...)' }
    [PSCustomObject]@{ Name = 'research';         Description = 'Company intel (NAME=...)' }
    [PSCustomObject]@{ Name = 'discover';         Description = 'Discover new jobs from sources' }
    [PSCustomObject]@{ Name = 'discover-apply';   Description = 'Discover + auto-create branches' }
    [PSCustomObject]@{ Name = 'batch';            Description = 'Apply to multiple jobs from CSV' }
    [PSCustomObject]@{ Name = 'batch-dry';        Description = 'Preview batch apply (dry run)' }
    [PSCustomObject]@{ Name = 'watch';            Description = 'Auto-recompile on YAML changes (NAME=...)' }
    [PSCustomObject]@{ Name = 'digest';           Description = 'Weekly pipeline digest (NO_SEND=true)' }
    [PSCustomObject]@{ Name = 'deadline-alert';   Description = 'Deadline + stale alerts (DAYS=3)' }
    [PSCustomObject]@{ Name = 'notify';           Description = 'Status update notifications (NAME= STATUS=)' }
    [PSCustomObject]@{ Name = 'contacts';         Description = 'Find recruiter/HM contacts (NAME=...)' }
    [PSCustomObject]@{ Name = 'url-check';        Description = 'Check if job URLs are live (NAME=...)' }
    [PSCustomObject]@{ Name = 'json-resume';      Description = 'Export to JSON Resume v1.0.0' }
    [PSCustomObject]@{ Name = 'question-bank';    Description = 'Aggregate Q&A from all prep.md' }
    [PSCustomObject]@{ Name = 'ats-rank';         Description = 'Rank applications by ATS score (MIN=70)' }
    [PSCustomObject]@{ Name = 'ats-text';         Description = 'Export as ATS-safe plain text (NAME=...)' }
    [PSCustomObject]@{ Name = 'job-fit';          Description = 'Fit score: salary, remote, culture (NAME=...)' }
    [PSCustomObject]@{ Name = 'linkedin-message'; Description = 'LinkedIn cold outreach (NAME=...)' }
    [PSCustomObject]@{ Name = 'cv-health';        Description = 'CV audit: verbs, length, repetition (NAME=...)' }
    [PSCustomObject]@{ Name = 'cv-versions';      Description = 'Manage named CV snapshots (ACTION=...)' }
    [PSCustomObject]@{ Name = 'milestone';        Description = 'Log interview stage (NAME= STAGE=)' }
    [PSCustomObject]@{ Name = 'cover-angles';     Description = '3 CL variants: biz/tech/culture (NAME=...)' }
    [PSCustomObject]@{ Name = 'recruiter-email';  Description = 'Cold email outreach (NAME=...)' }
    [PSCustomObject]@{ Name = 'references';       Description = 'Manage references (ACTION=list|add)' }
    [PSCustomObject]@{ Name = 'network-map';      Description = 'Mermaid network map (NAME=...)' }
    [PSCustomObject]@{ Name = 'prep-quiz';        Description = 'Terminal flashcard quiz (NAME= CAT=)' }
    [PSCustomObject]@{ Name = 'competitor-map';   Description = 'Competitor landscape (NAME=...)' }
    [PSCustomObject]@{ Name = 'salary-bench';     Description = 'Salary benchmark (NAME=...)' }
    [PSCustomObject]@{ Name = 'cv-fr-tailor';     Description = 'Translate CV+CL to French (NAME=...)' }
    [PSCustomObject]@{ Name = 'apply-board';      Description = 'Kanban board by stage (STAGE=...)' }
    [PSCustomObject]@{ Name = 'archive-app';      Description = 'Archive with summary + git tag (NAME=...)' }
    [PSCustomObject]@{ Name = 'linkedin-profile'; Description = 'LinkedIn Headline/About/Exp (NAME=...)' }
    [PSCustomObject]@{ Name = 'interview-brief';  Description = 'Morning-of cheat sheet (NAME=...)' }
    [PSCustomObject]@{ Name = 'prep-star';        Description = 'STAR stories from CV (NAME= COUNT=5)' }
    [PSCustomObject]@{ Name = 'interview-debrief';Description = 'Post-interview debrief (NAME=...)' }
    [PSCustomObject]@{ Name = 'linkedin-post';    Description = 'LinkedIn post (TYPE=...)' }
    [PSCustomObject]@{ Name = 'export-csv';       Description = 'Export applications to CSV' }
    [PSCustomObject]@{ Name = 'elevator-pitch';   Description = '30s/60s/90s pitches (NAME=...)' }
    [PSCustomObject]@{ Name = 'onboarding-plan';  Description = '30/60/90-day plan (NAME=...)' }
    [PSCustomObject]@{ Name = 'cover-critique';   Description = 'AI critique + rewrite suggestions (NAME=...)' }
    [PSCustomObject]@{ Name = 'interview-sim';    Description = 'Interactive interview simulator (NAME=...)' }
    [PSCustomObject]@{ Name = 'cv-keywords';      Description = 'Keyword gap: CV vs all job postings (MIN=2)' }
    [PSCustomObject]@{ Name = 'blind-spots';      Description = 'Silent objections + gap analysis (NAME=...)' }
    [PSCustomObject]@{ Name = 'validate-all';     Description = 'Validate all cv*.yml against schema' }
    [PSCustomObject]@{ Name = 'test';             Description = 'Run unit tests' }
    [PSCustomObject]@{ Name = 'dev-setup';        Description = 'One-command env setup (venv + deps)' }
    [PSCustomObject]@{ Name = 'preview';          Description = 'Generate all theme variant PDFs' }
    [PSCustomObject]@{ Name = 'dashboard';        Description = 'HTML pipeline dashboard' }
    [PSCustomObject]@{ Name = 'trends';           Description = 'Keyword trend analysis (SINCE=YYYY-MM)' }
    [PSCustomObject]@{ Name = 'thankyou';         Description = 'Thank-you email after interview (NAME= STAGE=)' }
    [PSCustomObject]@{ Name = 'negotiate';        Description = 'Negotiation script (NAME= OFFER=)' }
    [PSCustomObject]@{ Name = 'docker-build';     Description = 'Build Docker image (DOCKER_IMAGE=...)' }
    [PSCustomObject]@{ Name = 'docker-run';       Description = 'Run make target in container (TARGET=...)' }
)

Register-ArgumentCompleter -Native -CommandName make -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    $elements = $commandAst.CommandElements
    $targetProvided = $elements.Count -gt 1

    # First argument: complete target names
    if (-not $targetProvided -or ($elements.Count -eq 2 -and -not $wordToComplete.Contains('='))) {
        $CvTargets |
            Where-Object { $_.Name -like "$wordToComplete*" } |
            ForEach-Object {
                [System.Management.Automation.CompletionResult]::new(
                    $_.Name, $_.Name,
                    [System.Management.Automation.CompletionResultType]::ParameterValue,
                    $_.Description
                )
            }
        return
    }

    # NAME= completion
    if ($wordToComplete -like 'NAME=*') {
        $prefix = $wordToComplete.Substring(0, $wordToComplete.IndexOf('=') + 1)
        $partial = $wordToComplete.Substring($prefix.Length)
        if (Test-Path 'applications') {
            Get-ChildItem -Path 'applications' -Directory |
                Where-Object { $_.Name -like "$partial*" } |
                ForEach-Object {
                    $val = "${prefix}$($_.Name)"
                    [System.Management.Automation.CompletionResult]::new(
                        $val, $val,
                        [System.Management.Automation.CompletionResultType]::ParameterValue,
                        $_.Name
                    )
                }
        }
        return
    }

    # NAME1=, NAME2= completion
    foreach ($paramPrefix in @('NAME1=', 'NAME2=')) {
        if ($wordToComplete -like "${paramPrefix}*") {
            $partial = $wordToComplete.Substring($paramPrefix.Length)
            if (Test-Path 'applications') {
                Get-ChildItem -Path 'applications' -Directory |
                    Where-Object { $_.Name -like "$partial*" } |
                    ForEach-Object {
                        $val = "${paramPrefix}$($_.Name)"
                        [System.Management.Automation.CompletionResult]::new(
                            $val, $val,
                            [System.Management.Automation.CompletionResultType]::ParameterValue,
                            $_.Name
                        )
                    }
            }
            return
        }
    }

    # AI= completion
    if ($wordToComplete -like 'AI=*') {
        @('gemini', 'claude', 'openai', 'mistral', 'ollama') |
            ForEach-Object {
                $val = "AI=$_"
                [System.Management.Automation.CompletionResult]::new(
                    $val, $val,
                    [System.Management.Automation.CompletionResultType]::ParameterValue,
                    $_
                )
            }
        return
    }

    # FORMAT= completion
    if ($wordToComplete -like 'FORMAT=*') {
        @('json', 'markdown', 'text') |
            ForEach-Object {
                $val = "FORMAT=$_"
                [System.Management.Automation.CompletionResult]::new(
                    $val, $val,
                    [System.Management.Automation.CompletionResultType]::ParameterValue,
                    $_
                )
            }
        return
    }

    # TARGET= completion (docker-run)
    if ($wordToComplete -like 'TARGET=*') {
        @('render', 'check', 'test', 'score', 'app') |
            ForEach-Object {
                $val = "TARGET=$_"
                [System.Management.Automation.CompletionResult]::new(
                    $val, $val,
                    [System.Management.Automation.CompletionResultType]::ParameterValue,
                    "make $_ inside container"
                )
            }
        return
    }

    # Suggest param names based on target
    $target = if ($elements.Count -gt 1) { $elements[1].Value } else { '' }
    $params = switch ($target) {
        { $_ -in 'app','score','lint','diff','archive','check','fetch','prep',
                  'open','visual-diff','review','tone','cl-score','research',
                  'contacts','url-check','ats-text','job-fit','cv-health',
                  'milestone','cover-angles','recruiter-email','references',
                  'network-map','prep-quiz','competitor-map','salary-bench',
                  'cv-fr-tailor','archive-app','linkedin-profile','interview-brief',
                  'prep-star','interview-debrief','linkedin-post','export-csv',
                  'elevator-pitch','onboarding-plan','cover-critique','interview-sim',
                  'cv-keywords','blind-spots','thankyou','negotiate','followup',
                  'follow-up','notify','ats-rank','deadline-alert','digest',
                  'linkedin-message','effectiveness' }
            { @('NAME=') }
        { $_ -in 'tailor','pipeline' }
            { @('NAME=', 'AI=') }
        'compare'
            { @('NAME1=', 'NAME2=') }
        { $_ -in 'export','report' }
            { @('FORMAT=') }
        'render'
            { @('LANG=', 'PDFA=true', 'DRAFT=true') }
        { $_ -in 'apply','new' }
            { @('COMPANY=', 'POSITION=', 'URL=') }
        'linkedin'
            { @('PUSH=true') }
        { $_ -in 'batch','batch-dry' }
            { @('CSV=') }
        'docker-run'
            { @('TARGET=') }
        'docker-build'
            { @('DOCKER_IMAGE=') }
        default
            { @() }
    }

    $params |
        Where-Object { $_ -like "$wordToComplete*" } |
        ForEach-Object {
            [System.Management.Automation.CompletionResult]::new(
                $_, $_, [System.Management.Automation.CompletionResultType]::ParameterValue, $_
            )
        }
}
