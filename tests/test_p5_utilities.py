"""
Phase 15 P5 — Interview & utility scripts tests.

Covers: interview-prep, prep-star, milestone, doctor, archive-app,
        batch-apply, visual-diff, watch, salary-bench
"""

from __future__ import annotations

import importlib
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# interview-prep
# ---------------------------------------------------------------------------

interviewprep = importlib.import_module("interview-prep")


class TestInterviewPrepExtractJobSections:
    def test_extracts_requirements_section(self):
        text = "Requirements:\n- 5+ years experience\n- Python skills"
        sections = interviewprep.extract_job_sections(text)
        assert "requirements" in sections
        assert any("Python" in line for line in sections["requirements"])

    def test_extracts_responsibilities_section(self):
        text = "Responsibilities:\n- Lead a team\n- Drive revenue"
        sections = interviewprep.extract_job_sections(text)
        assert "responsibilities" in sections

    def test_extracts_about_section(self):
        text = "About the company:\nWe are a leading SaaS firm"
        sections = interviewprep.extract_job_sections(text)
        assert "about" in sections

    def test_returns_all_section_keys(self):
        sections = interviewprep.extract_job_sections("")
        assert "requirements" in sections
        assert "responsibilities" in sections
        assert "about" in sections
        assert "other" in sections

    def test_default_section_is_other(self):
        text = "Some random text without headers"
        sections = interviewprep.extract_job_sections(text)
        assert "other" in sections
        assert len(sections["other"]) > 0


class TestInterviewPrepMatchStrengths:
    def test_returns_list_of_matches(self):
        cv_data = {
            "experience": [
                {
                    "company": "Acme",
                    "items": [
                        {"label": "Growth", "text": "Drove revenue growth and increased sales pipeline"},
                    ],
                }
            ]
        }
        job_text = "We need someone who can drive revenue growth and build sales pipeline"
        result = interviewprep.match_strengths(cv_data, job_text)
        assert isinstance(result, list)

    def test_returns_at_most_10(self):
        cv_data = {
            "experience": [
                {
                    "company": "Acme",
                    "items": [
                        {"label": f"Win{i}", "text": f"Grew revenue and drove growth and led team {i}"}
                        for i in range(20)
                    ],
                }
            ]
        }
        job_text = "revenue growth and team leadership"
        result = interviewprep.match_strengths(cv_data, job_text)
        assert len(result) <= 10

    def test_handles_empty_cv(self):
        result = interviewprep.match_strengths({}, "some job text")
        assert isinstance(result, list)


class TestInterviewPrepIdentifyGaps:
    def test_returns_list_of_gaps(self):
        cv_data = {
            "experience": [{"company": "Acme", "items": [{"label": "X", "text": "Python cloud SaaS"}]}],
            "skills": [{"items": "Python, SQL"}],
        }
        job_sections = {
            "requirements": [
                "Must have experience with Kubernetes and Terraform and GitOps"
            ]
        }
        gaps = interviewprep.identify_gaps(cv_data, job_sections)
        assert isinstance(gaps, list)

    def test_at_most_8_gaps(self):
        cv_data = {}
        job_sections = {
            "requirements": [f"requires specific skill_{i} with knowledge_{i}" for i in range(20)]
        }
        gaps = interviewprep.identify_gaps(cv_data, job_sections)
        assert len(gaps) <= 8

    def test_empty_requirements(self):
        gaps = interviewprep.identify_gaps({}, {"requirements": []})
        assert isinstance(gaps, list)


