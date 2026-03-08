#!/usr/bin/env python3
"""
Tailor CV and generate cover letter using AI (Gemini, Claude, OpenAI, Mistral, Ollama).

Usage:
    scripts/ai-tailor.py <application-dir> [--cv-only | --cl-only] [--provider PROVIDER]

Providers:
    gemini   — Google Gemini (default, GEMINI_API_KEY)
    claude   — Anthropic Claude (ANTHROPIC_API_KEY)
    openai   — OpenAI GPT (OPENAI_API_KEY)
    mistral  — Mistral AI (MISTRAL_API_KEY)
    ollama   — Local Ollama server (no key, OLLAMA_HOST, OLLAMA_MODEL)

Flow:
    cv.yml + job.txt → AI → cv-tailored.yml → render.py → CV.tex → PDF
    cv.yml + job.txt → AI → coverletter.yml → render.py → CoverLetter.tex → PDF
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

try:
    import yaml
except ImportError:
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)

from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS, PROVIDER_MODELS
from lib.common import company_from_dirname, setup_logging, REPO_ROOT

# --- Script paths (resolved at import time) ---
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_RENDER_PY  = os.path.join(_SCRIPT_DIR, "render.py")

# --- Auto-trim prompts ---
CV_TRIM_PROMPT = """\
The following CV YAML currently renders to {pages} pages but MUST fit in 2 pages.

Reduce it by:
1. Trim experience[0].items to {target_bullets} bullets maximum (keep the most impactful ones)
2. Shorten profile to 3 sentences maximum
3. Shorten each key_wins text to 1 concise sentence
4. Do NOT change any other sections

Return ONLY valid YAML with the exact same structure and keys — no markdown fences, no comments:

{yaml_text}"""

CL_TRIM_PROMPT = """\
The following cover letter YAML currently renders to {pages} pages but MUST fit in 1 page.

Reduce it by:
1. Shorten the "About Me" section to 2-3 sentences
2. Shorten "Why <company>?" to 2-3 sentences
3. Reduce "Why Me?" to 3 short paragraphs maximum
4. Keep the closing_paragraph as-is

Return ONLY valid YAML with the exact same structure and keys — no markdown fences, no comments:

{yaml_text}"""


# ---------------------------------------------------------------------------
# Atomic file write helper
# ---------------------------------------------------------------------------

def _atomic_write(path: str, content: str) -> None:
    """Write content to path atomically using a temp file + os.replace.

    Prevents partially-written files if the process crashes mid-write.
    The temp file is created in the same directory as path so that
    os.replace (rename) is guaranteed to be atomic on POSIX.
    """
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch_url_text(url):
    """Fetch URL and extract plain text (simple HTML stripping)."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r} (only http/https)")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:15000]


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def fix_yaml_bold(yaml_text):
    """Quote YAML values that start with ** (bold markdown) to prevent parse errors.
    key: **bold text**  →  key: "**bold text**"
    """
    return re.sub(
        r'^(\s*(?:-\s+)?\w[\w\s-]*:\s)(\*\*.+)$',
        lambda m: m.group(1) + '"' + m.group(2).replace('"', '\\"') + '"',
        yaml_text,
        flags=re.MULTILINE,
    )


