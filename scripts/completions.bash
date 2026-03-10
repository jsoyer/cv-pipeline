# Bash completion for CV Makefile
# Source this file: source scripts/completions.bash
# Or add to ~/.bashrc: source /path/to/CV/scripts/completions.bash

_cv_make() {
    local cur prev words
    _init_completion || return

    local targets=(
        all app new apply tailor render score status lint diff compare
        archive export linkedin hooks check open report fetch prep changelog
        skills visual-diff stats doctor effectiveness review docx timeline
        length match followup clean help pipeline current watch batch
        batch-dry digest deadline-alert follow-up notify contacts url-check
        json-resume question-bank ats-rank ats-text ats-text job-fit
        linkedin-message cv-health cv-versions milestone cover-angles
        recruiter-email references network-map prep-quiz competitor-map
        salary-bench cv-fr-tailor apply-board archive-app linkedin-profile
        interview-brief prep-star interview-debrief linkedin-post export-csv
        elevator-pitch onboarding-plan cover-critique interview-sim
        cv-keywords blind-spots validate-all test dev-setup doctor preview
        clean-all tone cl-score research discover discover-apply dashboard
        trends thankyou negotiate blind-spots cv-keywords match docker-build
        docker-run
    )

    # First argument: complete target names
    if [[ "${COMP_CWORD}" -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${targets[*]}" -- "${cur}") )
        return
    fi

    # NAME= completion: list application directories
    if [[ "${cur}" == NAME=* ]]; then
        local prefix="NAME="
        local apps=()
        if [[ -d applications ]]; then
            while IFS= read -r d; do
                apps+=("${prefix}${d}")
            done < <(ls -1 applications/ 2>/dev/null)
        fi
        COMPREPLY=( $(compgen -W "${apps[*]}" -- "${cur}") )
        return
    fi

    if [[ "${cur}" == NAME1=* ]]; then
        local prefix="NAME1="
        local apps=()
        if [[ -d applications ]]; then
            while IFS= read -r d; do apps+=("${prefix}${d}"); done < <(ls -1 applications/ 2>/dev/null)
        fi
        COMPREPLY=( $(compgen -W "${apps[*]}" -- "${cur}") )
        return
    fi

    if [[ "${cur}" == NAME2=* ]]; then
        local prefix="NAME2="
        local apps=()
        if [[ -d applications ]]; then
            while IFS= read -r d; do apps+=("${prefix}${d}"); done < <(ls -1 applications/ 2>/dev/null)
        fi
        COMPREPLY=( $(compgen -W "${apps[*]}" -- "${cur}") )
        return
    fi

    # AI= provider completion
    if [[ "${cur}" == AI=* ]]; then
        COMPREPLY=( $(compgen -W "AI=gemini AI=claude AI=openai AI=mistral AI=ollama" -- "${cur}") )
        return
    fi

    # FORMAT= completion
    if [[ "${cur}" == FORMAT=* ]]; then
        COMPREPLY=( $(compgen -W "FORMAT=json FORMAT=markdown FORMAT=text" -- "${cur}") )
        return
    fi

    # LANG= completion
    if [[ "${cur}" == LANG=* ]]; then
        local langs=()
        for f in data/cv-*.yml; do
            [[ -f "$f" ]] && langs+=("LANG=$(basename "$f" | sed 's/cv-//;s/\.yml//')")
        done
        COMPREPLY=( $(compgen -W "${langs[*]}" -- "${cur}") )
        return
    fi

    # TARGET= completion (for docker-run)
    if [[ "${cur}" == TARGET=* ]]; then
        COMPREPLY=( $(compgen -W "TARGET=render TARGET=check TARGET=test TARGET=score" -- "${cur}") )
        return
    fi

    # Suggest param names based on target
    local target="${COMP_WORDS[1]}"
    local params=()
    case "${target}" in
        app|score|lint|diff|archive|check|fetch|prep|open|visual-diff|review|\
        tone|cl-score|research|contacts|url-check|ats-text|job-fit|cv-health|\
        cv-versions|milestone|cover-angles|recruiter-email|references|\
        network-map|prep-quiz|competitor-map|salary-bench|cv-fr-tailor|\
        archive-app|linkedin-profile|interview-brief|prep-star|interview-debrief|\
        linkedin-post|export-csv|elevator-pitch|onboarding-plan|cover-critique|\
        interview-sim|cv-keywords|blind-spots|salary-bench|thankyou|negotiate|\
        deadline-alert|follow-up|followup|digest|notify|ats-rank)
            params=("NAME=") ;;
        tailor|pipeline)
            params=("NAME=" "AI=") ;;
        compare)
            params=("NAME1=" "NAME2=") ;;
        export|report)
            params=("FORMAT=") ;;
        render)
            params=("LANG=" "PDFA=" "DRAFT=") ;;
        apply|new)
            params=("COMPANY=" "POSITION=" "URL=") ;;
        linkedin)
            params=("PUSH=") ;;
        batch|batch-dry)
            params=("CSV=") ;;
        docker-run)
            params=("TARGET=") ;;
        docker-build)
            params=("DOCKER_IMAGE=") ;;
    esac
    COMPREPLY=( $(compgen -W "${params[*]}" -- "${cur}") )
}

complete -F _cv_make make
