#!/usr/bin/env python3
"""
Generate interview preparation notes from job description + CV data.

Usage:
    scripts/interview-prep.py <application-dir>
"""

import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)


def load_cv_data(data_path="data/cv.yml"):
    with open(data_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_job_sections(text):
    """Parse job description into rough sections."""
    sections = {"requirements": [], "responsibilities": [], "about": [], "other": []}
    current = "other"

    for line in text.split("\n"):
        lower = line.lower().strip()
        if not lower:
            continue
        if re.search(r"(required|qualifications?|must.have|what you.+need|skills)", lower):
            current = "requirements"
        elif re.search(r"(responsibilit|what you.+do|duties|role)", lower):
            current = "responsibilities"
        elif re.search(r"(about (the|us|our)|who we are|company)", lower):
            current = "about"

        sections[current].append(line.strip())

    return sections


def match_strengths(cv_data, job_text):
    """Find CV bullet points relevant to the job."""
    job_lower = job_text.lower()
    matches = []

    for exp in cv_data.get("experience", []):
        for item in exp.get("items", []):
            text = item.get("text", "")
            words = set(re.findall(r"\b[a-z]{4,}\b", text.lower()))
            overlap = sum(1 for w in words if w in job_lower)
            if overlap >= 2:
                label = item.get("label", "")
                matches.append(f"**{label}:** {text}" if label else text)

    return matches[:10]


def identify_gaps(cv_data, job_sections):
    """Find requirements not well covered by CV."""
    cv_text = ""
    for exp in cv_data.get("experience", []):
        for item in exp.get("items", []):
            cv_text += " " + item.get("text", "")
    for skill in cv_data.get("skills", []):
        cv_text += " " + skill.get("items", "")
    cv_lower = cv_text.lower()

    gaps = []
    for req in job_sections.get("requirements", []):
        words = set(re.findall(r"\b[a-z]{4,}\b", req.lower()))
        overlap = sum(1 for w in words if w in cv_lower)
        if overlap == 0 and len(words) > 2:
            gaps.append(req.strip())

    return gaps[:8]


def generate_prep(cv_data, job_text, job_sections, company, position):
    """Generate interview prep markdown."""
    p = cv_data["personal"]
    strengths = match_strengths(cv_data, job_text)
    gaps = identify_gaps(cv_data, job_sections)

    lines = [
        f"# Interview Prep: {company} — {position}",
        f"",
        f"**Candidate:** {p['first_name']} {p['last_name']}",
        f"**Current role:** {p['position']}",
        f"",
        "---",
        "",
        "## Your Key Strengths for This Role",
        "",
    ]
    if strengths:
        for s in strengths:
            lines.append(f"- {s}")
    else:
        lines.append("- _Review job description and match manually_")
    lines.append("")

    lines.append("## Key Wins to Mention")
    lines.append("")
    for win in cv_data.get("key_wins", []):
        lines.append(f"- **{win['title']}:** {win['text']}")
    lines.append("")

    lines.append("## Potential Gaps — Prepare Answers")
    lines.append("")
    if gaps:
        for g in gaps:
            lines.append(f"- [ ] {g}")
            lines.append(f"  - _Your answer:_")
    else:
        lines.append("- No obvious gaps detected — review carefully")
    lines.append("")

    lines.extend([
        "## Questions to Ask",
        "",
        "### About the Role",
        "- What does success look like in the first 90 days?",
        "- How is the team currently structured?",
        "- What are the biggest challenges the team is facing?",
        "",
        "### About the Company",
        "- What's the company's growth trajectory for the next 12 months?",
        "- How does this role contribute to the company's strategic goals?",
        "",
        "### About the Culture",
        "- How would you describe the team culture?",
        "- What's the management style of the hiring manager?",
        "",
        "## STAR Stories to Prepare",
        "",
        "| Situation | Task | Action | Result |",
        "|-----------|------|--------|--------|",
        "| _Leadership challenge_ | | | |",
        "| _Technical win_ | | | |",
        "| _Team scaling_ | | | |",
        "| _Conflict resolution_ | | | |",
        "| _Revenue impact_ | | | |",
        "",
        "## Checklist",
        "",
        "- [ ] Research company recent news",
        "- [ ] Research interviewer(s) on LinkedIn",
        "- [ ] Prepare 2-minute elevator pitch",
        "- [ ] Review tailored CV",
        "- [ ] Test tech setup (if video call)",
        "",
        "---",
        "",
        "## Enhance with Gemini",
        "",
        "Paste this file + the job description into Gemini and ask:",
        "",
        "> Review my interview prep notes against the job description.",
        "> Add specific talking points, company insights, and tailor",
        "> the STAR stories to this role. Fill in the gaps section with",
        "> suggested answers.",
        "",
    ])

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: scripts/interview-prep.py <application-dir>")
        sys.exit(1)

    app_dir = sys.argv[1]
    if not os.path.isdir(app_dir):
        print(f"❌ Directory not found: {app_dir}")
        sys.exit(1)

    name = os.path.basename(app_dir)
    parts = name.split("-", 2)
    company = parts[2].replace("-", " ").title() if len(parts) > 2 else name

    position = "Unknown"
    for f in Path(app_dir).glob("CV - *.tex"):
        match = re.search(r"CV - .+? - (.+)\.tex", f.name)
        if match:
            position = match.group(1)
            break

    job_text = ""
    job_path = os.path.join(app_dir, "job.txt")
    if os.path.exists(job_path):
        with open(job_path, encoding="utf-8") as f:
            job_text = f.read()
    else:
        print("⚠️  No job.txt found — prep will be generic")

    cv_data = load_cv_data()
    job_sections = extract_job_sections(job_text)
    prep = generate_prep(cv_data, job_text, job_sections, company, position)

    out_path = os.path.join(app_dir, "prep.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(prep)

    print(f"✅ Generated {out_path}")
    print(f"   📋 {company} — {position}")
    print(f"   💡 Enhance with Gemini: paste prep.md + job.txt into Gemini")
    return 0


if __name__ == "__main__":
    sys.exit(main())
