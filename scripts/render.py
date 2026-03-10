#!/usr/bin/env python3
"""
Render CV.tex from data/cv.yml — single source of truth.

Usage:
    scripts/render.py                    # writes CV.tex
    scripts/render.py -o output.tex      # writes to custom path
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml required: pip install pyyaml")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import setup_logging


# ---------------------------------------------------------------------------
# LaTeX helpers
# ---------------------------------------------------------------------------


def escape_latex(text):
    """Escape LaTeX special characters in plain text."""
    text = text.replace("\\", "\\textbackslash{}")
    text = text.replace("&", "\\&")
    text = text.replace("%", "\\%")
    text = text.replace("$", "\\$")
    text = text.replace("#", "\\#")
    text = text.replace("_", "\\_")
    text = text.replace("~", "\\textasciitilde{}")
    text = text.replace("^", "\\textasciicircum{}")
    return text


def md_bold_to_latex(text):
    """Convert **bold** markers to \\textbf{} after LaTeX escaping."""
    return re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)


def process_text(text):
    """Escape LaTeX chars then convert markdown bold."""
    return md_bold_to_latex(escape_latex(text))


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def render_header(p):
    lines = []
    lines.append(f"\\name{{{p['first_name']}}}{{{p['last_name']}}}")
    lines.append(f"\\position{{{process_text(p['position'])}}}")
    lines.append(f"\\address{{{process_text(p['address'])}}}")
    lines.append("")
    lines.append(f"\\mobile{{{p['mobile']}}}")
    lines.append(f"\\email{{{p['email']}}}")
    lines.append(f"\\linkedin{{{p['linkedin']}}}")
    return "\n".join(lines)


def render_profile(profile):
    lines = [
        "\\cvsection{Profile}",
        "",
        "\\begin{cvparagraph}",
        process_text(profile),
        "\\end{cvparagraph}",
    ]
    return "\n".join(lines)


def render_skills(skills):
    lines = [
        "\\cvsection{Strategic Skills Portfolio}",
        "",
        "\\begin{cvskills}",
    ]
    for s in skills:
        lines.append("")
        lines.append("\\cvskill")
        lines.append(f"  {{{process_text(s['category'])}}}")
        lines.append(f"  {{{process_text(s['items'])}}}")
    lines.append("")
    lines.append("\\end{cvskills}")
    return "\n".join(lines)


def render_key_wins(wins):
    lines = [
        "\\cvsection{Strategic Key Wins \\& Business Impact}",
        "",
        "\\begin{cvparagraph}",
        "\\begin{itemize}[leftmargin=2ex, nosep, noitemsep]",
    ]
    for w in wins:
        title = process_text(w["title"])
        text = process_text(w["text"])
        lines.append(f"  \\item \\textbf{{{title}:}} {text}")
    lines.append("\\end{itemize}")
    lines.append("\\end{cvparagraph}")
    return "\n".join(lines)


def _render_entries_section(section_title, entries):
    """Render a cventries section (Work Experience, Early Career, etc.)."""
    lines = [
        f"\\cvsection{{{section_title}}}",
        "",
        "\\begin{cventries}",
    ]
    for e in entries:
        lines.append("")
        lines.append("%---------------------------------------------------------")
        lines.append("  \\cventry")
        lines.append(f"    {{{process_text(e['title'])}}}")
        lines.append(f"    {{{process_text(e['company'])}}}")
        lines.append(f"    {{{process_text(e['location'])}}}")
        lines.append(f"    {{{e['dates']}}}")
        items = e.get("items")
        if items:
            lines.append("    {")
            lines.append("      \\begin{cvitems}")
            for it in items:
                text = process_text(it["text"])
                label = it.get("label")
                if label:
                    label = process_text(label)
                    lines.append(f"        \\item {{\\textbf{{{label}:}} {text}}}")
                else:
                    lines.append(f"        \\item {{{text}}}")
            lines.append("      \\end{cvitems}")
            lines.append("    }")
        else:
            lines.append("    {}")
    lines.append("")
    lines.append("%---------------------------------------------------------")
    lines.append("\\end{cventries}")
    return "\n".join(lines)


def render_experience(entries):
    return _render_entries_section("Work Experience", entries)


def render_early_career(entries):
    return _render_entries_section("Early Career", entries)


def render_education(entries):
    lines = [
        "\\cvsection{Education}",
        "",
        "\\begin{cventries}",
    ]
    for e in entries:
        lines.append("")
        lines.append("%---------------------------------------------------------")
        lines.append("  \\cventry")
        lines.append(f"    {{{process_text(e['degree'])}}}")
        lines.append(f"    {{{process_text(e['school'])}}}")
        lines.append(f"    {{{process_text(e['location'])}}}")
        lines.append(f"    {{{e['dates']}}}")
        note = e.get("note")
        if note:
            lines.append("    {")
            lines.append("      \\begin{cvitems}")
            lines.append(f"        \\item {{{process_text(note)}}}")
            lines.append("      \\end{cvitems}")
            lines.append("    }")
        else:
            lines.append("    {}")
    lines.append("")
    lines.append("%---------------------------------------------------------")
    lines.append("\\end{cventries}")
    return "\n".join(lines)


def render_certifications(certs):
    lines = [
        "\\cvsection{Continuing Education}",
        "",
        "\\begin{cvhonors}",
    ]
    for c in certs:
        lines.append("")
        lines.append("%---------------------------------------------------------")
        lines.append("  \\cvhonor")
        lines.append(f"    {{{process_text(c['name'])}}}")
        lines.append(f"    {{{process_text(c['institution'])}}}")
        lines.append("    {}")
        lines.append(f"    {{{c['date']}}}")
    lines.append("")
    lines.append("%---------------------------------------------------------")
    lines.append("\\end{cvhonors}")
    return "\n".join(lines)


def render_awards_publications(awards, publications):
    lines = [
        "\\cvsection{Awards \\& Publications}",
        "",
        "\\begin{cvparagraph}",
        process_text(awards),
        "",
        process_text(publications),
        "\\end{cvparagraph}",
    ]
    return "\n".join(lines)


def render_languages_interests(languages, interests):
    lines = [
        "\\cvsection{Languages \\& Interests}",
        "",
        "\\begin{cvskills}",
        "",
        "\\cvskill",
        "  {Languages}",
        f"  {{{', '.join(escape_latex(l) for l in languages)}}}",
        "",
        "\\cvskill",
        "  {Interests}",
        f"  {{{', '.join(escape_latex(i) for i in interests)}}}",
        "",
        "\\end{cvskills}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cover Letter renderer
# ---------------------------------------------------------------------------


def render_coverletter(cl_data, personal, theme=None, pdfa=False, draft=False):
    """Render CoverLetter.tex from cover letter YAML + personal info."""
    cl_defaults = {**DEFAULT_CL_THEME, **(cl_data.get("theme") or {})}
    t = {**cl_defaults, **(theme or {})}
    sections = []

    # Preamble
    sections.append(
        build_preamble(
            t,
            pdfa=pdfa,
            comment="Cover Letter (template)",
            draft=draft,
            personal=personal,
        )
    )

    # Personal information
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tPERSONAL INFORMATION")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_header(personal))
    sections.append("")
    sections.append("")

    # Letter information
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tLETTER INFORMATION")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    r = cl_data["recipient"]
    sections.append("\\recipient")
    sections.append(f"  {{{process_text(r['name'])}}}")
    sections.append(f"  {{{process_text(r['company'])}}}")
    sections.append("\\letterdate{\\today}")
    sections.append(f"\\lettertitle{{{process_text(cl_data['title'])}}}")
    sections.append(f"\\letteropening{{{process_text(cl_data['opening'])}}}")
    sections.append(f"\\letterclosing{{{process_text(cl_data['closing'])}}}")
    sections.append("")
    sections.append("")

    # Begin document
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("\\begin{document}")
    sections.append("")
    sections.append("\\makecvheader[R]")
    sections.append("")
    sections.append("\\makecvfooter")
    sections.append("  {\\today}")
    sections.append(
        f"  {{{personal['first_name']} {personal['last_name']}~~~·~~~Cover Letter}}"
    )
    sections.append("  {}")
    sections.append("")
    sections.append("\\makelettertitle")
    sections.append("")

    # Letter content
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tLETTER CONTENT")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("\\begin{cvletter}")
    sections.append("")

    for s in cl_data["sections"]:
        sections.append(f"\\lettersection{{{process_text(s['title'])}}}")
        sections.append(process_text(s["content"]).replace("\n", "\n\n"))
        sections.append("")

    if "closing_paragraph" in cl_data:
        sections.append(process_text(cl_data["closing_paragraph"]).replace("\n", "\n\n"))
        sections.append("")

    sections.append("\\end{cvletter}")
    sections.append("")
    sections.append("")

    # Closing
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("\\makeletterclosing")
    sections.append("")
    sections.append("\\end{document}")
    sections.append("")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

DEFAULT_THEME = {
    "color": "1A5276",
    "font_size": "10pt",
    "paper": "a4paper",
    "geometry": "left=1.4cm, top=1.0cm, right=1.4cm, bottom=1.0cm, footskip=.5cm",
    "highlight": True,
}

DEFAULT_CL_THEME = {
    "color": "1A5276",
    "font_size": "10pt",
    "paper": "a4paper",
    "geometry": "left=1.4cm, top=.8cm, right=1.4cm, bottom=1.2cm, footskip=.5cm",
    "highlight": True,
}


def build_preamble(
    theme, pdfa=False, comment="Resume (2 pages)", draft=False, personal=None
):
    """Build LaTeX preamble with theme settings."""
    t = {**DEFAULT_THEME, **(theme or {})}
    highlight = "true" if t["highlight"] else "false"
    pdfa_block = ""
    if pdfa:
        pdfa_block = """
