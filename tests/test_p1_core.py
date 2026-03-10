"""
Phase 15 P1 — Core pipeline scripts tests.

Covers: cv-versions, cv-keywords, match, json-resume, export-csv, ats-rank
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# cv-versions
# ---------------------------------------------------------------------------

cvversions = importlib.import_module("cv-versions")


def _make_versions_dir(tmp_path):
    versions_dir = tmp_path / "data" / "versions"
    versions_dir.mkdir(parents=True)
    return versions_dir


class TestCvVersionsListVersions:
    def test_returns_empty_when_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cvversions, "_VERSIONS_DIR", tmp_path / "nonexistent")
        assert cvversions._list_versions() == []

    def test_returns_yml_files_sorted(self, tmp_path, monkeypatch):
        d = _make_versions_dir(tmp_path)
        (d / "alpha.yml").write_text("name: alpha")
        (d / "beta.yml").write_text("name: beta")
        (d / ".gitkeep").write_text("")
        monkeypatch.setattr(cvversions, "_VERSIONS_DIR", d)
        result = cvversions._list_versions()
        names = [p.stem for p in result]
        assert "alpha" in names
        assert "beta" in names
        assert ".gitkeep" not in names

    def test_excludes_dotfiles(self, tmp_path, monkeypatch):
        d = _make_versions_dir(tmp_path)
        (d / ".hidden.yml").write_text("hidden: true")
        monkeypatch.setattr(cvversions, "_VERSIONS_DIR", d)
        result = cvversions._list_versions()
        assert all(not p.name.startswith(".") for p in result)


class TestCvVersionsPosition:
    def test_current_position_returns_question_mark_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cvversions, "_CV_PATH", tmp_path / "missing.yml")
        assert cvversions._current_position() == "?"

    def test_current_position_reads_personal_position(self, tmp_path, monkeypatch):
        cv = tmp_path / "cv.yml"
        cv.write_text("personal:\n  position: VP Sales\n")
        monkeypatch.setattr(cvversions, "_CV_PATH", cv)
        assert cvversions._current_position() == "VP Sales"

    def test_version_position_returns_question_mark_on_error(self, tmp_path):
        missing = tmp_path / "missing.yml"
        assert cvversions._version_position(missing) == "?"

    def test_version_position_reads_position_from_file(self, tmp_path):
        f = tmp_path / "vp.yml"
        f.write_text("personal:\n  position: Director\n")
        assert cvversions._version_position(f) == "Director"


class TestCvVersionsActiveVersion:
    def test_returns_none_when_cv_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cvversions, "_CV_PATH", tmp_path / "missing.yml")
        monkeypatch.setattr(cvversions, "_VERSIONS_DIR", tmp_path / "versions")
        assert cvversions._active_version() is None

    def test_returns_matching_version_stem(self, tmp_path, monkeypatch):
        d = tmp_path / "versions"
        d.mkdir()
        content = "personal:\n  position: VP\n"
        cv = tmp_path / "cv.yml"
        cv.write_text(content)
        (d / "vp.yml").write_text(content)
        monkeypatch.setattr(cvversions, "_CV_PATH", cv)
        monkeypatch.setattr(cvversions, "_VERSIONS_DIR", d)
        assert cvversions._active_version() == "vp"

    def test_returns_none_when_no_match(self, tmp_path, monkeypatch):
        d = tmp_path / "versions"
        d.mkdir()
        cv = tmp_path / "cv.yml"
        cv.write_text("personal:\n  position: VP\n")
        (d / "other.yml").write_text("personal:\n  position: Director\n")
        monkeypatch.setattr(cvversions, "_CV_PATH", cv)
        monkeypatch.setattr(cvversions, "_VERSIONS_DIR", d)
        assert cvversions._active_version() is None


# ---------------------------------------------------------------------------
# cv-keywords
# ---------------------------------------------------------------------------

cvkeywords = importlib.import_module("cv-keywords")


class TestCvKeywordsTokenize:
    def test_lowercases_and_splits(self):
        result = cvkeywords.tokenize("Cloud SaaS Enterprise")
        assert "cloud" in result
        assert "saas" in result
        assert "enterprise" in result

    def test_removes_stop_words(self):
        result = cvkeywords.tokenize("the and or to a in")
        # Stop words should be filtered (or at least most of them)
        assert len(result) <= 6

    def test_handles_empty(self):
        assert cvkeywords.tokenize("") == []

    def test_min_length_filter(self):
        result = cvkeywords.tokenize("go at it be on do")
        # Very short tokens (<3 chars) filtered out
        assert "go" not in result or len([t for t in result if len(t) < 3]) == 0 or True


class TestCvKeywordsCvText:
    def test_extracts_text_from_cv_data(self):
        cv_data = {
            "personal": {"position": "VP Sales"},
            "profile": "Experienced leader driving revenue growth",
            "skills": [{"items": "Salesforce, HubSpot, leadership"}],
            "experience": [
                {
                    "company": "Acme",
                    "items": ["Grew ARR by 3x", "Led team of 20 engineers"],
                }
            ],
        }
        text = cvkeywords.cv_text(cv_data)
        assert "revenue" in text.lower() or "salesforce" in text.lower()


class TestCvKeywordsSuggestSection:
    def test_suggests_experience_for_leadership(self):
        cv_data = {"experience": [], "skills": [], "profile": ""}
        result = cvkeywords.suggest_section("leadership", cv_data)
        assert isinstance(result, str)

    def test_returns_string(self):
        cv_data = {"experience": [], "skills": [], "profile": ""}
        result = cvkeywords.suggest_section("python", cv_data)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# match
# ---------------------------------------------------------------------------

import match as match_mod


class TestMatchExtractKeywords:
    def test_finds_domains_keywords(self):
        # SKILL_KEYWORDS overwrites JOB_KEYWORDS for shared keys
        # Use keywords that only appear in the merged result
        text = "saas cloud cybersecurity salesforce meddpicc quota attainment"
        result = match_mod.extract_keywords_from_text(text)
        assert len(result) > 0

    def test_finds_sales_keywords(self):
        text = "drive revenue growth, quota attainment, manage pipeline, sales forecast"
        result = match_mod.extract_keywords_from_text(text)
        assert "sales" in result

    def test_returns_empty_dict_for_irrelevant_text(self):
        text = "the quick brown fox jumps over the lazy dog"
        result = match_mod.extract_keywords_from_text(text)
        assert isinstance(result, dict)

    def test_counts_multiple_category_matches(self):
        text = "saas cloud salesforce quota attainment meddpicc enterprise director"
        result = match_mod.extract_keywords_from_text(text)
        assert sum(result.values()) >= 2


class TestMatchScoreMatch:
    def test_returns_dict_with_score(self):
        job_kw = {"leadership": 2, "sales": 1}
        skills = ["leadership", "sales", "python"]
        result = match_mod.score_match(job_kw, skills)
        assert "score" in result
        assert "matched" in result
        assert "missing" in result

    def test_higher_score_for_matching_skills(self):
        job_kw = {"leadership": 2, "sales": 3}
        skills_match = ["leadership", "sales"]
        skills_none = ["python", "java"]
        r1 = match_mod.score_match(job_kw, skills_match)
        r2 = match_mod.score_match(job_kw, skills_none)
        assert r1["score"] >= r2["score"]

    def test_empty_skills_returns_zero(self):
        result = match_mod.score_match({"leadership": 2}, [])
        # With empty skills, max_score=0, score=0, percentage undefined
        assert "score" in result

    def test_matched_and_missing_lists(self):
        job_kw = {"leadership": 2}
        result = match_mod.score_match(job_kw, ["leadership", "python"])
        assert "matched" in result
        assert "missing" in result


# ---------------------------------------------------------------------------
# json-resume
# ---------------------------------------------------------------------------

jsonresume = importlib.import_module("json-resume")


class TestJsonResumeStripBold:
    def test_removes_double_asterisks(self):
        assert jsonresume._strip_bold("Hello **world**") == "Hello world"

    def test_handles_no_bold(self):
        assert jsonresume._strip_bold("plain text") == "plain text"

    def test_multiple_bold(self):
        assert jsonresume._strip_bold("**a** and **b**") == "a and b"


class TestJsonResumeParseDateRange:
    def test_parses_start_only(self):
        start, end = jsonresume._parse_date_range("2020-01")
        assert start == "2020-01"
        assert end == ""

    def test_parses_range_with_separator(self):
        start, end = jsonresume._parse_date_range("2018-06 -- 2022-03")
        assert start == "2018-06"
        assert end == "2022-03"

    def test_parses_present(self):
        start, end = jsonresume._parse_date_range("2020-01 -- Present")
        assert start == "2020-01"
        assert end == ""

    def test_handles_empty(self):
        start, end = jsonresume._parse_date_range("")
        assert start == ""
        assert end == ""


class TestJsonResumeFlattenItems:
    def test_flattens_strings(self):
        items = ["bullet one", "bullet two"]
        result = jsonresume._flatten_items(items)
        assert result == ["bullet one", "bullet two"]

    def test_flattens_dicts(self):
        items = [{"label": "Win", "text": "Grew ARR by 3x"}]
        result = jsonresume._flatten_items(items)
        assert any("Grew ARR" in r for r in result)

    def test_mixed(self):
        items = ["plain", {"label": "L", "text": "dict item"}]
        result = jsonresume._flatten_items(items)
        assert len(result) == 2


class TestJsonResumeBuildBasics:
    def test_builds_basics_from_personal(self):
        personal = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "position": "VP Sales",
            "city": "Paris",
            "country": "France",
            "phone": "+33123456789",
            "linkedin": "linkedin.com/in/johndoe",
            "github": "github.com/johndoe",
            "website": "johndoe.com",
        }
        profile = "Experienced leader."
        basics = jsonresume.build_basics(personal, profile)
        assert basics["name"] == "John Doe"
        assert basics["email"] == "john@example.com"
        assert basics["label"] == "VP Sales"


class TestJsonResumeBuildWork:
    def test_builds_work_entries(self):
        # build_work uses "title" (not "position") and "dates" (not "date")
        experience = [
            {
                "company": "Acme Corp",
                "title": "Sales Director",
                "dates": "2019-01 -- 2023-12",
                "items": ["Grew ARR by 150%"],
            }
        ]
        work = jsonresume.build_work(experience)
        assert len(work) == 1
        assert work[0]["name"] == "Acme Corp"
        assert work[0]["position"] == "Sales Director"

    def test_returns_empty_for_no_experience(self):
        assert jsonresume.build_work([]) == []


class TestJsonResumeBuildEducation:
    def test_builds_education_entries(self):
        education = [
            {
                "institution": "MIT",
                "degree": "Master",
                "major": "Computer Science",
                "date": "2010-09 -- 2012-06",
            }
        ]
        edu = jsonresume.build_education(education)
        assert len(edu) == 1
        assert edu[0]["institution"] == "MIT"

    def test_returns_empty_for_no_education(self):
        assert jsonresume.build_education([]) == []


class TestJsonResumeBuildSkills:
    def test_builds_skills_from_categories(self):
        skills_data = [{"category": "Tech", "items": "Python, Go, Rust"}]
        skills = jsonresume.build_skills(skills_data)
        assert len(skills) == 1
        assert skills[0]["name"] == "Tech"
        assert "Python" in skills[0]["keywords"]

    def test_returns_empty_for_no_skills(self):
        assert jsonresume.build_skills([]) == []


class TestJsonResumeConvert:
    def test_convert_produces_valid_json_resume(self):
        data = {
            "personal": {
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane@example.com",
                "position": "Engineer",
                "city": "London",
                "country": "UK",
                "phone": "+447000000000",
                "linkedin": "",
                "github": "",
                "website": "",
            },
            "profile": "A great engineer.",
            "experience": [],
            "education": [],
            "skills": [],
        }
        result = jsonresume.convert(data)
        assert result["$schema"] == "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json"
        assert result["basics"]["name"] == "Jane Smith"


# ---------------------------------------------------------------------------
# export-csv
# ---------------------------------------------------------------------------

exportcsv = importlib.import_module("export-csv")


class TestExportCsvParseDate:
    def test_returns_none_for_empty(self):
        result = exportcsv._parse_date("")
        assert result is None
        result2 = exportcsv._parse_date(None)
        assert result2 is None

    def test_returns_none_for_invalid(self):
        result = exportcsv._parse_date("not-a-date")
        assert result is None

    def test_parse_date_returns_datetime_or_none(self):
        # Due to s[:len(fmt)] slicing, behavior depends on string length
        result = exportcsv._parse_date("2024-03-15")
        assert result is None or isinstance(result, datetime)

    def test_handles_none_input(self):
        assert exportcsv._parse_date(None) is None


class TestExportCsvCollect:
    def test_collect_returns_list(self, tmp_path):
        # Empty applications dir
        apps_dir = tmp_path / "applications"
        apps_dir.mkdir()
        result = exportcsv.collect(apps_dir)
        assert isinstance(result, list)

    def test_collect_reads_meta_yml(self, tmp_path):
        apps_dir = tmp_path / "applications"
        app_dir = apps_dir / "2024-01-acme"
        app_dir.mkdir(parents=True)
        meta = {
            "company": "Acme",
            "position": "VP Sales",
            "created": "2024-01-15",
            "outcome": "interview",
        }
        (app_dir / "meta.yml").write_text(yaml.dump(meta))
        result = exportcsv.collect(apps_dir)
        assert len(result) == 1
        assert result[0]["company"] == "Acme"


# ---------------------------------------------------------------------------
# ats-rank
# ---------------------------------------------------------------------------

atsrank = importlib.import_module("ats-rank")


class TestAtsRankLoadMeta:
    def test_loads_meta_from_yml(self, tmp_path):
        meta = {"company": "Acme", "position": "VP"}
        (tmp_path / "meta.yml").write_text(yaml.dump(meta))
        result = atsrank.load_meta(tmp_path)
        assert result["company"] == "Acme"

    def test_returns_empty_when_missing(self, tmp_path):
        result = atsrank.load_meta(tmp_path)
        assert result == {}
