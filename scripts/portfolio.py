#!/usr/bin/env python3
"""Generate a static HTML portfolio page from data/cv.yml.

Usage:
    python scripts/portfolio.py [-o OUTPUT] [--lang en|fr]

Default output: portfolio/index.html
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import tempfile
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import REPO_ROOT, require_yaml


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text), quote=True)


def _bold_to_strong(text: str) -> str:
    """Convert **bold** markdown to <strong> tags (after HTML-escaping)."""
    escaped = _esc(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _item_text(item: object) -> str:
    """Extract plain text from an experience item (dict or string)."""
    if isinstance(item, dict):
        return str(item.get("text", item.get("label", "")))
    return str(item)


def _render_css() -> str:
    return """
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            font-size: 16px;
            line-height: 1.6;
            color: #2d3748;
            background: #f7f8fc;
        }
        a { color: #3182ce; text-decoration: none; }
        a:hover { text-decoration: underline; }

        /* Hero */
        .hero {
            background: #1A2744;
            color: #fff;
            padding: 56px 0 48px;
            text-align: center;
        }
        .hero h1 { font-size: 2.4rem; font-weight: 700; letter-spacing: -0.5px; }
        .hero .position {
            font-size: 1.15rem;
            color: #90cdf4;
            margin-top: 6px;
            font-weight: 400;
        }
        .hero .contact {
            margin-top: 20px;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 18px;
            font-size: 0.92rem;
        }
        .hero .contact a { color: #bee3f8; }
        .hero .contact a:hover { color: #fff; }
        .contact-item { display: flex; align-items: center; gap: 5px; }

        /* Layout */
        .container { max-width: 900px; margin: 0 auto; padding: 0 20px; }
        main { padding: 40px 0 60px; }
        section { margin-bottom: 40px; }
        h2 {
            font-size: 1.3rem;
            font-weight: 700;
            color: #1A2744;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            border-bottom: 2px solid #1A2744;
            padding-bottom: 8px;
            margin-bottom: 20px;
        }

        /* About */
        .about-text {
            background: #fff;
            border-radius: 8px;
            padding: 22px 26px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.07);
            font-size: 1rem;
            color: #444;
            line-height: 1.75;
        }

        /* Skills */
        .skills-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 16px;
        }
        .skill-card {
            background: #fff;
            border-radius: 8px;
            padding: 18px 20px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.07);
        }
        .skill-card h3 {
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #1A2744;
            margin-bottom: 10px;
        }
        .skill-tags { display: flex; flex-wrap: wrap; gap: 7px; }
        .skill-tag {
            background: #ebf4ff;
            color: #2b6cb0;
            border-radius: 4px;
            padding: 3px 10px;
            font-size: 0.82rem;
            font-weight: 500;
        }

        /* Experience */
        .exp-entry {
            background: #fff;
            border-radius: 8px;
            padding: 22px 26px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.07);
            margin-bottom: 16px;
        }
        .exp-header { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; }
        .exp-title { font-size: 1.05rem; font-weight: 700; color: #1A2744; }
        .exp-company { font-size: 0.97rem; font-weight: 600; color: #4a5568; margin-top: 2px; }
        .exp-dates { font-size: 0.85rem; color: #718096; white-space: nowrap; }
        .exp-items {
            margin-top: 14px;
            list-style: none;
            padding: 0;
        }
        .exp-items li {
            position: relative;
            padding-left: 18px;
            margin-bottom: 7px;
            font-size: 0.95rem;
            color: #444;
        }
        .exp-items li::before {
            content: "▸";
            position: absolute;
            left: 0;
            color: #3182ce;
            font-size: 0.8rem;
            top: 2px;
        }

        /* Education */
        .edu-entry {
            background: #fff;
            border-radius: 8px;
            padding: 18px 24px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.07);
            margin-bottom: 12px;
        }
        .edu-degree { font-weight: 700; color: #1A2744; }
        .edu-school { color: #4a5568; font-size: 0.95rem; margin-top: 3px; }
        .edu-dates { color: #718096; font-size: 0.85rem; margin-top: 2px; }

        /* Languages */
        .lang-list { display: flex; flex-wrap: wrap; gap: 12px; }
        .lang-badge {
            background: #1A2744;
            color: #fff;
            border-radius: 6px;
            padding: 6px 18px;
            font-size: 0.9rem;
            font-weight: 600;
            letter-spacing: 0.04em;
        }

        /* Footer */
        footer {
            background: #1A2744;
            color: #90cdf4;
            text-align: center;
            padding: 20px;
            font-size: 0.85rem;
        }

        @media (max-width: 600px) {
            .hero h1 { font-size: 1.8rem; }
            .exp-header { flex-direction: column; }
        }
    """


def _render_hero(personal: dict) -> str:
    first = _esc(personal.get("first_name", ""))
    last = _esc(personal.get("last_name", ""))
    position = _esc(personal.get("position", ""))
    email = personal.get("email", "")
    linkedin = personal.get("linkedin", "")
    github = personal.get("github", "")
    address = _esc(personal.get("address", ""))

    contacts = []
    if email:
        contacts.append(f'<span class="contact-item"><a href="mailto:{_esc(email)}">{_esc(email)}</a></span>')
    if linkedin:
        contacts.append(
            f'<span class="contact-item">'
            f'<a href="https://linkedin.com/in/{_esc(linkedin)}" target="_blank">'
            f"LinkedIn/{_esc(linkedin)}</a></span>"
        )
    if github:
        contacts.append(
            f'<span class="contact-item">'
            f'<a href="https://github.com/{_esc(github)}" target="_blank">'
            f"GitHub/{_esc(github)}</a></span>"
        )
    if address:
        contacts.append(f'<span class="contact-item">{address}</span>')

    contact_html = "\n".join(contacts)
    return f"""
    <header class="hero">
      <div class="container">
        <h1>{first} {last}</h1>
        <p class="position">{position}</p>
        <div class="contact">
          {contact_html}
        </div>
      </div>
    </header>"""


def _render_about(profile: str) -> str:
    if not profile:
        return ""
    return f"""
    <section id="about">
      <h2>About</h2>
      <div class="about-text">{_bold_to_strong(profile)}</div>
    </section>"""


def _render_skills(skills: list) -> str:
    if not skills:
        return ""
    cards = []
    for skill in skills:
        category = _esc(skill.get("category", ""))
        items_raw = skill.get("items", "")
        # Items can be a comma-separated string or a list
        if isinstance(items_raw, list):
            items = [str(i).strip() for i in items_raw]
        else:
            items = [i.strip() for i in str(items_raw).split(",")]
        tags = "\n".join(f'          <span class="skill-tag">{_esc(i)}</span>' for i in items if i)
        cards.append(
            f'      <div class="skill-card">\n'
            f"        <h3>{category}</h3>\n"
            f'        <div class="skill-tags">\n{tags}\n        </div>\n'
            f"      </div>"
        )
    cards_html = "\n".join(cards)
    return f"""
    <section id="skills">
      <h2>Skills</h2>
      <div class="skills-grid">
{cards_html}
      </div>
    </section>"""


def _render_experience(experience: list, limit: int = 5) -> str:
    if not experience:
        return ""
    entries = []
    for exp in experience[:limit]:
        title = _esc(exp.get("title", ""))
        company = _esc(exp.get("company", ""))
        dates = _esc(str(exp.get("dates", "")).replace("--", "–"))
        items = exp.get("items", []) or []

        items_html = ""
        if items:
            bullets = "\n".join(f"            <li>{_bold_to_strong(_item_text(item))}</li>" for item in items)
            items_html = f'          <ul class="exp-items">\n{bullets}\n          </ul>'

        entries.append(
            f'      <div class="exp-entry">\n'
            f'        <div class="exp-header">\n'
            f"          <div>\n"
            f'            <div class="exp-title">{title}</div>\n'
            f'            <div class="exp-company">{company}</div>\n'
            f"          </div>\n"
            f'          <span class="exp-dates">{dates}</span>\n'
            f"        </div>\n"
            f"{items_html}\n"
            f"      </div>"
        )

    entries_html = "\n".join(entries)
    return f"""
    <section id="experience">
      <h2>Experience</h2>
{entries_html}
    </section>"""


def _render_education(education: list) -> str:
    if not education:
        return ""
    entries = []
    for edu in education:
        degree = _esc(edu.get("degree", ""))
        school = _esc(edu.get("school", ""))
        location = _esc(edu.get("location", ""))
        dates = _esc(str(edu.get("dates", "")).replace("--", "–"))
        school_loc = f"{school}, {location}" if location else school
        entries.append(
            f'      <div class="edu-entry">\n'
            f'        <div class="edu-degree">{degree}</div>\n'
            f'        <div class="edu-school">{school_loc}</div>\n'
            f'        <div class="edu-dates">{dates}</div>\n'
            f"      </div>"
        )
    entries_html = "\n".join(entries)
    return f"""
    <section id="education">
      <h2>Education</h2>
{entries_html}
    </section>"""


def _render_languages(languages: list) -> str:
    if not languages:
        return ""
    badges = "\n".join(f'        <span class="lang-badge">{_esc(str(lang))}</span>' for lang in languages)
    return f"""
    <section id="languages">
      <h2>Languages</h2>
      <div class="lang-list">
{badges}
      </div>
    </section>"""


def generate_html(cv: dict) -> str:
    personal = cv.get("personal", {})
    profile = cv.get("profile", "")
    skills = cv.get("skills", []) or []
    experience = cv.get("experience", []) or []
    education = cv.get("education", []) or []
    languages = cv.get("languages", []) or []

    first = _esc(personal.get("first_name", ""))
    last = _esc(personal.get("last_name", ""))
    position = _esc(personal.get("position", ""))
    title_tag = f"{first} {last} — {position}" if position else f"{first} {last}"

    css = _render_css()
    hero = _render_hero(personal)
    about = _render_about(profile)
    skills_section = _render_skills(skills)
    exp_section = _render_experience(experience)
    edu_section = _render_education(education)
    lang_section = _render_languages(languages)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{title_tag}">
  <title>{title_tag}</title>
  <style>{css}
  </style>
</head>
<body>
{hero}
  <div class="container">
    <main>
{about}
{skills_section}
{exp_section}
{edu_section}
{lang_section}
    </main>
  </div>
  <footer>
    <div class="container">{first} {last} &mdash; Generated from CV data</div>
  </footer>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a static HTML portfolio from data/cv.yml")
    parser.add_argument(
        "-o",
        "--output",
        default=str(REPO_ROOT / "portfolio" / "index.html"),
        help="Output file path (default: portfolio/index.html)",
    )
    parser.add_argument(
        "--lang",
        choices=["en", "fr"],
        default="en",
        help="Language variant: en (cv.yml) or fr (cv-fr.yml)",
    )
    args = parser.parse_args()

    yaml = require_yaml()

    data_file = "cv-fr.yml" if args.lang == "fr" else "cv.yml"
    cv_path = REPO_ROOT / "data" / data_file

    if not cv_path.exists():
        print(f"Error: {cv_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(cv_path, encoding="utf-8") as f:
        cv = yaml.safe_load(f) or {}

    html_content = generate_html(cv)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(suffix=".html", dir=output_path.parent, prefix=".portfolio_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_content)
        os.replace(tmp_path, output_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    print(f"Portfolio generated: {output_path}")


if __name__ == "__main__":
    main()