% PDF/A compliance for ATS systems
\\usepackage[a-3u]{pdfx}
"""
    draft_block = ""
    if draft:
        draft_block = """
% Draft watermark
\\usepackage{draftwatermark}
\\SetWatermarkText{DRAFT}
\\SetWatermarkScale{1.5}
\\SetWatermarkColor[gray]{0.92}
"""
    metadata_block = ""
    name = ""
    if personal:
        name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        keywords = ""
        if "skills" in personal:
            skill_keywords = []
            for cat in personal["skills"][:5]:
                skill_keywords.extend(
                    [item.strip() for item in cat.get("items", "").split(",")]
                )
            keywords = ", ".join(skill_keywords[:15])
        position = personal.get("position", "")
        metadata_block = f"""\
% PDF metadata
\\hypersetup{{
  pdfauthor={{{name}}},
  pdftitle={{{position} - {name}}},
  pdfsubject={{Resume}},
  pdfkeywords={{{keywords}}},
  pdfcreator={{scripts/render.py}},
}}
"""
    return f"""\
%!TEX TS-program = xelatex
%!TEX encoding = UTF-8 Unicode
% {name} - {comment}
% Auto-generated from data/ by scripts/render.py
% Using Awesome-CV template by posquit0
% https://github.com/posquit0/Awesome-CV