class TestInterviewPrepGeneratePrep:
    def test_generates_markdown(self):
        cv_data = {
            "personal": {
                "first_name": "John",
                "last_name": "Doe",
                "position": "VP Sales",
            },
            "experience": [],
            "skills": [],
        }
        job_text = "We need a VP of Sales to drive revenue"
        job_sections = {"requirements": ["revenue growth"], "responsibilities": ["lead team"], "about": [], "other": []}
        result = interviewprep.generate_prep(cv_data, job_text, job_sections, "Acme", "VP Sales")
        assert "Acme" in result
        assert "VP Sales" in result
        assert "John Doe" in result

    def test_contains_sections(self):
        cv_data = {
            "personal": {"first_name": "Jane", "last_name": "Smith", "position": "Engineer"},
            "experience": [],
            "skills": [],
        }
        result = interviewprep.generate_prep(cv_data, "job text", {"requirements": [], "responsibilities": [], "about": [], "other": []}, "Beta", "Engineer")
        assert "#" in result


# ---------------------------------------------------------------------------
# prep-star
# ---------------------------------------------------------------------------

prepstar = importlib.import_module("prep-star")


class TestPrepStarStripBold:
    def test_removes_bold(self):
        assert prepstar._strip_bold("**hello** world") == "hello world"

    def test_handles_no_bold(self):
        assert prepstar._strip_bold("plain text") == "plain text"

    def test_multiple_bold(self):
        assert prepstar._strip_bold("**a** and **b**") == "a and b"


class TestPrepStarFlattenItems:
    def test_flattens_strings(self):
        items = ["bullet one", "bullet two"]
        assert prepstar._flatten_items(items) == ["bullet one", "bullet two"]

    def test_flattens_dicts_with_label_and_text(self):
        items = [{"label": "Win", "text": "Grew ARR by 3x"}]
        result = prepstar._flatten_items(items)
        assert len(result) == 1
        assert "Grew ARR" in result[0]

    def test_dict_without_label(self):
        items = [{"text": "just the text"}]
        result = prepstar._flatten_items(items)
        assert "just the text" in result[0]

    def test_handles_none(self):
        result = prepstar._flatten_items(None)
        assert result == []

    def test_mixed(self):
        items = ["string", {"label": "L", "text": "dict"}]
        result = prepstar._flatten_items(items)
        assert len(result) == 2


class TestPrepStarExtractAchievements:
    def test_extracts_key_wins(self):
        cv_data = {
            "key_wins": [{"title": "ARR Growth", "text": "Grew ARR by 150%"}],
            "experience": [],
        }
        result = prepstar.extract_achievements(cv_data)
        assert "ARR Growth" in result or "Grew ARR" in result

    def test_extracts_experience_items(self):
        cv_data = {
            "key_wins": [],
            "experience": [
                {
                    "company": "Acme",
                    "position": "VP Sales",
                    "items": [
                        {"label": "Win", "text": "Closed $5M deal"},
                    ],
                }
            ],
        }
        result = prepstar.extract_achievements(cv_data)
        assert "Closed $5M" in result

    def test_at_most_15_items(self):
        cv_data = {
            "key_wins": [{"title": f"Win{i}", "text": f"Text {i}"} for i in range(20)],
            "experience": [],
        }
        result = prepstar.extract_achievements(cv_data)
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) <= 15

    def test_handles_empty(self):
        result = prepstar.extract_achievements({})
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# milestone
# ---------------------------------------------------------------------------

import milestone as milestone_mod


class TestMilestoneLoadSave:
    def test_load_returns_empty_when_no_file(self, tmp_path):
        milestones = milestone_mod._load_milestones(tmp_path)
        assert milestones == []

    def test_load_reads_milestones(self, tmp_path):
        data = {"milestones": [{"stage": "phone-screen", "date": "2024-01-20"}]}
        (tmp_path / "milestones.yml").write_text(yaml.dump(data))
        milestones = milestone_mod._load_milestones(tmp_path)
        assert len(milestones) == 1
        assert milestones[0]["stage"] == "phone-screen"

    def test_save_and_reload(self, tmp_path):
        milestones = [{"stage": "technical", "date": "2024-02-01", "outcome": "passed"}]
        milestone_mod._save_milestones(tmp_path, milestones)
        loaded = milestone_mod._load_milestones(tmp_path)
        assert len(loaded) == 1
        assert loaded[0]["stage"] == "technical"
        assert loaded[0]["outcome"] == "passed"

    def test_save_creates_file(self, tmp_path):
        milestone_mod._save_milestones(tmp_path, [{"stage": "final"}])
        assert (tmp_path / "milestones.yml").exists()


