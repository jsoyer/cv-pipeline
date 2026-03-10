"""Unit tests for scripts/ats-text.py — ATS-safe plain text export."""

import importlib
import sys
from pathlib import Path

import pytest

# conftest.py adds scripts/ to sys.path; import hyphenated module via importlib
ats_text = importlib.import_module("ats-text")

_strip_bold        = ats_text._strip_bold
_clean             = ats_text._clean
_wrap              = ats_text._wrap
_flatten_items     = ats_text._flatten_items
_render_list_field = ats_text._render_list_field
render_cv          = ats_text.render_cv
render_coverletter = ats_text.render_coverletter
DIVIDER            = ats_text.DIVIDER


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_CV = {
    "personal": {
        "first_name": "Alice",
        "last_name":  "Martin",
        "position":   "Software Engineer",
        "address":    "Paris, France",
        "email":      "alice@example.com",
        "mobile":     "+33 6 00 00 00 00",
        "linkedin":   "alicemartin",
    },
    "profile": "Senior engineer with **10 years** experience in distributed systems.",
    "skills": [
        {"category": "Languages", "items": "Python, Go"},
    ],
    "key_wins": [
        {"title": "Revenue", "text": "Grew ARR by 40% in 12 months"},
    ],
    "experience": [
        {
            "title":    "Staff Engineer",
            "company":  "TechCorp",
            "location": "Paris",
            "dates":    "2020 -- Present",
            "items": [
                "Led team of 15 engineers delivering 3 products",
                {"text": "Reduced latency by 40%", "label": "Performance"},
            ],
        }
    ],
    "education": [
        {"degree": "MSc CS", "institution": "ENS Paris", "location": "Paris", "dates": "2010 -- 2012"},
    ],
    "certifications": [
        {"name": "AWS SA", "institution": "Amazon", "dates": "2022"},
    ],
    "awards":      "Speaker at PyCon 2023",
    "publications": "Author of 3 blog posts",
    "languages":   ["French (Native)", "English (Fluent)"],
    "interests":   ["Open source", "Cycling"],
}

MINIMAL_CL = {
    "recipient": {"name": "Hiring Manager", "company": "Acme Corp"},
    "title":     "Application for Staff Engineer",
    "opening":   "Dear Hiring Manager,",
    "closing":   "Best regards,",
    "sections": [
        {"title": "About Me",  "content": "I am a passionate engineer with broad experience."},
        {"title": "Why Acme?", "content": "Acme's mission aligns with my values."},
    ],
    "closing_paragraph": "Thank you for your time and consideration.",
}

PERSONAL = MINIMAL_CV["personal"]


# ---------------------------------------------------------------------------
# _strip_bold
# ---------------------------------------------------------------------------

class TestStripBold:
    def test_removes_markers(self):
        assert _strip_bold("**bold**") == "bold"

    def test_in_sentence(self):
        assert _strip_bold("with **10 years** experience") == "with 10 years experience"

    def test_no_markers_unchanged(self):
        assert _strip_bold("plain text") == "plain text"

    def test_empty_string(self):
        assert _strip_bold("") == ""

    def test_none_handled(self):
        # _strip_bold casts to str via str(text or "")
        assert _strip_bold(None) == ""


# ---------------------------------------------------------------------------
# _clean
# ---------------------------------------------------------------------------

class TestClean:
    def test_strips_bold(self):
        assert _clean("**bold**") == "bold"

    def test_converts_double_dash(self):
        assert _clean("2020 -- Present") == "2020 \u2013 Present"

    def test_both_transformations(self):
        result = _clean("**Led** team 2020 -- 2023")
        assert "Led" in result
        assert "\u2013" in result
        assert "**" not in result
        assert "--" not in result


# ---------------------------------------------------------------------------
# _wrap
# ---------------------------------------------------------------------------

class TestWrap:
    def test_short_text_unchanged(self):
        result = _wrap("Hello world")
        assert "Hello world" in result

    def test_long_text_wrapped(self):
        long = "word " * 20  # 100 chars
        result = _wrap(long)
        assert any(len(line) <= 78 for line in result.splitlines())

    def test_indent_applied(self):
        result = _wrap("Hello world", indent="  ")
        assert result.startswith("  ")

    def test_strips_bold(self):
        result = _wrap("**bold** text")
        assert "**" not in result


# ---------------------------------------------------------------------------
# _flatten_items
# ---------------------------------------------------------------------------

class TestFlattenItems:
    def test_string_item(self):
        result = _flatten_items(["Built a system handling 1M requests"])
        assert result == ["Built a system handling 1M requests"]

    def test_dict_item_with_label(self):
        result = _flatten_items([{"text": "Reduced latency", "label": "Performance"}])
        assert result == ["Performance: Reduced latency"]

    def test_dict_item_text_only(self):
        result = _flatten_items([{"text": "Reduced latency", "label": ""}])
        assert result == ["Reduced latency"]

    def test_mixed_items(self):
        items = ["Plain string", {"text": "Dict text", "label": ""}]
        result = _flatten_items(items)
        assert len(result) == 2

    def test_double_dash_converted(self):
        result = _flatten_items(["Worked 2020 -- 2023"])
        assert "\u2013" in result[0]

    def test_empty_list(self):
        assert _flatten_items([]) == []

    def test_none(self):
        assert _flatten_items(None) == []


