#!/usr/bin/env python3
"""
AI-powered interview simulator.

Phase 1: Generate N role-specific questions (1 API call).
Phase 2: Interactive Q&A — answer each question in the terminal.
Phase 3: AI evaluates all answers and provides coaching feedback (1 API call).

Reads: meta.yml, job.txt, cv-tailored.yml (fallback data/cv.yml), milestones.yml
Output: applications/NAME/interview-sim-TYPE-DATE.md

Usage:
    scripts/interview-sim.py <app-dir> [--rounds N] [--type behavioral|technical|mixed|pressure] [--ai PROVIDER]

AI providers: gemini (default) | claude | openai | mistral | ollama

Interview types:
  behavioral  — STAR-format questions (leadership, conflict, failure, teamwork)
  technical   — Role-specific technical questions (SE leadership: demos, architecture, strategy)
  mixed       — Mix of behavioral + technical (default)
  pressure    — Challenging questions, devil's advocate, rapid-fire
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML required: pip install pyyaml")
    sys.exit(1)

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT   = _SCRIPT_DIR.parent

GEMINI_MODEL    = "gemini-2.5-flash"
GEMINI_FALLBACK = "gemini-2.0-flash-lite"
CLAUDE_MODEL    = "claude-sonnet-4-6"
CLAUDE_FALLBACK = "claude-haiku-4-5-20251001"
OPENAI_MODEL    = "gpt-4o"
OPENAI_FALLBACK = "gpt-4o-mini"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
MISTRAL_MODEL    = "mistral-large-latest"
MISTRAL_FALLBACK = "mistral-small-latest"
MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"

VALID_PROVIDERS = {"gemini", "claude", "openai", "mistral", "ollama"}
KEY_ENV = {
    "gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY", "mistral": "MISTRAL_API_KEY", "ollama": None,
}

TYPE_LABEL = {
    "behavioral": "Behavioral (STAR)",
    "technical":  "Technical / Role-Specific",
    "mixed":      "Mixed (Behavioral + Technical)",
    "pressure":   "Pressure / Devil's Advocate",
}

TYPE_INSTRUCTIONS = {
    "behavioral": """\
Generate behavioral interview questions using STAR format triggers.
Focus on: leadership under pressure, scaling teams, managing conflict, driving revenue,
strategic decisions with incomplete info, M&A integration, coaching team members.
Start each question with "Tell me about a time..." or "Describe a situation where...".""",

    "technical": """\
Generate technical and role-specific questions for a VP of Sales Engineering role.
Focus on: SE team structure and metrics, demo strategy, technical win rates, POC management,
competitive positioning, SE/AE alignment, pipeline coverage, building technical sales culture,
handling a complex enterprise deal from a technical perspective.""",

    "mixed": """\
Generate a mix: half behavioral (STAR format), half technical/role-specific.
Behavioral: leadership, scaling, conflict, revenue.
Technical: SE metrics, demo strategy, team structure, enterprise deals.""",

    "pressure": """\