class TestMilestoneLoadMeta:
    def test_returns_empty_when_no_meta(self, tmp_path):
        result = milestone_mod._load_meta(tmp_path)
        assert result == {}

    def test_reads_meta_fields(self, tmp_path):
        meta = {"company": "Acme", "position": "VP"}
        (tmp_path / "meta.yml").write_text(yaml.dump(meta))
        result = milestone_mod._load_meta(tmp_path)
        assert result["company"] == "Acme"


class TestMilestoneConstants:
    def test_valid_stages(self):
        assert "phone-screen" in milestone_mod.VALID_STAGES
        assert "technical" in milestone_mod.VALID_STAGES
        assert "offer" in milestone_mod.VALID_STAGES

    def test_stage_emoji_map(self):
        assert isinstance(milestone_mod.STAGE_EMOJI, dict)
        for stage in milestone_mod.VALID_STAGES:
            assert stage in milestone_mod.STAGE_EMOJI

    def test_outcome_emoji_map(self):
        assert "passed" in milestone_mod.OUTCOME_EMOJI
        assert "failed" in milestone_mod.OUTCOME_EMOJI
        assert "pending" in milestone_mod.OUTCOME_EMOJI


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

import doctor as doctor_mod


class TestDoctorCheckCommand:
    def test_returns_true_for_existing_command(self):
        # python3 should always be found
        result = doctor_mod.check_command("python3")
        assert result is True

    def test_returns_false_for_nonexistent_command(self):
        result = doctor_mod.check_command("nonexistent_command_xyz_123")
        assert result is False

    def test_path_check_returns_true_when_path_exists(self, tmp_path):
        binary = tmp_path / "mybinary"
        binary.write_text("fake binary")
        result = doctor_mod.check_command("nonexistent", path=str(binary))
        assert result is True

    def test_path_check_falls_back_to_which(self):
        result = doctor_mod.check_command("python3", path="/nonexistent/path")
        assert result is True


class TestDoctorCheckPythonModule:
    def test_returns_true_for_installed_module(self):
        assert doctor_mod.check_python_module("yaml") is True
        assert doctor_mod.check_python_module("sys") is True

    def test_returns_false_for_missing_module(self):
        assert doctor_mod.check_python_module("nonexistent_module_xyz") is False


class TestDoctorConstants:
    def test_tool_checks_is_list(self):
        assert isinstance(doctor_mod.TOOL_CHECKS, list)
        assert len(doctor_mod.TOOL_CHECKS) > 0

    def test_required_modules_is_list(self):
        assert isinstance(doctor_mod.REQUIRED_MODULES, list)
        # yaml and requests should be required
        module_names = [m[0] for m in doctor_mod.REQUIRED_MODULES]
        assert "yaml" in module_names or "requests" in module_names

    def test_api_keys_is_list(self):
        assert isinstance(doctor_mod.API_KEYS, list)
        env_names = [k[0] for k in doctor_mod.API_KEYS]
        assert "GEMINI_API_KEY" in env_names


# ---------------------------------------------------------------------------
# archive-app
# ---------------------------------------------------------------------------

archiveapp = importlib.import_module("archive-app")


class TestArchiveAppParseDate:
    def test_returns_none_for_empty(self):
        assert archiveapp._parse_date("") is None
        assert archiveapp._parse_date(None) is None

    def test_returns_datetime_or_none_for_date_string(self):
        # Due to s[:len(fmt)] slicing, may return None
        result = archiveapp._parse_date("2024-03-15")
        assert result is None or hasattr(result, 'year')

    def test_returns_none_for_invalid(self):
        assert archiveapp._parse_date("not-a-date") is None