%-------------------------------------------------------------------------------
% CONFIGURATIONS
%-------------------------------------------------------------------------------
\\documentclass[{t["font_size"]}, {t["paper"]}]{{awesome-cv}}

\\geometry{{{t["geometry"]}}}
{pdfa_block}{draft_block}% Theme color
\\definecolor{{awesome}}{{HTML}}{{{t["color"]}}}

% Set false if you don't want to highlight section with awesome color
\\setbool{{acvSectionColorHighlight}}{{{highlight}}}

\\renewcommand{{\\acvHeaderSocialSep}}{{\\quad\\textbar\\quad}}

% Hyperref for metadata
\\usepackage{{hyperref}}
{metadata_block}
"""


def _build_footer(personal: dict | None = None) -> str:
    """Build CV footer with dynamic name from personal data."""
    if personal:
        name = f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
    else:
        name = ""
    return (
        "\\makecvfooter\n"
        "  {\\today}\n"
        f"  {{{name}~~~·~~~Résumé}}\n"
        "  {\\thepage}\n"
    )


def render_cv(data, theme=None, pdfa=False, draft=False):
    """Render full CV.tex content from parsed YAML data."""
    sections = []

    # Preamble
    sections.append(
        build_preamble(theme, pdfa=pdfa, draft=draft, personal=data.get("personal"))
    )

    # Personal information
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tPERSONAL INFORMATION")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_header(data["personal"]))
    sections.append("")
    sections.append("")

    # Begin document
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("\\begin{document}")
    sections.append("")
    sections.append("% Print the header with above personal information")
    sections.append("\\makecvheader[C]")
    sections.append("")
    sections.append("% Print the footer with 3 arguments(<left>, <center>, <right>)")
    sections.append(_build_footer(data.get("personal")))
    sections.append("")

    # Profile
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tPROFILE")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_profile(data["profile"]))
    sections.append("")
    sections.append("")

    # Skills
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tSTRATEGIC SKILLS PORTFOLIO")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_skills(data["skills"]))
    sections.append("")
    sections.append("")

    # Key Wins
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tSTRATEGIC KEY WINS & BUSINESS IMPACT")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_key_wins(data["key_wins"]))
    sections.append("")
    sections.append("")

    # Work Experience
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tWORK EXPERIENCE")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_experience(data["experience"]))
    sections.append("")
    sections.append("\\newpage")
    sections.append("")

    # Early Career
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tEARLY CAREER")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_early_career(data["early_career"]))
    sections.append("")
    sections.append("")

    # Education
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tEDUCATION")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_education(data["education"]))
    sections.append("")
    sections.append("")

    # Certifications
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tCONTINUING EDUCATION")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_certifications(data["certifications"]))
    sections.append("")
    sections.append("")

    # Awards & Publications
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tAWARDS & PUBLICATIONS")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_awards_publications(data["awards"], data["publications"]))
    sections.append("")
    sections.append("")

    # Languages & Interests
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("%\tLANGUAGES & INTERESTS")
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append(render_languages_interests(data["languages"], data["interests"]))
    sections.append("")
    sections.append("")

    # End document
    sections.append(
        "%-------------------------------------------------------------------------------"
    )
    sections.append("\\end{document}")
    sections.append("")

    return "\n".join(sections)


MODERNCV_TEMPLATES = ("classic", "casual", "banking", "oldstyle", "fancy")


def _moderncv_entry_items(items: list) -> str:
    """Render experience items as LaTeX itemize for ModernCV."""
    if not items:
        return ""
    lines = ["\\begin{itemize}[noitemsep,topsep=2pt]"]
    for it in items:
        text = process_text(it["text"]) if isinstance(it, dict) else process_text(str(it))
        label = it.get("label") if isinstance(it, dict) else None
        if label:
            lines.append(f"  \\item \\textbf{{{process_text(label)}:}} {text}")
        else:
            lines.append(f"  \\item {text}")
    lines.append("\\end{itemize}")
    return "\n".join(lines)


def render_cv_moderncv(data: dict, style: str = "classic", color: str = "blue") -> str:
    """Render CV.tex using the ModernCV package (TeX Live built-in)."""
    p = data["personal"]
    first = escape_latex(p["first_name"])
    last = escape_latex(p["last_name"])
    full_name = f"{p['first_name']} {p['last_name']}"

    out: list[str] = []

    out.append(f"""\
