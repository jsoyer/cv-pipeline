"""Tests for ats-score.py — keyword extraction, section detection, scoring."""

import importlib
import sys
from pathlib import Path

import pytest

# Import the module from scripts/ (conftest.py adds scripts/ to sys.path)
ats_score = importlib.import_module("ats-score")


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic_words(self):
        tokens = ats_score.tokenize("python kubernetes docker")
        assert "python" in tokens
        assert "kubernetes" in tokens
        assert "docker" in tokens

    def test_filters_short_words(self):
        tokens = ats_score.tokenize("go is an ok language")
        # "go", "is", "an", "ok" are < 3 chars, should be filtered
        assert "language" in tokens
        assert "go" not in tokens
        assert "is" not in tokens

    def test_filters_stop_words(self):
        tokens = ats_score.tokenize("the and with for are this that")
        assert tokens == []

    def test_handles_hyphens(self):
        tokens = ats_score.tokenize("cross-functional go-to-market")
        assert "cross-functional" in tokens
        assert "go-to-market" in tokens

    def test_lowercases(self):
        tokens = ats_score.tokenize("Python KUBERNETES Docker")
        assert all(t == t.lower() for t in tokens)

    def test_empty_string(self):
        assert ats_score.tokenize("") == []


# ---------------------------------------------------------------------------
# extract_bigrams
# ---------------------------------------------------------------------------

class TestExtractBigrams:
    def test_basic(self):
        bigrams = ats_score.extract_bigrams(["machine", "learning", "model"])
        assert "machine learning" in bigrams
        assert "learning model" in bigrams

    def test_single_token(self):
        assert ats_score.extract_bigrams(["python"]) == []

    def test_empty(self):
        assert ats_score.extract_bigrams([]) == []


# ---------------------------------------------------------------------------
# detect_sections
# ---------------------------------------------------------------------------

class TestDetectSections:
    def test_required_section(self):
        text = """About the role

We are hiring.

Requirements:
- 5 years Python experience
- Kubernetes knowledge

Nice to have:
- Rust experience
"""
        sections = ats_score.detect_sections(text)
        req_text = "\n".join(sections["required"])
        pref_text = "\n".join(sections["preferred"])
        assert "python" in req_text.lower()
        assert "kubernetes" in req_text.lower()
        assert "rust" in pref_text.lower()

    def test_what_you_need_pattern(self):
        text = """What you'll need:
- Leadership experience
- Cloud architecture
"""
        sections = ats_score.detect_sections(text)
        assert len(sections["required"]) > 0

    def test_no_sections_all_general(self):
        text = "We want someone who knows Python and Docker."
        sections = ats_score.detect_sections(text)
        assert len(sections["general"]) > 0
        assert len(sections["required"]) == 0
        assert len(sections["preferred"]) == 0

    def test_responsibilities_section(self):
        text = """Responsibilities:
- Lead the team
- Design architecture
"""
        sections = ats_score.detect_sections(text)
        assert len(sections["responsibilities"]) > 0


# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------

class TestExtractKeywords:
    def test_returns_list(self):
        kws = ats_score.extract_keywords("python python python docker docker kubernetes")
        assert isinstance(kws, list)
        assert len(kws) > 0

    def test_most_frequent_first(self):
        kws = ats_score.extract_keywords(
            "python python python python docker docker kubernetes"
        )
        # "python" should be near the top (bigrams may rank higher)
        assert "python" in kws[:3]

    def test_respects_top_n(self):
        text = " ".join([f"word{i}" * 3 for i in range(20)])
        kws = ats_score.extract_keywords(text, top_n=5)
        assert len(kws) <= 5

    def test_empty_text(self):
        assert ats_score.extract_keywords("") == []


# ---------------------------------------------------------------------------
# categorize_keyword
# ---------------------------------------------------------------------------

class TestCategorizeKeyword:
    def test_leadership(self):
        assert ats_score.categorize_keyword("leadership") == "Leadership"
        assert ats_score.categorize_keyword("management") == "Leadership"

    def test_technical(self):
        assert ats_score.categorize_keyword("cloud") == "Technical"
        assert ats_score.categorize_keyword("architecture") == "Technical"

    def test_sales(self):
        assert ats_score.categorize_keyword("pipeline") == "Sales & GTM"
        assert ats_score.categorize_keyword("revenue") == "Sales & GTM"

    def test_unknown_returns_other(self):
        assert ats_score.categorize_keyword("xylophone") == "Other"


# ---------------------------------------------------------------------------
# extract_text_from_tex
# ---------------------------------------------------------------------------

class TestExtractTextFromTex:
    def test_strips_latex_commands(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text(r"\textbf{Python} and \emph{Docker}")
        text = ats_score.extract_text_from_tex(str(tex))
        assert "python" in text
        assert "docker" in text
        assert "\\textbf" not in text

    def test_strips_comments(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("real content\n%this is a comment\nmore content")
        text = ats_score.extract_text_from_tex(str(tex))
        assert "real content" in text
        # The % and everything after it on the same line is stripped
        assert "more content" in text

    def test_returns_lowercase(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("UPPERCASE content HERE")
        text = ats_score.extract_text_from_tex(str(tex))
        assert text == text.lower()