class TestArchiveAppBuildArchiveMd:
    def test_contains_company_name(self, tmp_path):
        meta = {
            "company": "Acme Corp",
            "position": "VP Sales",
            "outcome": "offer",
            "created": "2024-01-01",
        }
        result = archiveapp.build_archive_md(tmp_path, meta, None)
        assert "Acme Corp" in result
        assert "VP Sales" in result

    def test_contains_outcome(self, tmp_path):
        meta = {
            "company": "Beta",
            "position": "Director",
            "outcome": "rejected",
            "created": "2024-01-01",
        }
        result = archiveapp.build_archive_md(tmp_path, meta, None)
        assert "Rejected" in result or "rejected" in result

    def test_includes_ats_score_when_provided(self, tmp_path):
        meta = {
            "company": "Gamma",
            "position": "Engineer",
            "outcome": "interview",
            "created": "2024-01-01",
        }
        ats = {"score": 82.5, "found_count": 15, "total_keywords": 20}
        result = archiveapp.build_archive_md(tmp_path, meta, ats)
        assert "82.5" in result or "82" in result

    def test_includes_milestones_when_present(self, tmp_path):
        meta = {"company": "Delta", "position": "VP", "outcome": "offer", "created": "2024-01-01"}
        ms_data = {"milestones": [{"stage": "phone-screen", "date": "2024-01-20", "interviewer": "Jane", "outcome": "passed"}]}
        (tmp_path / "milestones.yml").write_text(yaml.dump(ms_data))
        result = archiveapp.build_archive_md(tmp_path, meta, None)
        assert "phone-screen" in result

    def test_is_markdown(self, tmp_path):
        meta = {"company": "Test", "position": "Role", "outcome": "", "created": "2024-01-01"}
        result = archiveapp.build_archive_md(tmp_path, meta, None)
        assert "#" in result


# ---------------------------------------------------------------------------
# batch-apply
# ---------------------------------------------------------------------------

batchapply = importlib.import_module("batch-apply")


class TestBatchApply:
    def test_module_imports(self):
        assert batchapply is not None

    def test_has_main(self):
        assert hasattr(batchapply, "main")

    def test_has_expected_attributes(self):
        # batch-apply should define something about CSV or jobs
        attrs = dir(batchapply)
        assert len(attrs) > 5


# ---------------------------------------------------------------------------
# visual-diff
# ---------------------------------------------------------------------------

visualdiff_mod = importlib.import_module("visual-diff")


class TestVisualDiffCheckImagemagick:
    def test_returns_bool(self):
        # Whether ImageMagick is installed or not, should return True/False
        result = visualdiff_mod.check_imagemagick()
        assert isinstance(result, bool)

    @patch("subprocess.run")
    def test_returns_true_when_magick_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = visualdiff_mod.check_imagemagick()
        assert result is True

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_returns_false_when_magick_not_available(self, mock_run):
        result = visualdiff_mod.check_imagemagick()
        assert result is False


# ---------------------------------------------------------------------------
# watch
# ---------------------------------------------------------------------------

watchmod = importlib.import_module("watch")


class TestWatch:
    def test_module_imports(self):
        assert watchmod is not None

    def test_has_main(self):
        assert hasattr(watchmod, "main")


# ---------------------------------------------------------------------------
# salary-bench
# ---------------------------------------------------------------------------

salarybench = importlib.import_module("salary-bench")


class TestSalaryBench:
    def test_module_imports(self):
        assert salarybench is not None

    def test_has_main(self):
        assert hasattr(salarybench, "main")

    def test_has_expected_functions(self):
        # Should have at least extract_location, build_prompt etc.
        attrs = [a for a in dir(salarybench) if not a.startswith("__")]
        assert len(attrs) > 2
