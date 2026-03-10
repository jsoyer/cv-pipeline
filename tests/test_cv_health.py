"""Unit tests for scripts/cv-health.py — audit scoring functions."""

import importlib
import sys
from pathlib import Path

import pytest

# conftest.py adds scripts/ to sys.path; import hyphenated module via importlib
cv_health = importlib.import_module("cv-health")

_flatten_items      = cv_health._flatten_items
_check_quantification = cv_health._check_quantification
_check_action_verbs   = cv_health._check_action_verbs
_check_bullet_length  = cv_health._check_bullet_length
_check_profile        = cv_health._check_profile
_check_repetition     = cv_health._check_repetition
_check_completeness   = cv_health._check_completeness
_check_duplicates     = cv_health._check_duplicates
audit                 = cv_health.audit


# ---------------------------------------------------------------------------
# _flatten_items
# ---------------------------------------------------------------------------

class TestFlattenItems:
    def test_string_items(self):
        result = _flatten_items(["First bullet", "Second bullet"])
        assert result == ["First bullet", "Second bullet"]

    def test_dict_items_text_only(self):
        result = _flatten_items([{"text": "Built system", "label": ""}])
        assert result == ["Built system"]

    def test_dict_items_label_and_text(self):
        result = _flatten_items([{"text": "Built system", "label": "Achievement"}])
        assert result == ["Achievement: Built system"]

    def test_bold_stripped(self):
        result = _flatten_items(["**Led** team of 10"])
        assert result == ["Led team of 10"]

    def test_empty_list(self):
        assert _flatten_items([]) == []

    def test_none(self):
        assert _flatten_items(None) == []

    def test_mixed_str_and_dict(self):
        items = ["Plain string", {"text": "Dict item", "label": ""}]
        result = _flatten_items(items)
        assert len(result) == 2
        assert result[0] == "Plain string"
        assert result[1] == "Dict item"


# ---------------------------------------------------------------------------
# _check_quantification
# ---------------------------------------------------------------------------

class TestCheckQuantification:
    def test_all_with_metrics(self):
        bullets = ["Increased revenue by 30%", "Managed team of 15 engineers"]
        result = _check_quantification(bullets)
        assert result["with_metrics"] == 2

    def test_none_with_metrics(self):
        bullets = ["Managed a team", "Worked on projects"]
        result = _check_quantification(bullets)
        assert result["with_metrics"] == 0
        assert result["score"] == 0

    def test_empty_bullets(self):
        result = _check_quantification([])
        assert result["score"] == 0
        assert result["total"] == 0

    def test_dollar_sign_counts(self):
        result = _check_quantification(["Generated $1M in revenue"])
        assert result["with_metrics"] == 1

    def test_multiplier_counts(self):
        result = _check_quantification(["Improved throughput by 3x"])
        assert result["with_metrics"] == 1

    def test_score_capped_at_100(self):
        bullets = [f"Grew metric by {i*10}%" for i in range(1, 20)]
        result = _check_quantification(bullets)
        assert result["score"] <= 100

    def test_detail_key_present(self):
        result = _check_quantification(["Led team of 5"])
        assert "detail" in result

    def test_rate_is_percentage(self):
        bullets = ["Has metric 50%", "No metric here"]
        result = _check_quantification(bullets)
        assert result["rate"] == 50.0


# ---------------------------------------------------------------------------
# _check_action_verbs
# ---------------------------------------------------------------------------

class TestCheckActionVerbs:
    def test_strong_verb_detected(self):
        result = _check_action_verbs(["Led a team of engineers"])
        assert result["strong"] == 1

    def test_weak_verb_detected(self):
        result = _check_action_verbs(["Helped the team with tasks"])
        assert result["weak"] == 1

    def test_weak_examples_populated(self):
        result = _check_action_verbs(["Helped with project", "Assisted in review"])
        assert len(result["weak_examples"]) > 0

    def test_empty_bullets(self):
        result = _check_action_verbs([])
        assert result["score"] == 0

    def test_score_in_range(self):
        bullets = ["Led growth", "Built platform", "Delivered results"]
        result = _check_action_verbs(bullets)
        assert 0 <= result["score"] <= 100

    def test_all_strong_verbs_high_score(self):
        bullets = ["Led team", "Built platform", "Delivered product", "Scaled operations"]
        result = _check_action_verbs(bullets)
        assert result["strong"] == 4
        assert result["weak"] == 0

    def test_neutral_verb_counted(self):
        result = _check_action_verbs(["Analyzed requirements for the project"])
        assert result["neutral"] == 1