def extract_yaml_block(text):
    """Extract YAML content from a response that may contain markdown fences."""
    match = re.search(r"```ya?ml\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return fix_yaml_bold(match.group(1).strip())
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return fix_yaml_bold(match.group(1).strip())
    return fix_yaml_bold(text.strip())


# ---------------------------------------------------------------------------
# Auto-trim helpers
# ---------------------------------------------------------------------------

def count_pdf_pages(pdf_path):
    """Count pages in a PDF. Returns -1 on failure."""
    try:
        r = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
    except Exception:
        pass
    # Regex fallback (reads raw PDF binary)
    try:
        with open(pdf_path, "rb") as f:
            content = f.read()
        m = re.search(rb"/Type\s*/Pages\b[^>]*/Count\s+(\d+)", content)
        return int(m.group(1)) if m else -1
    except Exception:
        return -1


def render_and_compile(yml_path, tex_path, app_dir, xelatex):
    """Render YAML → LaTeX (via render.py) then compile to PDF (via xelatex).
    Returns PDF path on success, None on failure."""
    is_cl = "coverletter" in os.path.basename(yml_path).lower()
    render_cmd = ["python3", _RENDER_PY, "-d", yml_path, "-o", tex_path]
    if is_cl:
        cv_data = os.path.join(app_dir, "cv-tailored.yml")
        if not os.path.exists(cv_data):
            cv_data = os.path.join(str(REPO_ROOT), "data", "cv.yml")
        render_cmd += ["--cv-data", cv_data]
    try:
        subprocess.run(render_cmd, check=True, capture_output=True, cwd=str(REPO_ROOT))
    except subprocess.CalledProcessError as e:
        log.warning("render.py failed: %s", e.stderr.decode(errors="ignore")[:200])
        return None

    env = os.environ.copy()
    env["TEXINPUTS"] = os.path.join(str(REPO_ROOT), "awesome-cv") + ":" + env.get("TEXINPUTS", "")
    try:
        subprocess.run(
            [xelatex, "-interaction=nonstopmode", "-output-directory", app_dir, tex_path],
            check=True, capture_output=True, env=env, cwd=str(REPO_ROOT),
        )
    except subprocess.CalledProcessError as e:
        log.warning("xelatex failed (check %s manually)", tex_path)
        return None

    pdf_path = tex_path[:-4] + ".pdf" if tex_path.endswith(".tex") else tex_path + ".pdf"
    return pdf_path if os.path.exists(pdf_path) else None


def trim_to_pages(app_dir, yml_path, tex_path, api_key, provider, page_limit, max_iterations=3, model=None):
    """Render → compile → check pages → AI-trim loop until the PDF fits within page_limit."""
    xelatex = os.environ.get("XELATEX") or shutil.which("xelatex")
    if not xelatex:
        log.warning("xelatex not in PATH — skipping auto-trim (set XELATEX env var to override)")
        return

    is_cl = "coverletter" in os.path.basename(yml_path).lower()

    for i in range(max_iterations):
        print(f"   🔄 Compiling to check page count (attempt {i + 1}/{max_iterations})...", flush=True)
        pdf_path = render_and_compile(yml_path, tex_path, app_dir, xelatex)
        if not pdf_path:
            log.warning("Compilation failed — skipping auto-trim")
            return

        pages = count_pdf_pages(pdf_path)
        if pages == -1:
            log.warning("Could not count pages — skipping auto-trim")
            return
        if pages <= page_limit:
            print(f"   ✅ Fits in {pages} page(s) (limit: {page_limit})")
            return

        print(f"   📏 {pages} page(s) — needs trimming (limit: {page_limit})", flush=True)

        with open(yml_path, encoding="utf-8") as f:
            yaml_text = f.read()

        if is_cl:
            prompt = CL_TRIM_PROMPT.format(pages=pages, yaml_text=yaml_text)
        else:
            try:
                bullets = len(yaml.safe_load(yaml_text).get("experience", [{}])[0].get("items", []))
            except Exception:
                bullets = 5
            target_bullets = max(3, bullets - 2)
            prompt = CV_TRIM_PROMPT.format(
                pages=pages, bullet_count=bullets,
                target_bullets=target_bullets, yaml_text=yaml_text,
            )

        model_label = f" ({model})" if model else ""
        print(f"   🤖 Asking {provider}{model_label} to trim...", flush=True)
        result = call_ai(prompt, provider, api_key, model=model)
        trimmed = extract_yaml_block(result)

        try:
            yaml.safe_load(trimmed)
        except Exception as e:
            log.warning("Trim returned invalid YAML: %s — stopping", e)
            return

        _atomic_write(yml_path, trimmed)

    # Final check
    pdf_path = render_and_compile(yml_path, tex_path, app_dir, xelatex)
    if pdf_path:
        pages = count_pdf_pages(pdf_path)
        if pages <= page_limit:
            print(f"   ✅ Fits in {pages} page(s) after {max_iterations} trim(s)")
            return
    log.warning("Still too long after %d trim(s) — review %s manually", max_iterations, yml_path)


# ---------------------------------------------------------------------------
# Core tailoring functions
# ---------------------------------------------------------------------------

def tailor_cv(app_dir, job_url, job_text, api_key, provider, cv_data_path="data/cv.yml", model=None, dry_run=False):
    """Tailor the CV using the selected AI provider. Returns YAML, not LaTeX."""
    with open(cv_data_path, encoding="utf-8") as f:
        cv_yaml = f.read()

    prompt = f"""You are an expert career advisor specializing in Sales Engineering, \
Pre-Sales, and Technical Leadership roles.

I need you to tailor my resume YAML data for a specific job application.

### Target Job Posting
Content extracted from {job_url}:

{job_text}

### My Master Resume (YAML format)

```yaml
{cv_yaml}
```

### Instructions

1. **Analyze** the job description and identify the top 5-7 key requirements/skills.
2. **Rewrite** ONLY these sections to better align with the target role:
   - `profile`: Rewrite the summary to mirror the job's language. 3-4 sentences max.
   - `skills`: Reorder categories and adjust items. Add relevant keywords from the job posting.
   - `key_wins`: Rewrite titles and text to emphasize relevant achievements.
   - `experience[0].items` (the RVP role ONLY): Rewrite bullet labels and text to emphasize \
relevant accomplishments.
3. **Do NOT change**: `personal`, `experience[1:]` (past roles), `early_career`, `education`, \
`certifications`, `awards`, `publications`, `languages`, `interests`.
4. **Output format**: Return ONLY valid YAML with the exact same structure and keys as the input. \
No markdown fences, no comments, no explanations — just raw YAML.
5. **YAML rules**:
   - Use `>-` for multiline text (profile, key_wins text)
   - Use `**bold**` for emphasis (render.py converts this to LaTeX bold)
   - Never use LaTeX commands — this is YAML, not LaTeX
   - Do NOT escape special characters (& % $ #) — render.py handles escaping
6. **Tone**: Professional, leadership-focused, results-driven. Strong action verbs and metrics.
7. **Length constraint**: Keep content concise — the final PDF must fit on 2 pages."""

    result = call_ai(prompt, provider, api_key, model=model)
    yaml_text = extract_yaml_block(result)

    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict) or "personal" not in data:
            raise ValueError("Missing 'personal' key — not a valid CV YAML")
    except Exception as e:
        if dry_run:
            log.warning("%s returned invalid YAML: %s", provider, e)
            print("--- AI response (cv-tailored.yml) ---")
            print(result)
            return None
        raw_path = os.path.join(app_dir, "cv-tailored-raw.txt")
        _atomic_write(raw_path, result)
        log.warning("%s returned invalid YAML: %s", provider, e)
        log.warning("Raw output saved to: %s", raw_path)
        log.warning("Fix the YAML manually and save as cv-tailored.yml")
        return None

    output = os.path.join(app_dir, "cv-tailored.yml")
    if dry_run:
        print(f"[DRY RUN] Would write: {output}")
        print("--- AI response (cv-tailored.yml) ---")
        print(yaml_text)
        return None
    _atomic_write(output, yaml_text)
    return output


