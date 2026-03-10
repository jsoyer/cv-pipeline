"""Unit tests for scripts/export.py — JSON/Markdown/text export."""

import json
import sys
from pathlib import Path

import pytest

# conftest.py adds scripts/ to sys.path
import export as export_mod
from export import strip_bold, render_json, render_markdown, render_text, FORMATS


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

SAMPLE_CV = {
    "personal": {
        "first_name": "Jane",
        "last_name":  "Smith",
        "position":   "Engineering Manager",
        "address":    "London, UK",
        "email":      "jane@example.com",
        "mobile":     "+44 7700 000000",
        "linkedin":   "janesmith",
    },
    "profile": "Experienced engineering manager with **10 years** in distributed systems.",
    "skills": [
        {"category": "Languages",  "items": "Python, Go, Rust"},
        {"category": "Cloud",      "items": "AWS, GCP"},
    ],
    "key_wins": [
        {"title": "Revenue Growth", "text": "Grew ARR by **50%** in 12 months"},
        {"title": "Team",           "text": "Hired and led 20 engineers across 3 offices"},
    ],
    "experience": [
        {
            "title":    "Senior Engineer",
            "company":  "Acme Corp",
            "location": "London",
            "dates":    "2020 -- Present",
            "items": [
                {"text": "Built distributed systems serving 10M users", "label": ""},
                {"text": "Reduced latency by 40%",                      "label": "Performance"},
            ],
        }
    ],
    "early_career": [
        {
            "title":    "Junior Developer",
            "company":  "Startup",
            "location": "Manchester",
            "dates":    "2015 -- 2020",
        }
    ],
    "education": [
        {
            "degree":   "MSc Computer Science",
            "school":   "University of London",
            "location": "London",
            "dates":    "2013 -- 2015",
            "note":     "Distinction",
        }
    ],
    "certifications": [
        {"name": "AWS Solutions Architect", "institution": "Amazon", "date": "2022"},
    ],
    "awards":       "Speaker at PyCon 2023",
    "publications": "Author of 3 technical blog posts on distributed systems",
    "languages":    ["French (Native)", "English (Fluent)"],
    "interests":    ["Open source", "Cycling"],
}


# ---------------------------------------------------------------------------
# strip_bold
# ---------------------------------------------------------------------------

class TestStripBold:
    def test_removes_bold_markers(self):
        assert strip_bold("**bold**") == "bold"

    def test_bold_in_sentence(self):
        assert strip_bold("I am **very** good") == "I am very good"

    def test_multiple_bold(self):
        assert strip_bold("**a** and **b**") == "a and b"

    def test_no_bold_unchanged(self):
        assert strip_bold("plain text") == "plain text"

    def test_empty_string(self):
        assert strip_bold("") == ""


# ---------------------------------------------------------------------------
# render_json
# ---------------------------------------------------------------------------

class TestRenderJson:
    def test_returns_valid_json(self):
        result = render_json(SAMPLE_CV)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_contains_personal_info(self):
        result = render_json(SAMPLE_CV)
        parsed = json.loads(result)
        assert parsed["personal"]["first_name"] == "Jane"
        assert parsed["personal"]["last_name"] == "Smith"

    def test_preserves_all_keys(self):
        result = render_json(SAMPLE_CV)
        parsed = json.loads(result)
        for key in SAMPLE_CV:
            assert key in parsed

    def test_ensure_ascii_false(self):
        # Non-ASCII characters should be preserved, not escaped
        data = {"name": "François"}
        result = render_json(data)
        assert "François" in result

    def test_indented_output(self):
        result = render_json({"a": 1})
        assert "\n" in result  # indented → has newlines


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def setup_method(self):
        self.result = render_markdown(SAMPLE_CV)

    def test_h1_contains_name(self):
        assert "# Jane Smith" in self.result

    def test_profile_section_present(self):
        assert "## Profile" in self.result

    def test_profile_bold_stripped(self):
        # **10 years** → 10 years in markdown output
        assert "10 years" in self.result
        assert "**10 years**" not in self.result

    def test_skills_section_present(self):
        assert "## Skills" in self.result

    def test_skill_categories_present(self):
        assert "Languages" in self.result
        assert "Python, Go, Rust" in self.result

    def test_key_wins_section_present(self):
        assert "## Key Wins" in self.result

    def test_experience_section_present(self):
        assert "## Experience" in self.result

    def test_experience_h3_format(self):
        assert "### Senior Engineer" in self.result

    def test_experience_item_with_label(self):
        assert "**Performance:**" in self.result

    def test_education_section_present(self):
        assert "## Education" in self.result

    def test_education_note_included(self):
        assert "Distinction" in self.result

    def test_certifications_section_present(self):
        assert "## Certifications" in self.result

    def test_awards_section_present(self):
        assert "## Awards & Publications" in self.result

    def test_languages_section_present(self):
        assert "## Languages" in self.result

    def test_interests_section_present(self):
        assert "## Interests" in self.result

    def test_returns_string(self):
        assert isinstance(self.result, str)

    def test_linkedin_link(self):
        assert "janesmith" in self.result


# ---------------------------------------------------------------------------
# render_text
# ---------------------------------------------------------------------------

class TestRenderText:
    def setup_method(self):
        self.result = render_text(SAMPLE_CV)

    def test_name_at_top(self):
        lines = self.result.splitlines()
        assert "Jane Smith" in lines[0]

    def test_profile_header(self):
        assert "PROFILE" in self.result

    def test_dividers_present(self):
        assert "=" * 60 in self.result

    def test_profile_bold_stripped(self):
        assert "10 years" in self.result
        assert "**10 years**" not in self.result

    def test_skills_section(self):
        assert "SKILLS" in self.result
        assert "Python, Go, Rust" in self.result

    def test_key_wins_section(self):
        assert "KEY WINS" in self.result

    def test_experience_section(self):
        assert "EXPERIENCE" in self.result
        assert "Acme Corp" in self.result

    def test_experience_item_with_label(self):
        assert "Performance:" in self.result

    def test_early_career_section(self):
        assert "EARLY CAREER" in self.result

    def test_education_section(self):
        assert "EDUCATION" in self.result
        assert "Distinction" in self.result

    def test_certifications_section(self):
        assert "CERTIFICATIONS" in self.result
        assert "AWS Solutions Architect" in self.result

    def test_awards_section(self):
        assert "AWARDS & PUBLICATIONS" in self.result

    def test_languages_line(self):
        assert "Languages:" in self.result

    def test_interests_line(self):
        assert "Interests:" in self.result

    def test_returns_string(self):
        assert isinstance(self.result, str)


# ---------------------------------------------------------------------------
# FORMATS dict / aliases
# ---------------------------------------------------------------------------

class TestFormatsDict:
    def test_json_key(self):
        assert "json" in FORMATS

    def test_markdown_key(self):
        assert "markdown" in FORMATS

    def test_md_alias_same_as_markdown(self):
        assert FORMATS["md"] is FORMATS["markdown"]

    def test_text_key(self):
        assert "text" in FORMATS

    def test_txt_alias_same_as_text(self):
        assert FORMATS["txt"] is FORMATS["text"]

    def test_json_format_callable(self):
        result = FORMATS["json"]({"key": "value"})
        assert json.loads(result) == {"key": "value"}