# ---------------------------------------------------------------------------
# _render_list_field
# ---------------------------------------------------------------------------

class TestRenderListField:
    def test_list_of_strings(self):
        result = _render_list_field(["French", "English"])
        assert result == "French, English"

    def test_list_of_dicts_with_level(self):
        field = [{"language": "French", "fluency": "Native"}]
        result = _render_list_field(field)
        assert "French" in result
        assert "Native" in result

    def test_list_of_dicts_with_name_level(self):
        field = [{"name": "English", "level": "Fluent"}]
        result = _render_list_field(field)
        assert "English (Fluent)" in result

    def test_string_input(self):
        result = _render_list_field("French, English")
        assert result == "French, English"

    def test_empty_list(self):
        result = _render_list_field([])
        assert result == ""


# ---------------------------------------------------------------------------
# render_cv
# ---------------------------------------------------------------------------

class TestRenderCv:
    def setup_method(self):
        self.result = render_cv(MINIMAL_CV)

    def test_name_in_header(self):
        assert "ALICE MARTIN" in self.result

    def test_position_in_header(self):
        assert "Software Engineer" in self.result

    def test_email_in_header(self):
        assert "alice@example.com" in self.result

    def test_linkedin_in_header(self):
        assert "alicemartin" in self.result

    def test_profile_section(self):
        assert "PROFILE" in self.result
        assert DIVIDER in self.result

    def test_profile_bold_stripped(self):
        assert "10 years" in self.result
        assert "**10 years**" not in self.result

    def test_skills_section(self):
        assert "SKILLS" in self.result
        assert "Python, Go" in self.result

    def test_key_achievements_section(self):
        assert "KEY ACHIEVEMENTS" in self.result
        assert "Revenue" in self.result

    def test_experience_section(self):
        assert "PROFESSIONAL EXPERIENCE" in self.result
        assert "TechCorp" in self.result

    def test_experience_string_item(self):
        assert "Led team of 15 engineers" in self.result

    def test_experience_dict_item_with_label(self):
        assert "Performance: Reduced latency" in self.result

    def test_education_section(self):
        assert "EDUCATION" in self.result
        assert "ENS Paris" in self.result

    def test_certifications_section(self):
        assert "CERTIFICATIONS" in self.result
        assert "AWS SA" in self.result

    def test_awards_section(self):
        assert "AWARDS & PUBLICATIONS" in self.result
        assert "PyCon" in self.result

    def test_languages_section(self):
        assert "LANGUAGES & INTERESTS" in self.result
        assert "Languages:" in self.result

    def test_returns_string(self):
        assert isinstance(self.result, str)

    def test_empty_data_returns_string(self):
        result = render_cv({})
        assert isinstance(result, str)

    def test_date_range_converted(self):
        # "2020 -- Present" should appear as en-dash
        assert "\u2013" in self.result


# ---------------------------------------------------------------------------
# render_coverletter
# ---------------------------------------------------------------------------

class TestRenderCoverletter:
    def setup_method(self):
        self.result = render_coverletter(MINIMAL_CL, PERSONAL)

    def test_sender_name_present(self):
        assert "Alice Martin" in self.result

    def test_sender_email_present(self):
        assert "alice@example.com" in self.result

    def test_recipient_name_present(self):
        assert "Hiring Manager" in self.result

    def test_recipient_company_present(self):
        assert "Acme Corp" in self.result

    def test_re_line_present(self):
        assert "Re: Application for Staff Engineer" in self.result

    def test_opening_present(self):
        assert "Dear Hiring Manager," in self.result

    def test_section_title_uppercased(self):
        assert "ABOUT ME" in self.result

    def test_section_content_present(self):
        assert "passionate engineer" in self.result

    def test_closing_paragraph_present(self):
        assert "Thank you for your time" in self.result

    def test_sign_off_present(self):
        assert "Best regards," in self.result

    def test_name_at_end(self):
        lines = self.result.splitlines()
        assert "Alice Martin" in lines[-1]

    def test_returns_string(self):
        assert isinstance(self.result, str)

    def test_section_as_string(self):
        cl_data = {
            **MINIMAL_CL,
            "sections": ["This is a plain string section."],
        }
        result = render_coverletter(cl_data, PERSONAL)
        assert "plain string section" in result

    def test_recipient_as_string(self):
        cl_data = {**MINIMAL_CL, "recipient": "Acme Corp Talent Team"}
        result = render_coverletter(cl_data, PERSONAL)
        assert "Acme Corp Talent Team" in result

    def test_no_closing_paragraph(self):
        cl_data = {k: v for k, v in MINIMAL_CL.items() if k != "closing_paragraph"}
        result = render_coverletter(cl_data, PERSONAL)
        assert isinstance(result, str)