def generate_cover_letter(app_dir, job_url, job_text, api_key, provider,
                          cv_data_path="data/cv.yml", model=None, dry_run=False):
    """Generate cover letter YAML using the selected AI provider."""
    with open(cv_data_path, encoding="utf-8") as f:
        cv_yaml = f.read()

    app_name = os.path.basename(app_dir)
    company = company_from_dirname(app_name)

    prompt = f"""You are an expert career advisor specializing in Sales Engineering, \
Pre-Sales, and Technical Leadership roles.

I need you to write a cover letter as YAML data for a specific job application.

### Target Job Posting
Content extracted from {job_url}:

{job_text}

### My Resume (YAML, for context)

```yaml
{cv_yaml}
```

### Output Format

Return ONLY valid YAML with this exact structure (no markdown fences, no comments):

recipient:
  name: [Hiring Manager name if found in job posting, else "Talent Acquisition Team"]
  company: {company}

title: "Application for [exact position title from job posting]"
opening: "Dear [recipient name],"
closing: "Best regards,"

sections:
  - title: About Me
    content: >-
      [3-4 sentences. Confident opening. Current role, scope (50+ HC, Continental Europe), key achievement.]
  - title: "Why {company}?"
    content: >-
      [4-5 sentences. Genuine enthusiasm. Reference specific products, tech, market position, recent news.]
  - title: Why Me?
    content: >-
      [4-5 short paragraphs with **Bold Title:** format. Map strengths to company needs with metrics.]

closing_paragraph: >-
  [2-3 sentences. Thank them, express enthusiasm, mention next steps.]

### Rules
- Use `>-` for multiline content
- Use `**bold**` for emphasis (converted to LaTeX bold by render.py)
- Do NOT use LaTeX commands — this is YAML, not LaTeX
- Do NOT escape special characters (& % $ #) — render.py handles that
- Tone: Confident but not arrogant. Strategic and business-oriented.
- Length: Must fit on a single page when rendered."""

    result = call_ai(prompt, provider, api_key, model=model)
    yaml_text = extract_yaml_block(result)

    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict) or "sections" not in data:
            raise ValueError("Missing 'sections' key — not a valid cover letter YAML")
    except Exception as e:
        if dry_run:
            log.warning("%s returned invalid YAML: %s", provider, e)
            print("--- AI response (coverletter.yml) ---")
            print(result)
            return None
        raw_path = os.path.join(app_dir, "coverletter-raw.txt")
        _atomic_write(raw_path, result)
        log.warning("%s returned invalid YAML: %s", provider, e)
        log.warning("Raw output saved to: %s", raw_path)
        log.warning("Fix the YAML manually and save as coverletter.yml")
        return None

    output = os.path.join(app_dir, "coverletter.yml")
    if dry_run:
        print(f"[DRY RUN] Would write: {output}")
        print("--- AI response (coverletter.yml) ---")
        print(yaml_text)
        return None
    _atomic_write(output, yaml_text)
    return output


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Tailor CV and cover letter using AI (Gemini, Claude, OpenAI, Mistral, Ollama)"
    )
    parser.add_argument(
        "app_dir",
        help="Application directory (e.g. applications/2026-02-databricks)",
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("AI_PROVIDER", "gemini"),
        choices=sorted(VALID_PROVIDERS),
        help="AI provider to use (default: gemini, or set AI_PROVIDER env var)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cv-only", action="store_true", help="Only tailor CV")
    group.add_argument("--cl-only", action="store_true", help="Only generate cover letter")
    parser.add_argument(
        "--auto-trim", action="store_true",
        help="After tailoring, loop render→compile→trim until PDF fits page limits (CV ≤ 2p, CL ≤ 1p)",
    )
    all_models = [m for ms in PROVIDER_MODELS.values() for m in ms]
    parser.add_argument(
        "--model", default=None,
        help=f"Override default model (e.g. {', '.join(all_models[:4])}…). Leave blank for provider default.",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Call the AI provider and show what would be written, but do not write any files or compile",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    log = setup_logging(args.verbose)

    provider = args.provider
    model = args.model or None
    dry_run = args.dry_run

    if dry_run:
        print("[DRY RUN] No files will be written and no compilation will run.")

    # Resolve API key for the chosen provider
    key_var = KEY_ENV[provider]
    api_key = os.environ.get(key_var) if key_var else None
    if key_var and not api_key:
        log.error("Set %s environment variable", key_var)
        log.error("   export %s=your-key-here", key_var)
        sys.exit(1)

    print(f"🤖 Provider: {provider}" + (f" · Model: {model}" if model else ""), flush=True)
    if provider == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = model or os.environ.get("OLLAMA_MODEL", "llama3")
        print(f"   Host: {host}  Model: {ollama_model}", flush=True)

    app_dir = args.app_dir
    if not os.path.isdir(app_dir):
        log.error("Directory not found: %s", app_dir)
        sys.exit(1)

    # Read job URL / fallback to job.txt
    job_url = ""
    job_text = ""
    job_url_file = os.path.join(app_dir, "job.url")
    job_txt_file = os.path.join(app_dir, "job.txt")

    if os.path.exists(job_url_file):
        with open(job_url_file, encoding="utf-8") as f:
            job_url = f.read().strip().replace("\\", "")

    if job_url:
        print(f"🌐 Fetching: {job_url}")
        try:
            job_text = fetch_url_text(job_url)
            print(f"   Extracted {len(job_text)} characters")
        except Exception as e:
            log.warning("Could not fetch URL: %s", e)

    if not job_text and os.path.exists(job_txt_file):
        with open(job_txt_file, encoding="utf-8") as f:
            job_text = f.read()
        print(f"   Using fallback: {job_txt_file}")

    if not job_text:
        log.error("No job description found. Provide job.url or job.txt")
        sys.exit(1)

    # Read meta.yml for company/position (needed for auto-trim .tex filenames)
    meta_company, meta_position = "", ""
    meta_path = os.path.join(app_dir, "meta.yml")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f)
            meta_company = (meta or {}).get("company", "")
            meta_position = (meta or {}).get("position", "")
        except Exception:
            pass

    # CV tailoring
    cv_yml_path = None
    if not args.cl_only:
        print("🤖 Tailoring CV (YAML)...")
        cv_yml_path = tailor_cv(app_dir, job_url, job_text, api_key, provider, model=model, dry_run=dry_run)
        if cv_yml_path:
            print(f"   ✅ {cv_yml_path}")
            if args.auto_trim and meta_company and meta_position:
                cv_tex = os.path.join(app_dir, f"CV - {meta_company} - {meta_position}.tex")
                print("📏 Auto-trimming CV to 2 pages...")
                trim_to_pages(app_dir, cv_yml_path, cv_tex, api_key, provider, page_limit=2, model=model)
            elif args.auto_trim:
                log.warning("meta.yml missing company/position — skipping auto-trim")
        elif not dry_run:
            log.error("CV tailoring failed — see raw output above")

    # Cover letter generation
    cl_yml_path = None
    if not args.cv_only:
        print("🤖 Generating cover letter (YAML)...")
        cl_yml_path = generate_cover_letter(app_dir, job_url, job_text, api_key, provider, model=model, dry_run=dry_run)
        if cl_yml_path:
            print(f"   ✅ {cl_yml_path}")
            if args.auto_trim and meta_company and meta_position:
                cl_tex = os.path.join(app_dir, f"CoverLetter - {meta_company} - {meta_position}.tex")
                print("📏 Auto-trimming Cover Letter to 1 page...")
                trim_to_pages(app_dir, cl_yml_path, cl_tex, api_key, provider, page_limit=1, model=model)
            elif args.auto_trim:
                log.warning("meta.yml missing company/position — skipping auto-trim")
        elif not dry_run:
            log.error("Cover letter generation failed — see raw output above")

    print(f"\n✨ Done! Next steps:")
    print(f"   1. Review YAML files in {app_dir}/")
    print(f"   2. make app NAME={os.path.basename(app_dir)}")


if __name__ == "__main__":
    main()