%!TEX TS-program = xelatex
%!TEX encoding = UTF-8 Unicode
% {full_name} -- Resume (ModernCV template)
% Auto-generated from data/ by scripts/render.py

\\documentclass[11pt,a4paper,sans]{{moderncv}}
\\moderncvstyle{{{style}}}
\\moderncvcolor{{{color}}}

\\usepackage[scale=0.85,top=1.2cm,bottom=1.2cm]{{geometry}}
\\usepackage{{xltxtra,xunicode}}
\\usepackage[T1]{{fontenc}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{enumitem}}

\\name{{{first}}}{{{last}}}
\\title{{{process_text(p["position"])}}}
\\address{{{escape_latex(p["address"])}}}{{}}{{}}
\\phone[mobile]{{{escape_latex(p["mobile"])}}}
\\email{{{escape_latex(p["email"])}}}
\\social[linkedin]{{{escape_latex(p["linkedin"])}}}
""")

    out.append("\\begin{document}")
    out.append("\\makecvtitle")
    out.append("")

    out.append("\\section{Profile}")
    out.append(f"\\cvitem{{}}{{{process_text(data['profile'])}}}")
    out.append("")

    out.append("\\section{Skills}")
    for s in data.get("skills", []):
        out.append(f"\\cvitem{{{process_text(s['category'])}}}{{{process_text(s['items'])}}}")
    out.append("")

    if data.get("key_wins"):
        out.append("\\section{Key Achievements}")
        for w in data["key_wins"]:
            title = process_text(w["title"])
            text = process_text(w["text"])
            out.append(f"\\cvitem{{\\textbf{{{title}}}}}{{{text}}}")
        out.append("")

    out.append("\\section{Work Experience}")
    for e in data.get("experience", []):
        items_tex = _moderncv_entry_items(e.get("items", []))
        out.append(
            f"\\cventry{{{e['dates']}}}{{{process_text(e['title'])}}}"
            f"{{{process_text(e['company'])}}}{{{process_text(e['location'])}}}{{}}{{"
        )
        if items_tex:
            out.append(items_tex)
        out.append("}")
    out.append("")

    if data.get("early_career"):
        out.append("\\section{Early Career}")
        for e in data["early_career"]:
            out.append(
                f"\\cventry{{{e['dates']}}}{{{process_text(e['title'])}}}"
                f"{{{process_text(e['company'])}}}{{{process_text(e['location'])}}}{{}}{{}}",
            )
        out.append("")

    out.append("\\section{Education}")
    for e in data.get("education", []):
        note = process_text(e["note"]) if e.get("note") else ""
        out.append(
            f"\\cventry{{{e['dates']}}}{{{process_text(e['degree'])}}}"
            f"{{{process_text(e['school'])}}}{{{process_text(e['location'])}}}{{}}{{{note}}}",
        )
    out.append("")

    if data.get("certifications"):
        out.append("\\section{Certifications}")
        for c in data["certifications"]:
            out.append(f"\\cvitem{{{c['date']}}}{{{process_text(c['name'])} -- {process_text(c['institution'])}}}")
        out.append("")

    if data.get("languages"):
        out.append("\\section{Languages}")
        out.append(f"\\cvitem{{}}{{{', '.join(escape_latex(l) for l in data['languages'])}}}")
        out.append("")

    out.append("\\end{document}")
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Deedy-style renderer (article, 2-column, 1-page compact)
# ---------------------------------------------------------------------------


def render_cv_deedy(data: dict) -> str:
    """Render a compact 1-page Deedy-inspired CV using article + multicol."""
    p = data["personal"]
    full_name = f"{p['first_name']} {p['last_name']}"

    out: list[str] = []

    out.append(f"""\
