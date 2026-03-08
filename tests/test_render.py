"""Unit tests for scripts/render.py — LaTeX rendering helpers."""

import sys
from pathlib import Path

import pytest

# render.py lives in scripts/, not scripts/lib/, so we import it directly.
# conftest.py already added scripts/ to sys.path.
import render as render_mod
from render import (
    escape_latex,
    md_bold_to_latex,
    process_text,
    render_profile,
    render_skills,
)


# ---------------------------------------------------------------------------
# escape_latex
# ---------------------------------------------------------------------------


class TestEscapeLatex:
    def test_ampersand(self):
        assert escape_latex("AT&T") == "AT\\&T"

    def test_percent(self):
        assert escape_latex("100%") == "100\\%"

    def test_hash(self):
        assert escape_latex("C#") == "C\\#"

    def test_dollar(self):
        assert escape_latex("$100") == "\\$100"

    def test_underscore(self):
        assert escape_latex("snake_case") == "snake\\_case"

    def test_backslash(self):
        # Backslash must be escaped first to avoid double-escaping.
        assert escape_latex("a\\b") == "a\\textbackslash{}b"

    def test_tilde(self):
        assert escape_latex("~home") == "\\textasciitilde{}home"

    def test_caret(self):
        assert escape_latex("x^2") == "x\\textasciicircum{}2"

    def test_plain_text_unchanged(self):
        assert escape_latex("Hello World") == "Hello World"

    def test_multiple_special_chars(self):
        result = escape_latex("50% & more")
        assert "\\%" in result
        assert "\\&" in result

    def test_empty_string(self):
        assert escape_latex("") == ""


# ---------------------------------------------------------------------------
# md_bold_to_latex
# ---------------------------------------------------------------------------


class TestMdBoldToLatex:
    def test_single_bold(self):
        assert md_bold_to_latex("**bold**") == "\\textbf{bold}"

    def test_bold_in_sentence(self):
        result = md_bold_to_latex("This is **important** text")
        assert result == "This is \\textbf{important} text"

    def test_multiple_bold_markers(self):
        result = md_bold_to_latex("**a** and **b**")
        assert result == "\\textbf{a} and \\textbf{b}"

    def test_no_bold_markers_unchanged(self):
        assert md_bold_to_latex("plain text") == "plain text"

    def test_empty_string(self):
        assert md_bold_to_latex("") == ""


# ---------------------------------------------------------------------------
# process_text (escape then bold)
# ---------------------------------------------------------------------------


class TestProcessText:
    def test_bold_after_escape(self):
        # The & should be escaped; then bold markers converted.
        result = process_text("**AT&T**")
        assert result == "\\textbf{AT\\&T}"

    def test_percent_in_bold(self):
        result = process_text("**100%**")
        assert result == "\\textbf{100\\%}"

    def test_plain_bold(self):
        result = process_text("**hello**")
        assert result == "\\textbf{hello}"

    def test_no_special_chars(self):
        result = process_text("Hello World")
        assert result == "Hello World"


# ---------------------------------------------------------------------------
# render_profile
# ---------------------------------------------------------------------------


class TestRenderProfile:
    SAMPLE_PROFILE = (
        "Experienced software engineer with a focus on distributed systems "
        "and cloud infrastructure."
    )

    def test_contains_cvsection(self):
        output = render_profile(self.SAMPLE_PROFILE)
        assert "\\cvsection{Profile}" in output

    def test_contains_cvparagraph_env(self):
        output = render_profile(self.SAMPLE_PROFILE)
        assert "\\begin{cvparagraph}" in output
        assert "\\end{cvparagraph}" in output

    def test_profile_text_is_included(self):
        output = render_profile(self.SAMPLE_PROFILE)
        assert self.SAMPLE_PROFILE in output

    def test_special_chars_are_escaped(self):
        profile = "Works with 50% efficiency & great results"
        output = render_profile(profile)
        assert "\\%" in output
        assert "\\&" in output
        # Raw unescaped versions must not appear (except inside the escape sequences).
        assert "50%" not in output
        assert " & " not in output

    def test_bold_is_converted(self):
        profile = "Expert in **Python** and distributed systems"
        output = render_profile(profile)
        assert "\\textbf{Python}" in output

    def test_returns_string(self):
        assert isinstance(render_profile(self.SAMPLE_PROFILE), str)

    def test_nonempty_output(self):
        assert len(render_profile(self.SAMPLE_PROFILE)) > 0


# ---------------------------------------------------------------------------
# render_skills
# ---------------------------------------------------------------------------


class TestRenderSkills:
    SAMPLE_SKILLS = [
        {"category": "Languages", "items": "Python, Go, Rust"},
        {"category": "Cloud & Infrastructure", "items": "AWS, GCP, Kubernetes"},
    ]

    def test_contains_cvsection(self):
        output = render_skills(self.SAMPLE_SKILLS)
        assert "\\cvsection{Strategic Skills Portfolio}" in output

    def test_contains_cvskills_env(self):
        output = render_skills(self.SAMPLE_SKILLS)
        assert "\\begin{cvskills}" in output
        assert "\\end{cvskills}" in output

    def test_cvskill_entries_present(self):
        output = render_skills(self.SAMPLE_SKILLS)
        assert output.count("\\cvskill") == len(self.SAMPLE_SKILLS)

    def test_category_appears_in_output(self):
        output = render_skills(self.SAMPLE_SKILLS)
        assert "Languages" in output

    def test_items_appear_in_output(self):
        output = render_skills(self.SAMPLE_SKILLS)
        assert "Python, Go, Rust" in output

    def test_special_chars_in_category_are_escaped(self):
        skills = [{"category": "Cloud & Infra", "items": "AWS"}]
        output = render_skills(skills)
        assert "\\&" in output

    def test_empty_skills_list(self):
        output = render_skills([])
        assert "\\begin{cvskills}" in output
        assert "\\end{cvskills}" in output
        assert "\\cvskill" not in output

    def test_returns_string(self):
        assert isinstance(render_skills(self.SAMPLE_SKILLS), str)