Generate challenging, pressure-test questions. Include:
- Devil's advocate challenges ("Why should we pick you over someone with direct industry experience?")
- Failure/weakness probes ("What's the biggest deal you lost and why was it your fault?")
- Scenario traps ("Your top SE just resigned the week before a critical renewal — what do you do?")
- Provocative framings ("Convince me SE teams are a cost, not a revenue driver.")
Do not make them unfair — they should be realistic pressure an interviewer might apply.""",
}


def call_gemini(prompt, api_key, retries=6):
    for model in (GEMINI_MODEL, GEMINI_FALLBACK):
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={api_key}")
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                               "generationConfig": {"temperature": 0.5, "maxOutputTokens": 4000}}).encode()
        for attempt in range(retries):
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(min(2 ** (attempt + 2), 60))
                elif e.code == 429 and model != GEMINI_FALLBACK:
                    break
                else:
                    raise
    raise RuntimeError("Gemini rate-limited")


def call_claude(prompt, api_key, retries=6):
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    for model in (CLAUDE_MODEL, CLAUDE_FALLBACK):
        payload = json.dumps({"model": model, "max_tokens": 4000,
                               "messages": [{"role": "user", "content": prompt}]}).encode()
        for attempt in range(retries):
            req = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())["content"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(min(2 ** (attempt + 2), 60))
                elif e.code == 429 and model != CLAUDE_FALLBACK:
                    break
                else:
                    raise
    raise RuntimeError("Claude rate-limited")


def call_openai_compat(prompt, endpoint, api_key, models, retries=6):
    primary, fallback = models
    headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    for model in (primary, fallback):
        payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                               "max_tokens": 4000, "temperature": 0.5}).encode()
        for attempt in range(retries):
            req = urllib.request.Request(endpoint, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read())["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(min(2 ** (attempt + 2), 60))
                elif e.code == 429 and model != fallback:
                    break
                else:
                    raise
    raise RuntimeError("API rate-limited")


def call_ollama(prompt, retries=3):
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3")
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                           "stream": False}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(f"{host}/api/chat", data=payload,
                                      headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read())["message"]["content"]
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                raise RuntimeError(f"Cannot connect to Ollama at {host}")


def call_ai(prompt, provider, api_key):
    if provider == "gemini":  return call_gemini(prompt, api_key)
    if provider == "claude":  return call_claude(prompt, api_key)
    if provider == "openai":  return call_openai_compat(prompt, OPENAI_ENDPOINT, api_key, (OPENAI_MODEL, OPENAI_FALLBACK))
    if provider == "mistral": return call_openai_compat(prompt, MISTRAL_ENDPOINT, api_key, (MISTRAL_MODEL, MISTRAL_FALLBACK))
    if provider == "ollama":  return call_ollama(prompt)
    raise ValueError(f"Unknown provider: {provider}")


def load_env():
    env_path = _REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _strip_bold(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", s)


def _read(path: Path, max_chars: int = 1500) -> str:
    return path.read_text(encoding="utf-8")[:max_chars] if path.exists() else ""


QUESTIONS_PROMPT = """\
You are preparing a senior hiring panel interview for {position} at {company}.
The candidate is Jérôme Soyer, VP of Sales Engineering with 15+ years in cybersecurity/SaaS.

Job Description:
{job_excerpt}

{type_instructions}

Generate exactly {rounds} interview questions for this role and candidate profile.
Return ONLY a valid JSON array of strings — no intro, no numbering, no commentary.
Example format: ["Question 1?", "Question 2?", "Question 3?"]
"""

EVALUATION_PROMPT = """\
You are a senior hiring panel evaluator assessing a candidate's interview performance.
Be honest, specific, and constructive. Rate objectively — do not over-encourage.

## Candidate
Jérôme Soyer — applying for {position} at {company}.

## Interview Type
{type_label}

## Q&A Transcript
{transcript}

## Job Context
{job_excerpt}

## Task

Evaluate the full interview using this exact format:

---

## 📊 Overall Assessment

| Metric | Rating |
|--------|--------|
| Answer quality (STAR completeness) | Excellent / Good / Fair / Weak |
| Specificity (numbers, names, details) | Excellent / Good / Fair / Weak |
| Executive presence (confidence, clarity) | Excellent / Good / Fair / Weak |
| Role fit signal | Strong / Moderate / Unclear |
| **Overall readiness** | **Ready / Almost / Needs Work** |

---

## Question-by-Question Feedback

For each question, provide:
**Q{n}: [question text]**
- **Strength:** [what worked]
- **Gap:** [what was missing or weak]
- **Better answer element:** [1 sentence on what to add or change]

---

## 🔁 Patterns to Fix
2–3 recurring weaknesses across all answers (e.g. "answers too long", "missing quantification").

## 💪 Consistent Strengths
2–3 things done well across multiple answers.

## 🎯 Top 3 Priorities Before Next Interview
Specific, actionable coaching points — ordered by impact.