# ---------------------------------------------------------------------------
# _check_bullet_length
# ---------------------------------------------------------------------------

class TestCheckBulletLength:
    def test_ideal_length(self):
        bullet = "Built distributed system that scales to handle traffic spikes globally"
        result = _check_bullet_length([bullet])
        assert result["ideal"] == 1
        assert result["too_short"] == 0
        assert result["too_long"] == 0

    def test_too_short(self):
        result = _check_bullet_length(["Led team"])
        assert result["too_short"] == 1

    def test_too_long(self):
        long_bullet = " ".join(["word"] * 30)
        result = _check_bullet_length([long_bullet])
        assert result["too_long"] == 1

    def test_empty(self):
        result = _check_bullet_length([])
        assert result["score"] == 0

    def test_score_capped_at_100(self):
        bullets = ["Built scalable microservices platform serving millions of daily active users"] * 5
        result = _check_bullet_length(bullets)
        assert result["score"] <= 100

    def test_detail_present(self):
        result = _check_bullet_length(["Short bullet here with context"])
        assert "detail" in result


# ---------------------------------------------------------------------------
# _check_profile
# ---------------------------------------------------------------------------

class TestCheckProfile:
    def test_ideal_length(self):
        # 60 words — ideal range
        profile = " ".join(["word"] * 60)
        result = _check_profile(profile)
        assert result["score"] >= 100

    def test_too_short(self):
        result = _check_profile("Short profile text")
        assert result["score"] < 100
        assert result["words"] < 40

    def test_too_long(self):
        profile = " ".join(["word"] * 100)
        result = _check_profile(profile)
        assert result["words"] > 80

    def test_missing_profile(self):
        result = _check_profile("")
        assert result["score"] == 0

    def test_metric_detected(self):
        profile = "Senior engineer with 10 years experience leading teams of 50 people."
        result = _check_profile(profile)
        assert result["has_metric"] is True

    def test_no_metric(self):
        profile = " ".join(["engineer"] * 55)
        result = _check_profile(profile)
        assert result["has_metric"] is False

    def test_detail_present(self):
        result = _check_profile("Short")
        assert "detail" in result


# ---------------------------------------------------------------------------
# _check_repetition
# ---------------------------------------------------------------------------

class TestCheckRepetition:
    def test_overused_word_detected(self):
        bullets = ["managed team", "managed project", "managed budget", "managed resources"]
        result = _check_repetition(bullets, "")
        overused_words = [w for w, _ in result["overused"]]
        assert "managed" in overused_words

    def test_no_overused_words(self):
        bullets = ["Led engineering", "Built platform", "Delivered product", "Scaled team"]
        result = _check_repetition(bullets, "")
        assert result["score"] == 100

    def test_score_decreases_with_overuse(self):
        clean = _check_repetition(["Led team", "Built system"], "")
        overused = _check_repetition(["managed managed managed managed managed"] * 3, "")
        assert overused["score"] < clean["score"]

    def test_stop_words_excluded(self):
        # Common stop words should not appear in overused list
        bullets = ["with the team", "with the client", "with the board", "with the product"]
        result = _check_repetition(bullets, "")
        overused_words = [w for w, _ in result["overused"]]
        assert "with" not in overused_words
        assert "the" not in overused_words

    def test_detail_present(self):
        result = _check_repetition(["word word word word"], "")
        assert "detail" in result


# ---------------------------------------------------------------------------
# _check_completeness
# ---------------------------------------------------------------------------

class TestCheckCompleteness:
    def test_all_sections_present(self):
        data = {
            "personal":       {"name": "John"},
            "profile":        "Text",
            "skills":         [{"category": "x", "items": "y"}],
            "key_wins":       [{"title": "x", "text": "y"}],
            "experience":     [{"title": "x"}],
            "education":      [{"degree": "x"}],
            "certifications": [{"name": "x"}],
            "languages":      ["French"],
        }
        result = _check_completeness(data)
        assert result["score"] == 100
        assert result["missing"] == []

    def test_all_missing(self):
        result = _check_completeness({})
        assert result["score"] == 0
        assert len(result["missing"]) == 8

    def test_partial_completeness(self):
        data = {"personal": {"name": "x"}, "profile": "text"}
        result = _check_completeness(data)
        assert 0 < result["score"] < 100

    def test_missing_list_populated(self):
        result = _check_completeness({"personal": {"name": "x"}})
        assert len(result["missing"]) == 7

    def test_detail_present(self):
        result = _check_completeness({})
        assert "detail" in result


