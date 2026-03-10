"""
Phase 15 — remaining coverage gaps.

Covers:
  - ats-text.py    : main() CLI paths
  - export.py      : main() CLI paths
  - effectiveness.py : all (load_applications, main)
  - generate-dashboard.py : get_ats_score, get_pr_info
  - contacts.py    : extract_domain, _is_recruiter_context, _pick_primary,
                     save_contacts, search_hunter, search_github (mocked HTTP)
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# ats-text.py — main() CLI
# ---------------------------------------------------------------------------

ats_text = importlib.import_module("ats-text")

MINIMAL_CV = {
    "personal": {
        "first_name": "Alice",
        "last_name": "Martin",
        "position": "Engineer",
        "email": "alice@example.com",
        "mobile": "+33 6 00",
        "address": "Paris",
        "linkedin": "alice",
    },
    "profile": "Senior engineer.",
    "skills": [{"category": "Tech", "items": "Python"}],
    "key_wins": [{"title": "ARR", "text": "Grew ARR 3x"}],
    "experience": [
        {
            "title": "VP Eng",
            "company": "Acme",
            "location": "Paris",
            "dates": "2020-01 -- 2024-01",
            "items": ["Built scalable systems"],
        }
    ],
    "early_career": [
        {"title": "Dev", "company": "Beta", "location": "Lyon", "dates": "2015 -- 2020"}
    ],
    "education": [
        {"degree": "MSc CS", "school": "École Poly", "location": "Paris", "dates": "2010 -- 2015"}
    ],
    "certifications": [{"name": "AWS SAA", "institution": "Amazon", "date": "2022"}],
    "awards": "Best speaker 2021",
    "publications": "Paper on ML",
    "languages": ["English", "French"],
    "interests": ["Music", "Running"],
}

MINIMAL_CL = {
    "title": "VP Engineering",
    "opening": "Dear Hiring Manager,",
    "sections": [{"title": "Motivation", "content": "I am excited to apply."}],
    "closing_paragraph": "Thank you for your consideration.",
    "closing": "Sincerely,",
    "recipient": {"name": "John Doe", "company": "Acme"},
}


class TestAtsTextMain:
    def test_master_cv_no_app_dir(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cv.yml").write_text(yaml.dump(MINIMAL_CV))
        out_path = tmp_path / "CV.txt"
        with patch.object(ats_text, "REPO_ROOT", tmp_path), \
             patch("sys.argv", ["ats-text.py", "-o", str(out_path)]):
            rc = ats_text.main()
        assert rc == 0
        assert out_path.exists()
        assert "ALICE MARTIN" in out_path.read_text()

    def test_with_app_dir_no_tailored(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cv.yml").write_text(yaml.dump(MINIMAL_CV))
        app_dir = tmp_path / "applications" / "2026-01-acme"
        app_dir.mkdir(parents=True)
        out_path = app_dir / "CV.txt"
        with patch.object(ats_text, "REPO_ROOT", tmp_path), \
             patch("sys.argv", ["ats-text.py", str(app_dir), "--no-cl", "-o", str(out_path)]):
            rc = ats_text.main()
        assert rc == 0
        assert out_path.exists()

    def test_with_app_dir_and_coverletter(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cv.yml").write_text(yaml.dump(MINIMAL_CV))
        app_dir = tmp_path / "applications" / "2026-01-beta"
        app_dir.mkdir(parents=True)
        (app_dir / "coverletter.yml").write_text(yaml.dump(MINIMAL_CL))
        out_path = app_dir / "CV.txt"
        with patch.object(ats_text, "REPO_ROOT", tmp_path), \
             patch("sys.argv", ["ats-text.py", str(app_dir), "-o", str(out_path)]):
            rc = ats_text.main()
        assert rc == 0
        cl_out = app_dir / "CoverLetter.txt"
        assert cl_out.exists()

    def test_with_tailored_yml(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cv.yml").write_text(yaml.dump(MINIMAL_CV))
        app_dir = tmp_path / "applications" / "2026-01-gamma"
        app_dir.mkdir(parents=True)
        tailored = dict(MINIMAL_CV)
        tailored["personal"] = dict(MINIMAL_CV["personal"])
        tailored["personal"]["first_name"] = "Tailored"
        (app_dir / "cv-tailored.yml").write_text(yaml.dump(tailored))
        out_path = app_dir / "CV.txt"
        with patch.object(ats_text, "REPO_ROOT", tmp_path), \
             patch("sys.argv", ["ats-text.py", str(app_dir), "--no-cl", "-o", str(out_path)]):
            rc = ats_text.main()
        assert rc == 0
        assert "TAILORED" in out_path.read_text()

    def test_missing_app_dir_exits(self, tmp_path):
        with patch("sys.argv", ["ats-text.py", str(tmp_path / "nonexistent"), "--no-cl"]):
            with pytest.raises(SystemExit) as exc:
                ats_text.main()
        assert exc.value.code != 0


# ---------------------------------------------------------------------------
# export.py — main() CLI
# ---------------------------------------------------------------------------

import export as export_mod

SAMPLE_DATA = {
    "personal": {
        "first_name": "Jane",
        "last_name": "Smith",
        "position": "Manager",
        "email": "jane@example.com",
        "mobile": "+1 555",
        "address": "NYC",
        "linkedin": "jane",
        "github": "janesmith",
    },
    "profile": "Senior manager.",
    "skills": [{"category": "Tech", "items": "Python, Go"}],
    "key_wins": [{"title": "Growth", "text": "3x ARR"}],
    "experience": [
        {
            "title": "Director",
            "company": "Acme",
            "location": "NYC",
            "dates": "2020 -- 2024",
            "items": [{"label": "Leadership", "text": "Led team of 20"}],
        }
    ],
    "early_career": [
        {"title": "Dev", "company": "Beta", "location": "LA", "dates": "2015 -- 2020"}
    ],
    "education": [
        {"degree": "BS CS", "school": "MIT", "location": "Boston", "dates": "2011 -- 2015"}
    ],
    "certifications": [{"name": "PMP", "institution": "PMI", "date": "2021"}],
    "awards": "Top performer 2022",
    "publications": "None",
    "languages": ["English"],
    "interests": ["Hiking"],
}


class TestExportMain:
    def test_json_to_stdout(self, tmp_path, capsys):
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text(yaml.dump(SAMPLE_DATA))
        with patch("sys.argv", ["export.py", "json", "-d", str(cv_path)]):
            rc = export_mod.main()
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "personal" in data or "experience" in data

    def test_markdown_to_file(self, tmp_path):
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text(yaml.dump(SAMPLE_DATA))
        out_path = tmp_path / "cv.md"
        with patch("sys.argv", ["export.py", "markdown", "-d", str(cv_path), "-o", str(out_path)]):
            rc = export_mod.main()
        assert rc == 0
        assert out_path.exists()
        assert "Jane Smith" in out_path.read_text()

    def test_text_to_stdout(self, tmp_path, capsys):
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text(yaml.dump(SAMPLE_DATA))
        with patch("sys.argv", ["export.py", "text", "-d", str(cv_path)]):
            rc = export_mod.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "Jane Smith" in out

    def test_missing_data_file_exits(self, tmp_path):
        with patch("sys.argv", ["export.py", "json", "-d", str(tmp_path / "missing.yml")]):
            with pytest.raises(SystemExit) as exc:
                export_mod.main()
        assert exc.value.code != 0

    def test_md_alias(self, tmp_path, capsys):
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text(yaml.dump(SAMPLE_DATA))
        with patch("sys.argv", ["export.py", "md", "-d", str(cv_path)]):
            rc = export_mod.main()
        assert rc == 0

    def test_txt_alias(self, tmp_path, capsys):
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text(yaml.dump(SAMPLE_DATA))
        with patch("sys.argv", ["export.py", "txt", "-d", str(cv_path)]):
            rc = export_mod.main()
        assert rc == 0


# ---------------------------------------------------------------------------
# effectiveness.py
# ---------------------------------------------------------------------------

import effectiveness as eff_mod


class TestEffectivenessLoadApplications:
    def test_returns_list_when_no_dir(self, tmp_path):
        with patch.object(eff_mod, "WORKDIR", tmp_path):
            apps = eff_mod.load_applications()
        assert apps == []

    def test_returns_list_when_empty_dir(self, tmp_path):
        (tmp_path / "applications").mkdir()
        with patch.object(eff_mod, "WORKDIR", tmp_path):
            apps = eff_mod.load_applications()
        assert apps == []

    def test_skips_apps_without_meta(self, tmp_path):
        app_dir = tmp_path / "applications" / "2026-01-acme"
        app_dir.mkdir(parents=True)
        with patch.object(eff_mod, "WORKDIR", tmp_path):
            apps = eff_mod.load_applications()
        assert apps == []

    def test_loads_meta_fields(self, tmp_path):
        app_dir = tmp_path / "applications" / "2026-01-acme"
        app_dir.mkdir(parents=True)
        (app_dir / "meta.yml").write_text(
            "company: Acme\nposition: VP\noutcome: interview\n"
        )
        with patch.object(eff_mod, "WORKDIR", tmp_path):
            apps = eff_mod.load_applications()
        assert len(apps) == 1
        assert apps[0]["company"] == "Acme"
        assert apps[0]["outcome"] == "interview"

    def test_loads_ats_score_when_job_txt(self, tmp_path):
        app_dir = tmp_path / "applications" / "2026-01-scored"
        app_dir.mkdir(parents=True)
        (app_dir / "meta.yml").write_text("company: Scored\noutcome: offer\n")
        (app_dir / "job.txt").write_text("python cloud saas")
        fake_result = MagicMock(returncode=0, stdout=json.dumps({"score": 85.0, "found_count": 10, "total_keywords": 12}))
        with patch.object(eff_mod, "WORKDIR", tmp_path), \
             patch("subprocess.run", return_value=fake_result):
            apps = eff_mod.load_applications()
        assert apps[0].get("ats_score") == 85.0

    def test_handles_ats_score_failure(self, tmp_path):
        app_dir = tmp_path / "applications" / "2026-01-fail"
        app_dir.mkdir(parents=True)
        (app_dir / "meta.yml").write_text("company: Fail\noutcome: \n")
        (app_dir / "job.txt").write_text("some job")
        import subprocess
        with patch.object(eff_mod, "WORKDIR", tmp_path), \
             patch("subprocess.run", side_effect=FileNotFoundError("not found")):
            apps = eff_mod.load_applications()
        assert "ats_score" not in apps[0]


class TestEffectivenessMain:
    def test_no_apps_returns_zero(self, tmp_path, capsys):
        with patch.object(eff_mod, "WORKDIR", tmp_path):
            rc = eff_mod.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "No applications" in out

    def test_with_apps_prints_report(self, tmp_path, capsys):
        app_dir = tmp_path / "applications" / "2026-01-acme"
        app_dir.mkdir(parents=True)
        (app_dir / "meta.yml").write_text(
            "company: Acme\nposition: VP\noutcome: interview\n"
        )
        with patch.object(eff_mod, "WORKDIR", tmp_path):
            rc = eff_mod.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "Total applications" in out

    def test_outcome_breakdown_printed(self, tmp_path, capsys):
        apps_dir = tmp_path / "applications"
        for name, outcome in [
            ("2026-01-a", "interview"),
            ("2026-01-b", "rejected"),
            ("2026-01-c", "offer"),
        ]:
            d = apps_dir / name
            d.mkdir(parents=True)
            (d / "meta.yml").write_text(f"company: {name}\noutcome: {outcome}\n")
        with patch.object(eff_mod, "WORKDIR", tmp_path):
            rc = eff_mod.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "Outcome" in out
        assert "Interview rate" in out

    def test_ats_correlation_printed(self, tmp_path, capsys):
        apps_dir = tmp_path / "applications"
        for name, outcome, score in [
            ("2026-01-a", "interview", 85.0),
            ("2026-01-b", "rejected", 55.0),
        ]:
            d = apps_dir / name
            d.mkdir(parents=True)
            (d / "meta.yml").write_text(f"company: {name}\noutcome: {outcome}\n")
            (d / "job.txt").write_text("python cloud")
        fake_result = MagicMock(returncode=0, stdout=json.dumps({"score": 85.0, "found_count": 5, "total_keywords": 6}))
        with patch.object(eff_mod, "WORKDIR", tmp_path), \
             patch("subprocess.run", return_value=fake_result):
            rc = eff_mod.main()
        assert rc == 0

    def test_response_days_printed(self, tmp_path, capsys):
        app_dir = tmp_path / "applications" / "2026-01-acme"
        app_dir.mkdir(parents=True)
        (app_dir / "meta.yml").write_text(
            "company: Acme\noutcome: interview\nresponse_days: 7\n"
        )
        with patch.object(eff_mod, "WORKDIR", tmp_path):
            rc = eff_mod.main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "response time" in out.lower()


# ---------------------------------------------------------------------------
# generate-dashboard.py — get_ats_score, get_pr_info
# ---------------------------------------------------------------------------

dashboard = importlib.import_module("generate-dashboard")


class TestGetAtsScore:
    def test_returns_score_when_job_txt_exists(self, tmp_path):
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "job.txt").write_text("python cloud")
        fake = MagicMock(returncode=0, stdout=json.dumps({"score": 78.5}))
        with patch("subprocess.run", return_value=fake):
            score = dashboard.get_ats_score(app_dir)
        assert score == 78.5

    def test_returns_none_when_no_job_txt(self, tmp_path):
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        score = dashboard.get_ats_score(app_dir)
        assert score is None

    def test_returns_none_on_subprocess_failure(self, tmp_path):
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "job.txt").write_text("python")
        with patch("subprocess.run", side_effect=Exception("fail")):
            score = dashboard.get_ats_score(app_dir)
        assert score is None

    def test_returns_none_on_bad_json(self, tmp_path):
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "job.txt").write_text("python")
        fake = MagicMock(returncode=0, stdout="not json")
        with patch("subprocess.run", return_value=fake):
            score = dashboard.get_ats_score(app_dir)
        assert score is None


class TestGetPrInfo:
    def test_returns_dict_on_success(self):
        fake_resp = MagicMock()
        fake_resp.returncode = 0
        fake_resp.stdout = json.dumps({"state": "OPEN", "labels": []})
        with patch("subprocess.run", return_value=fake_resp):
            result = dashboard.get_pr_info("2026-01-acme")
        assert isinstance(result, dict)

    def test_returns_empty_dict_on_failure(self):
        with patch("subprocess.run", side_effect=Exception("gh not found")):
            result = dashboard.get_pr_info("2026-01-acme")
        assert result == {}

    def test_returns_empty_dict_on_bad_json(self):
        fake_resp = MagicMock(returncode=0, stdout="not json")
        with patch("subprocess.run", return_value=fake_resp):
            result = dashboard.get_pr_info("2026-01-acme")
        assert result == {}


# ---------------------------------------------------------------------------
# contacts.py
# ---------------------------------------------------------------------------

import contacts as contacts_mod


class TestExtractDomain:
    def test_from_job_url(self, tmp_path):
        (tmp_path / "job.url").write_text("https://careers.acme.com/jobs/123")
        domain = contacts_mod.extract_domain(tmp_path, "Acme")
        assert "acme.com" in domain

    def test_strips_www(self, tmp_path):
        (tmp_path / "job.url").write_text("https://www.acme.com/about")
        domain = contacts_mod.extract_domain(tmp_path, "Acme")
        assert domain == "acme.com"

    def test_fallback_to_company_name(self, tmp_path):
        domain = contacts_mod.extract_domain(tmp_path, "Acme Corp")
        assert domain == "acmecorp.com"

    def test_ignores_linkedin(self, tmp_path):
        (tmp_path / "job.url").write_text("https://www.linkedin.com/jobs/view/123")
        domain = contacts_mod.extract_domain(tmp_path, "Acme")
        # Should fall back to company name since linkedin is a job board
        assert "acme" in domain

    def test_greenhouse_url(self, tmp_path):
        (tmp_path / "job.url").write_text("https://boards.greenhouse.io/acme/jobs/123")
        domain = contacts_mod.extract_domain(tmp_path, "Acme")
        # boards.greenhouse.io stripped → acme/jobs/123 → acme (first part)
        assert isinstance(domain, str)

    def test_no_job_url_file(self, tmp_path):
        domain = contacts_mod.extract_domain(tmp_path, "Beta Inc")
        assert domain == "betainc.com"


class TestIsRecruiterContext:
    def test_recruiter_keyword(self):
        assert contacts_mod._is_recruiter_context("Head of Talent Acquisition") is True

    def test_hr_keyword(self):
        assert contacts_mod._is_recruiter_context("HR Manager") is True

    def test_people_keyword(self):
        assert contacts_mod._is_recruiter_context("People Partner") is True

    def test_non_recruiter(self):
        assert contacts_mod._is_recruiter_context("Senior Software Engineer") is False

    def test_empty_string(self):
        assert contacts_mod._is_recruiter_context("") is False


class TestPickPrimary:
    def test_returns_none_for_empty(self):
        assert contacts_mod._pick_primary([]) is None

    def test_prefers_hunter_source(self):
        contacts = [
            {"source": "website", "confidence": 90, "name": "Web", "email": "web@a.com", "position": "CEO"},
            {"source": "hunter", "confidence": 70, "name": "Hunter", "email": "h@a.com", "position": "Recruiter"},
        ]
        result = contacts_mod._pick_primary(contacts)
        assert result["source"] == "hunter"

    def test_prefers_recruiter_role(self):
        contacts = [
            {"source": "hunter", "confidence": 80, "name": "A", "email": "a@a.com", "position": "CTO"},
            {"source": "hunter", "confidence": 70, "name": "B", "email": "b@a.com", "position": "Talent Acquisition"},
        ]
        result = contacts_mod._pick_primary(contacts)
        assert result["name"] == "B"

    def test_returns_first_if_no_recruiter(self):
        contacts = [
            {"source": "github", "confidence": 30, "name": "Dev", "email": "dev@a.com", "position": "Engineer"},
        ]
        result = contacts_mod._pick_primary(contacts)
        assert result is not None


class TestSaveContacts:
    def test_creates_contacts_md(self, tmp_path):
        contacts_mod.save_contacts(tmp_path, "Acme", "acme.com", [], [], [])
        assert (tmp_path / "contacts.md").exists()

    def test_contains_company_name(self, tmp_path):
        contacts_mod.save_contacts(tmp_path, "Acme Corp", "acme.com", [], [], [])
        content = (tmp_path / "contacts.md").read_text()
        assert "Acme Corp" in content

    def test_hunter_contacts_in_table(self, tmp_path):
        hunter = [{"name": "Jane", "email": "j@acme.com", "position": "Recruiter", "confidence": 85, "source": "hunter"}]
        contacts_mod.save_contacts(tmp_path, "Acme", "acme.com", hunter, [], [])
        content = (tmp_path / "contacts.md").read_text()
        assert "j@acme.com" in content
        assert "Hunter.io" in content

    def test_website_contacts_listed(self, tmp_path):
        website = [{"email": "hr@acme.com", "confidence": 50, "source": "website", "name": "", "position": "Contact"}]
        contacts_mod.save_contacts(tmp_path, "Acme", "acme.com", [], website, [])
        content = (tmp_path / "contacts.md").read_text()
        assert "hr@acme.com" in content

    def test_github_contacts_listed(self, tmp_path):
        github = [{"name": "Dev", "email": "dev@a.com", "handle": "devuser", "confidence": 30, "source": "github", "position": ""}]
        contacts_mod.save_contacts(tmp_path, "Acme", "acme.com", [], [], github)
        content = (tmp_path / "contacts.md").read_text()
        assert "devuser" in content

    def test_no_contacts_shows_fallback(self, tmp_path):
        contacts_mod.save_contacts(tmp_path, "Acme", "acme.com", [], [], [])
        content = (tmp_path / "contacts.md").read_text()
        assert "No contacts found" in content or "LinkedIn" in content

    def test_suggested_contact_when_primary(self, tmp_path):
        hunter = [{"name": "Jane HR", "email": "j@acme.com", "position": "Talent", "confidence": 90, "source": "hunter"}]
        contacts_mod.save_contacts(tmp_path, "Acme", "acme.com", hunter, [], [])
        content = (tmp_path / "contacts.md").read_text()
        assert "Primary contact" in content or "j@acme.com" in content


class TestSearchHunterMocked:
    def test_returns_empty_without_key(self):
        result = contacts_mod.search_hunter("acme.com", "")
        assert result == []

    def test_returns_contacts_on_success(self):
        payload = {
            "data": {
                "emails": [
                    {"first_name": "Jane", "last_name": "Doe", "value": "jane@acme.com", "position": "Recruiter", "confidence": 85}
                ]
            }
        }
        import urllib.request
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = contacts_mod.search_hunter("acme.com", "fake-key")
        assert len(result) == 1
        assert result[0]["email"] == "jane@acme.com"
        assert result[0]["source"] == "hunter"

    def test_handles_http_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(None, 401, "Unauthorized", {}, None)):
            result = contacts_mod.search_hunter("acme.com", "bad-key")
        assert result == []

    def test_handles_rate_limit(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(None, 429, "Too Many", {}, None)):
            result = contacts_mod.search_hunter("acme.com", "key")
        assert result == []


class TestSearchGithubMocked:
    def test_returns_empty_when_no_requests(self):
        with patch.object(contacts_mod, "HAS_REQUESTS", False):
            result = contacts_mod.search_github("Acme")
        assert result == []

    def test_returns_contacts_with_email(self):
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"items": [{"login": "janedoe"}]}
        profile_resp = MagicMock()
        profile_resp.status_code = 200
        profile_resp.json.return_value = {"email": "jane@acme.com", "name": "Jane Doe", "bio": "Recruiter"}
        with patch.object(contacts_mod, "HAS_REQUESTS", True), \
             patch("requests.get", side_effect=[search_resp, profile_resp]):
            result = contacts_mod.search_github("Acme")
        assert len(result) == 1
        assert result[0]["email"] == "jane@acme.com"

    def test_returns_empty_on_403(self):
        resp = MagicMock(status_code=403)
        with patch.object(contacts_mod, "HAS_REQUESTS", True), \
             patch("requests.get", return_value=resp):
            result = contacts_mod.search_github("Acme")
        assert result == []

    def test_handles_exception(self):
        with patch.object(contacts_mod, "HAS_REQUESTS", True), \
             patch("requests.get", side_effect=Exception("network error")):
            result = contacts_mod.search_github("Acme")
        assert result == []