---
"""


def _get_multiline_input(prompt_text: str) -> str:
    """Read multi-line input. Single blank line = done."""
    print(prompt_text)
    print("  (type your answer, press Enter on a blank line when done)\n")
    lines = []
    try:
        while True:
            line = input()
            if line == "":
                if lines:
                    break
            else:
                lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines).strip()


def main():
    parser = argparse.ArgumentParser(description="Interactive AI interview simulator")
    parser.add_argument("app_dir", help="Application directory")
    parser.add_argument("--rounds", type=int, default=5,
                        help="Number of questions (default: 5)")
    parser.add_argument("--type", dest="interview_type", default="mixed",
                        choices=list(TYPE_LABEL),
                        help="Interview type (default: mixed)")
    parser.add_argument("--ai", default="gemini", choices=sorted(VALID_PROVIDERS))
    args = parser.parse_args()

    load_env()

    app_dir = Path(args.app_dir)
    if not app_dir.is_dir():
        app_dir = _REPO_ROOT / "applications" / Path(args.app_dir).name
    if not app_dir.is_dir():
        print(f"❌ Directory not found: {args.app_dir}")
        sys.exit(1)

    key_env = KEY_ENV.get(args.ai)
    api_key = os.environ.get(key_env, "") if key_env else ""
    if key_env and not api_key:
        print(f"❌ {key_env} not set")
        sys.exit(1)

    meta = {}
    if (app_dir / "meta.yml").exists():
        with open(app_dir / "meta.yml", encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}

    company  = meta.get("company", app_dir.name)
    position = meta.get("position", "the role")
    job_excerpt = _read(app_dir / "job.txt", 1500) or "(no job.txt)"

    type_label = TYPE_LABEL[args.interview_type]
    type_instructions = TYPE_INSTRUCTIONS[args.interview_type]

    divider = "═" * 60

    print(f"\n🎯 Interview Simulation — {company}")
    print(f"   {position} · {type_label} · {args.rounds} questions · AI: {args.ai}")
    print(f"\n{divider}")
    print("Generating questions...")

    # Phase 1: Generate questions
    q_prompt = QUESTIONS_PROMPT.format(
        company=company,
        position=position,
        job_excerpt=job_excerpt,
        type_instructions=type_instructions,
        rounds=args.rounds,
    )
    raw_questions = call_ai(q_prompt, args.ai, api_key)

    # Parse JSON questions, with fallback to line-splitting
    questions = []
    try:
        # Strip markdown code blocks if present
        cleaned = re.sub(r"```(?:json)?", "", raw_questions).strip().strip("`")
        questions = json.loads(cleaned)
        if not isinstance(questions, list):
            raise ValueError("Not a list")
    except Exception:
        # Fallback: split by lines, strip numbering
        for line in raw_questions.splitlines():
            line = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip().strip('"').strip("'")
            if line and line.endswith("?"):
                questions.append(line)
    questions = [str(q).strip() for q in questions[:args.rounds] if str(q).strip()]

    if not questions:
        print("❌ Failed to generate questions. Try again.")
        sys.exit(1)

    print(f"✅ {len(questions)} questions ready.\n")
    print(f"{divider}")
    print("INSTRUCTIONS:")
    print("  • Answer each question as you would in a real interview.")
    print("  • Aim for 1–3 minutes per answer (written form).")
    print("  • Be specific — use names, numbers, outcomes.")
    print("  • Press Enter on a blank line to submit your answer.")
    print(f"{divider}\n")

    input("Press Enter to begin...")

    # Phase 2: Interactive Q&A
    qa_pairs = []
    for i, question in enumerate(questions, 1):
        print(f"\n{divider}")
        print(f"Question {i}/{len(questions)}")
        print(f"{divider}\n")
        print(f"{question}\n")
        answer = _get_multiline_input(f"Your answer:")
        if not answer:
            answer = "(no answer provided)"
        qa_pairs.append((question, answer))
        if i < len(questions):
            print(f"\n✅ Recorded. Moving to question {i + 1}...")

    print(f"\n{divider}")
    print(f"🏁 All {len(questions)} questions answered.")
    print("Generating AI evaluation...")
    print(f"{divider}\n")

    # Phase 3: Evaluate all answers
    transcript_lines = []
    for i, (q, a) in enumerate(qa_pairs, 1):
        transcript_lines.append(f"**Q{i}:** {q}\n\n**Answer:** {a}\n")
    transcript = "\n---\n".join(transcript_lines)

    eval_prompt = EVALUATION_PROMPT.format(
        company=company,
        position=position,
        type_label=type_label,
        transcript=transcript,
        job_excerpt=job_excerpt,
    )
    evaluation = call_ai(eval_prompt, args.ai, api_key)

    print(evaluation.strip())

    # Save transcript + evaluation
    from datetime import date
    today = date.today().isoformat()
    out_name = f"interview-sim-{args.interview_type}-{today}.md"

    out_lines = [
        f"# Interview Simulation — {company}",
        f"*{position} · {type_label} · {len(questions)} questions · {today} · AI: {args.ai}*",
        "",
        "---",
        "",
        "## Transcript",
        "",
    ]
    for i, (q, a) in enumerate(qa_pairs, 1):
        out_lines += [
            f"### Q{i}",
            "",
            f"**{q}**",
            "",
            a,
            "",
        ]
    out_lines += [
        "---",
        "",
        evaluation.strip(),
        "",
    ]

    out = app_dir / out_name
    out.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\n✅ Saved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