%!TEX TS-program = xelatex
%!TEX encoding = UTF-8 Unicode
% {full_name} -- Resume (Deedy-style, 1 page)
% Auto-generated from data/ by scripts/render.py

\\documentclass[a4paper,10pt]{{article}}
\\usepackage[left=1.4cm,right=1.4cm,top=1.0cm,bottom=1.0cm]{{geometry}}
\\usepackage{{xltxtra,xunicode}}
\\usepackage{{fontspec}}
\\usepackage{{multicol}}
\\usepackage{{titlesec}}
\\usepackage{{enumitem}}
\\usepackage{{hyperref}}
\\usepackage{{xcolor}}

\\definecolor{{accent}}{{HTML}}{{1A5276}}
\\setlength{{\\columnsep}}{{1.8em}}
\\setlength{{\\columnseprule}}{{0.4pt}}

\\titleformat{{\\section}}{{\\normalsize\\bfseries\\color{{accent}}}}{{}}{{0em}}{{}}[\\titlerule]
\\titlespacing{{\\section}}{{0pt}}{{5pt}}{{3pt}}

\\setlist[itemize]{{noitemsep,topsep=2pt,leftmargin=1.2em,label={{\\textbullet}}}}

\\hypersetup{{hidelinks}}
\\pagestyle{{empty}}
""")

    out.append("\\begin{document}")
    out.append("")

    out.append("% ---- Header ----")
    out.append("{\\centering")
    out.append(f"  {{\\LARGE\\bfseries {escape_latex(full_name)}}}\\\\[3pt]")
    contact = (
        f"{escape_latex(p['address'])} "
        f"\\quad\\textbar\\quad {escape_latex(p['mobile'])} "
        f"\\quad\\textbar\\quad \\href{{mailto:{escape_latex(p['email'])}}}{{{escape_latex(p['email'])}}} "
        f"\\quad\\textbar\\quad linkedin.com/in/{escape_latex(p['linkedin'])}"
    )
    out.append(f"  {{\\small {contact}}}\\\\[2pt]")
    out.append(f"  {{\\itshape\\small {process_text(p['position'])}}}")
    out.append("\\par}")
    out.append("\\vspace{5pt}")
    out.append("\\hrule")
    out.append("\\vspace{8pt}")
    out.append("")

    out.append("\\begin{multicols}{2}")
    out.append("")

    profile_text = data["profile"]
    if len(profile_text) > 500:
        profile_text = profile_text[:497] + "..."
    out.append("\\section{Profile}")
    out.append(f"{{\\small {process_text(profile_text)}}}")
    out.append("")

    out.append("\\section{Skills}")
    for s in data.get("skills", []):
        out.append(f"{{\\small\\textbf{{{process_text(s['category'])}:}} {process_text(s['items'])}}}\\\\[2pt]")
    out.append("")

    out.append("\\section{Education}")
    for e in data.get("education", []):
        out.append(
            f"{{\\small\\textbf{{{process_text(e['degree'])}}}}}\\\\[1pt]"
            f"{{\\small {process_text(e['school'])}, {process_text(e['location'])} · {e['dates']}}}\\\\[3pt]"
        )
    out.append("")

    if data.get("languages"):
        out.append("\\section{Languages}")
        out.append(f"{{\\small {', '.join(escape_latex(l) for l in data['languages'])}}}")
        out.append("")

    out.append("\\columnbreak")
    out.append("")

    out.append("\\section{Experience}")
    for e in data.get("experience", [])[:3]:
        out.append(
            f"{{\\small\\textbf{{{process_text(e['title'])}}} · {process_text(e['company'])}, "
            f"{process_text(e['location'])}}}\\\\[1pt]"
            f"{{\\footnotesize\\itshape {e['dates']}}}\\\\[1pt]"
        )
        items = e.get("items", [])
        if items:
            out.append("\\begin{itemize}[noitemsep,topsep=1pt]")
            for it in items[:4]:
                text = process_text(it["text"]) if isinstance(it, dict) else process_text(str(it))
                out.append(f"  \\item {{\\small {text}}}")
            out.append("\\end{itemize}")
        out.append("\\vspace{4pt}")
    out.append("")

    if data.get("key_wins"):
        out.append("\\section{Key Wins}")
        out.append("\\begin{itemize}")
        for w in data["key_wins"][:3]:
            title = process_text(w["title"])
            text = process_text(w["text"])
            out.append(f"  \\item {{\\small\\textbf{{{title}:}} {text}}}")
        out.append("\\end{itemize}")
        out.append("")

    out.append("\\end{multicols}")
    out.append("")
    out.append("\\end{document}")
    out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(
        description="Render CV.tex or CoverLetter.tex from YAML data"
    )
    parser.add_argument(
        "-o", "--output", help="Output .tex file (auto-detected if omitted)"
    )
    parser.add_argument(
        "-d",
        "--data",
        default="data/cv.yml",
        help="YAML data file (default: data/cv.yml)",
    )
    parser.add_argument(
        "-l", "--lang", help="Language code (e.g., fr). Loads data/{stem}-{lang}.yml"
    )
    parser.add_argument(
        "-t", "--theme", help="Theme YAML file (overrides color, font size, etc.)"
    )
    parser.add_argument(
        "--pdfa", action="store_true", help="Enable PDF/A compliance (for ATS systems)"
    )
    parser.add_argument("--draft", action="store_true", help="Add DRAFT watermark")
    parser.add_argument(
        "--cv-data",
        help="CV YAML for personal info (cover letter mode, default: data/cv.yml)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--template",
        default="awesome-cv",
        choices=["awesome-cv", "moderncv", "deedy"],
        help="LaTeX template: awesome-cv (default), moderncv, deedy",
    )
    args = parser.parse_args()

    log = setup_logging(args.verbose)

    # Resolve data path with optional language override
    base = Path(args.data)
    if args.lang:
        stem = base.stem  # "cv" or "coverletter"
        data_path = base.parent / f"{stem}-{args.lang}.yml"
        print(f"🌐 Language: {args.lang}")
    else:
        data_path = base

    if not data_path.exists():
        log.error("Data file not found: %s", data_path)
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        log.error("YAML file is empty or invalid: %s", data_path)
        sys.exit(1)

    if not isinstance(data, dict):
        log.error("YAML file must be a mapping at the top level: %s", data_path)
        sys.exit(1)

    # Auto-detect: cover letter has "recipient" key, CV has "profile" key
    is_coverletter = "recipient" in data

    # Load and apply theme if provided
    theme = {}
    if args.theme:
        theme_path = Path(args.theme)
        if theme_path.exists():
            with open(theme_path, encoding="utf-8") as f:
                theme = yaml.safe_load(f) or {}
            print(f"🎨 Applying theme from {theme_path}")

    # Default output based on document type
    default_output = "CoverLetter.tex" if is_coverletter else "CV.tex"
    out_path = Path(args.output or default_output)

    # Also check for theme.yml next to the output file
    if not theme:
        auto_theme = out_path.parent / "theme.yml"
        if auto_theme.exists():
            with open(auto_theme, encoding="utf-8") as f:
                theme = yaml.safe_load(f) or {}
            print(f"🎨 Auto-detected theme: {auto_theme}")

    if args.pdfa:
        print("📄 PDF/A mode enabled")
    if args.draft:
        print("📝 Draft watermark enabled")
    if args.template != "awesome-cv":
        print(f"📐 Template: {args.template}")

    if args.template == "moderncv":
        if is_coverletter:
            log.error("ModernCV cover letter not supported — use awesome-cv for cover letters")
            sys.exit(1)
        default_output = "CV-moderncv.tex"
        out_path = Path(args.output or default_output)
        output = render_cv_moderncv(data)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ Rendered {out_path} from {data_path}")
        return 0

    if args.template == "deedy":
        if is_coverletter:
            log.error("Deedy cover letter not supported — use awesome-cv for cover letters")
            sys.exit(1)
        default_output = "CV-deedy.tex"
        out_path = Path(args.output or default_output)
        output = render_cv_deedy(data)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ Rendered {out_path} from {data_path}")
        return 0

    if is_coverletter:
        # Load personal info from CV data
        if args.cv_data:
            cv_data_path = Path(args.cv_data)
        elif args.lang:
            cv_data_path = data_path.parent / f"cv-{args.lang}.yml"
        else:
            cv_data_path = data_path.parent / "cv.yml"

        if not cv_data_path.exists():
            log.error("CV data not found: %s", cv_data_path)
            log.error("Use --cv-data to specify the CV YAML file for personal info.")
            sys.exit(1)

        with open(cv_data_path, encoding="utf-8") as f:
            cv_data = yaml.safe_load(f)

        if not cv_data or not isinstance(cv_data, dict):
            log.error("CV YAML file is empty or invalid: %s", cv_data_path)
            sys.exit(1)

        if "personal" not in cv_data:
            log.error("Missing required key 'personal' in %s", cv_data_path)
            sys.exit(1)

        cl_required_keys = ["recipient", "title", "opening", "closing", "sections"]
        for key in cl_required_keys:
            if key not in data:
                log.error("Missing required key '%s' in %s", key, data_path)
                sys.exit(1)

        output = render_coverletter(
            data, cv_data["personal"], theme=theme, pdfa=args.pdfa, draft=args.draft
        )
        print(f"📨 Cover letter mode (personal info from {cv_data_path})")
    else:
        cv_required_keys = [
            "personal",
            "profile",
            "skills",
            "key_wins",
            "experience",
            "early_career",
            "education",
            "certifications",
            "awards",
            "publications",
            "languages",
            "interests",
        ]
        for key in cv_required_keys:
            if key not in data:
                log.error("Missing required key '%s' in %s", key, data_path)
                sys.exit(1)

        output = render_cv(data, theme=theme, pdfa=args.pdfa, draft=args.draft)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ Rendered {out_path} from {data_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