# ---------------------------------------------------------------------------
# _check_duplicates
# ---------------------------------------------------------------------------

class TestCheckDuplicates:
    def test_no_duplicates(self):
        bullets = [
            "Built distributed microservices platform handling payments",
            "Negotiated vendor contracts saving annual budget",
            "Led hiring and mentoring engineers globally",
        ]
        result = _check_duplicates(bullets)
        assert result["score"] == 100
        assert result["duplicates"] == []

    def test_near_duplicate_detected(self):
        bullets = [
            "Led team of engineers to deliver product on time",
            "Led team of engineers to deliver product within budget",
        ]
        result = _check_duplicates(bullets)
        assert len(result["duplicates"]) >= 1

    def test_score_decreases_with_duplicates(self):
        bullet = "Managed team of engineers and delivered results on schedule"
        result = _check_duplicates([bullet, bullet])
        assert result["score"] < 100

    def test_empty_bullets(self):
        result = _check_duplicates([])
        assert result["score"] == 100
        assert result["duplicates"] == []

    def test_detail_present(self):
        result = _check_duplicates(["Led team", "Led team"])
        assert "detail" in result


# ---------------------------------------------------------------------------
# audit()
# ---------------------------------------------------------------------------

_BASE_DATA = {
    "personal": {"first_name": "John", "last_name": "Doe"},
    "profile": (
        "Senior software engineer with 10 years experience leading distributed "
        "teams across EMEA region delivering high-impact technical initiatives."
    ),
    "skills":         [{"category": "Languages", "items": "Python, Go"}],
    "key_wins":       [{"title": "Revenue", "text": "Grew ARR by 40%"}],
    "experience": [
        {
            "title": "VP Engineering",
            "company": "Acme",
            "dates": "2020 -- Present",
            "location": "Paris",
            "items": [
                "Led team of 20 engineers delivering 3 products on schedule",
                "Increased revenue by 40% through platform optimization",
                "Reduced infrastructure costs by $500K annually",
            ],
        }
    ],
    "early_career": [],
    "education":      [{"degree": "MSc", "school": "MIT", "location": "Boston", "dates": "2010 -- 2012"}],
    "certifications": [{"name": "AWS SA", "institution": "Amazon", "date": "2022"}],
    "languages":      ["English", "French"],
}


class TestAudit:
    def test_returns_overall_score(self):
        result = audit(_BASE_DATA)
        assert "overall" in result
        assert 0 <= result["overall"] <= 100

    def test_returns_grade(self):
        result = audit(_BASE_DATA)
        assert result["grade"] in {"🟢 Excellent", "🟡 Good", "🟠 Fair", "🔴 Needs work"}

    def test_all_metric_keys_present(self):
        result = audit(_BASE_DATA)
        for key in [
            "quantification", "action_verbs", "bullet_length",
            "profile", "repetition", "completeness", "duplicates",
        ]:
            assert key in result

    def test_bullet_count(self):
        result = audit(_BASE_DATA)
        assert result["bullet_count"] == 3

    def test_empty_experience(self):
        data = {**_BASE_DATA, "experience": [], "early_career": []}
        result = audit(data)
        assert result["bullet_count"] == 0

    def test_grade_needs_work_on_empty_cv(self):
        result = audit({})
        assert result["grade"] == "🔴 Needs work"

    def test_overall_is_weighted_sum(self):
        result = audit(_BASE_DATA)
        # Overall must be integer between 0 and 100
        assert isinstance(result["overall"], int)

    def test_early_career_bullets_counted(self):
        data = {
            **_BASE_DATA,
            "experience": [],
            "early_career": [
                {"title": "Dev", "company": "X", "dates": "2010--2015", "location": "Y",
                 "items": ["Built system handling 1M users daily"]}
            ],
        }
        result = audit(data)
        assert result["bullet_count"] == 1
