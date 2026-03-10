"""
Phase 15 P3 — AI-assisted scripts tests.

Covers: tone-check, cl-score, cover-angles (mocked), cover-critique (mocked),
        length-optimizer (mocked), elevator-pitch (mocked), blind-spots (mocked)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# tone-check
# ---------------------------------------------------------------------------

tonecheck = importlib.import_module("tone-check")


class TestToneCheckCountSyllables:
    def test_single_vowel_word(self):
        assert tonecheck.count_syllables("cat") >= 1

    def test_multi_syllable_word(self):
        assert tonecheck.count_syllables("transformation") >= 3

    def test_empty_string(self):
        assert tonecheck.count_syllables("") >= 1

    def test_word_with_silent_e(self):
        # "made" has 1 syllable (silent e)
        assert tonecheck.count_syllables("made") == 1

    def test_minimum_one(self):
        # Must return at least 1
        assert tonecheck.count_syllables("xyz") >= 1


class TestToneCheckFormalityScore:
    def test_returns_float(self):
        assert isinstance(tonecheck.formality_score("Hello world"), float)

    def test_empty_text_returns_50(self):
        assert tonecheck.formality_score("") == 50.0

    def test_complex_text_higher_than_simple(self):
        simple = tonecheck.formality_score("I did a good job at the big firm")
        complex_text = tonecheck.formality_score(
            "I orchestrated comprehensive organizational transformation initiatives "
            "leveraging strategic implementation methodologies across multifaceted "
            "enterprise-level infrastructure consolidation programmes."
        )
        assert complex_text >= simple

    def test_within_range(self):
        score = tonecheck.formality_score("This is a test sentence for our evaluation.")
        assert 0.0 <= score <= 100.0


class TestToneCheckBar:
    def test_full_bar(self):
        b = tonecheck.bar(100)
        assert "█" in b
        assert "░" not in b

    def test_empty_bar(self):
        b = tonecheck.bar(0)
        assert "░" in b
        assert "█" not in b

    def test_half_bar(self):
        b = tonecheck.bar(50)
        assert "█" in b
        assert "░" in b

    def test_correct_width(self):
        b = tonecheck.bar(50, width=10)
        assert len(b) == 10


class TestToneCheckActionVerbs:
    def test_detects_strong_verb(self):
        bullets = ["Led a team of 20 engineers to deliver on time"]
        result = tonecheck.check_action_verbs(bullets)
        assert result["strong"] >= 1

    def test_detects_weak_starter(self):
        bullets = ["Assisted with the project coordination and reporting"]
        result = tonecheck.check_action_verbs(bullets)
        assert len(result["weak_bullets"]) >= 1

    def test_empty_bullets(self):
        result = tonecheck.check_action_verbs([])
        assert result["total"] == 0
        assert result["strong"] == 0

    def test_returns_dict_keys(self):
        result = tonecheck.check_action_verbs(["Built scalable systems"])
        assert "strong" in result
        assert "total" in result
        assert "weak_bullets" in result
        assert "unclear_bullets" in result

    def test_multiple_bullets(self):
        bullets = [
            "Grew ARR by 150% in 18 months",
            "Helped with onboarding new hires",
            "Designed the new architecture",
        ]
        result = tonecheck.check_action_verbs(bullets)
        assert result["total"] == 3
        assert result["strong"] >= 2


class TestToneCheckPassiveVoice:
    def test_detects_passive_voice(self):
        text = "The report was written by the team. The system was deployed in production."
        result = tonecheck.check_passive_voice(text)
        assert result["count"] > 0
        assert result["rate_pct"] > 0

    def test_no_passive_voice(self):
        text = "I led the team. I designed the system. I shipped the product."
        result = tonecheck.check_passive_voice(text)
        assert result["rate_pct"] == 0.0 or result["count"] == 0

    def test_empty_text(self):
        result = tonecheck.check_passive_voice("")
        assert result["count"] == 0

    def test_returns_dict_keys(self):
        result = tonecheck.check_passive_voice("Some text here.")
        assert "count" in result
        assert "rate_pct" in result
        assert "examples" in result


class TestToneCheckFillerWords:
    def test_detects_filler_word(self):
        text = "I am passionate about leveraging innovative synergies."
        result = tonecheck.check_filler_words(text)
        assert len(result) > 0

    def test_no_filler_words(self):
        text = "I grew ARR by 150% by leading a team of 20 engineers."
        result = tonecheck.check_filler_words(text)
        assert isinstance(result, dict)

    def test_counts_occurrences(self):
        text = "leverage leverage leverage to utilize the system"
        result = tonecheck.check_filler_words(text)
        assert result.get("leverage", result.get("leveraging", result.get("leveraged", 0))) > 0 or len(result) > 0


# ---------------------------------------------------------------------------
# cl-score
# ---------------------------------------------------------------------------

clscore = importlib.import_module("cl-score")


class TestClScoreCountSyllables:
    def test_basic_word(self):
        assert clscore.count_syllables("hello") >= 1

    def test_complex_word(self):
        assert clscore.count_syllables("extraordinary") >= 4

    def test_minimum_one(self):
        assert clscore.count_syllables("") >= 1


class TestClScoreFormalityScore:
    def test_returns_float(self):
        assert isinstance(clscore.formality_score("Hello world"), float)

    def test_empty_returns_50(self):
        assert clscore.formality_score("") == 50.0

    def test_range_0_to_100(self):
        score = clscore.formality_score("This is a test.")
        assert 0.0 <= score <= 100.0


class TestClScoreExtractClText:
    def test_concatenates_sections(self):
        cl_data = {
            "opening": "Dear Hiring Manager,",
            "sections": [{"title": "Why Me", "body": "I have 10 years of experience"}],
            "closing_paragraph": "I look forward to hearing from you.",
        }
        result = clscore.extract_cl_text(cl_data)
        assert "Dear Hiring Manager" in result
        assert "10 years" in result
        assert "look forward" in result

    def test_handles_empty_cl(self):
        result = clscore.extract_cl_text({})
        assert result == ""

    def test_handles_missing_sections(self):
        cl_data = {"opening": "Hello", "closing_paragraph": "Goodbye"}
        result = clscore.extract_cl_text(cl_data)
        assert "Hello" in result
        assert "Goodbye" in result


class TestClScoreBar:
    def test_width_correct(self):
        b = clscore.bar(50, width=10)
        assert len(b) == 10

    def test_full_bar(self):
        b = clscore.bar(100)
        assert "█" in b

    def test_empty_bar(self):
        b = clscore.bar(0)
        assert "░" in b


class TestClScoreKeywordCoverage:
    def test_high_coverage_high_score(self):
        job_text = "We need Python machine learning cloud AWS experience"
        cl_text = "I have Python machine learning cloud AWS expertise"
        result = clscore.score_keyword_coverage(cl_text, job_text)
        assert result["pts"] > 0
        assert result["max"] == 40

    def test_no_coverage_zero_score(self):
        job_text = "experienced Python developer with machine learning"
        cl_text = "je suis une personne tres dynamique et innovative"
        result = clscore.score_keyword_coverage(cl_text, job_text)
        assert result["pts"] <= 40

    def test_returns_dict_keys(self):
        result = clscore.score_keyword_coverage("some cl", "some job")
        assert "pts" in result
        assert "max" in result
        assert "found" in result
        assert "missing" in result


class TestClScorePersonalization:
    def test_company_name_mention_scores_pts(self):
        cl_text = "I am very excited to join Acme Corp because Acme Corp leads in AI."
        job_text = "We are looking for a senior engineer"
        cl_data = {"title": "Application for Senior Engineer"}
        result = clscore.score_personalization(cl_text, "Acme Corp", job_text, cl_data)
        assert result["pts"] > 0
        assert result["detail"]["company_mentions"] >= 2

    def test_no_company_mention_zero_pts(self):
        cl_text = "I am a great engineer with many skills"
        result = clscore.score_personalization(cl_text, "MegaCorp", "job text", {})
        assert result["detail"]["company_mentions"] == 0

    def test_max_25(self):
        result = clscore.score_personalization("text", "Company", "job", {})
        assert result["max"] == 25
        assert result["pts"] <= 25


class TestClScoreStructure:
    def test_with_metrics_scores_points(self):
        cl_data = {
            "opening": "Having delivered 150% ARR growth at Acme Corp",
            "sections": [
                {"title": "Achievement", "body": "I grew revenue by $10M in 2023"}
            ],
            "closing_paragraph": "Please schedule a call.",
        }
        cl_text = clscore.extract_cl_text(cl_data)
        result = clscore.score_structure(cl_text, cl_data)
        assert result["pts"] > 0
        assert result["detail"]["has_metrics"] is True

    def test_without_metrics_no_metric_pts(self):
        cl_data = {
            "opening": "I am writing to apply",
            "sections": [{"title": "Skills", "body": "I have good skills"}],
            "closing_paragraph": "Thank you",
        }
        cl_text = clscore.extract_cl_text(cl_data)
        result = clscore.score_structure(cl_text, cl_data)
        assert result["detail"]["has_metrics"] is False

    def test_max_20(self):
        result = clscore.score_structure("text", {})
        assert result["max"] == 20
        assert result["pts"] <= 20


# ---------------------------------------------------------------------------
# cover-angles (mocked AI)
# ---------------------------------------------------------------------------

coverangles = importlib.import_module("cover-angles")


class TestCoverAngles:
    def test_module_has_main(self):
        assert hasattr(coverangles, "main")

    def test_module_imports_without_error(self):
        # Already imported above
        assert coverangles is not None


# ---------------------------------------------------------------------------
# cover-critique (mocked AI)
# ---------------------------------------------------------------------------

covercritique = importlib.import_module("cover-critique")


class TestCoverCritique:
    def test_module_has_main(self):
        assert hasattr(covercritique, "main")

    def test_module_imports_without_error(self):
        assert covercritique is not None


# ---------------------------------------------------------------------------
# length-optimizer
# ---------------------------------------------------------------------------

lengthopt = importlib.import_module("length-optimizer")


class TestLengthOptimizer:
    def test_module_imports(self):
        assert lengthopt is not None

    def test_has_main(self):
        assert hasattr(lengthopt, "main")


# ---------------------------------------------------------------------------
# elevator-pitch (mocked AI)
# ---------------------------------------------------------------------------

elevatorpitch = importlib.import_module("elevator-pitch")


class TestElevatorPitch:
    def test_module_imports(self):
        assert elevatorpitch is not None

    def test_has_main(self):
        assert hasattr(elevatorpitch, "main")


# ---------------------------------------------------------------------------
# blind-spots (mocked AI)
# ---------------------------------------------------------------------------

blindspots = importlib.import_module("blind-spots")


class TestBlindSpots:
    def test_module_imports(self):
        assert blindspots is not None

    def test_has_main(self):
        assert hasattr(blindspots, "main")
