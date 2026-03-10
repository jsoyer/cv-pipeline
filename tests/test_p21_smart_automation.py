"""
Phase 21 — Smart automation tests.

Covers: doctor.py --fix helpers, semantic-search.py, smart-followup.py
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    module_name = name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# doctor.py — --fix helpers
# ---------------------------------------------------------------------------


class TestDoctorFixHelpers:
    def test_fix_env_file_copies_example(self, tmp_path):
        mod = _load("doctor")
        example = tmp_path / ".env.example"
        example.write_text("GEMINI_API_KEY=\n", encoding="utf-8")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            result = mod._fix_env_file()
        assert result is True
        assert (tmp_path / ".env").exists()
        assert "GEMINI_API_KEY" in (tmp_path / ".env").read_text()

    def test_fix_env_file_creates_template_when_no_example(self, tmp_path):
        mod = _load("doctor")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            result = mod._fix_env_file()
        assert result is True
        env_content = (tmp_path / ".env").read_text()
        assert "GEMINI_API_KEY" in env_content

    def test_fix_env_file_noop_when_exists(self, tmp_path):
        mod = _load("doctor")
        (tmp_path / ".env").write_text("existing", encoding="utf-8")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            result = mod._fix_env_file()
        assert result is False
        # File unchanged
        assert (tmp_path / ".env").read_text() == "existing"

    def test_fix_submodule_calls_git(self):
        mod = _load("doctor")
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = mod._fix_submodule()
        assert result is True
        args = mock_run.call_args[0][0]
        assert "submodule" in args

    def test_fix_submodule_returns_false_on_failure(self):
        mod = _load("doctor")
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            result = mod._fix_submodule()
        assert result is False

    def test_fix_pip_modules_installs_missing(self):
        mod = _load("doctor")
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            with patch.object(mod, "check_python_module", return_value=False):
                fixed = mod._fix_pip_modules([("fakemod", "FakeMod", "pip install fakemod")])
        assert "FakeMod" in fixed

    def test_fix_pip_modules_skips_installed(self):
        mod = _load("doctor")
        with patch.object(mod, "check_python_module", return_value=True):
            fixed = mod._fix_pip_modules([("yaml", "PyYAML", "pip install pyyaml")])
        assert fixed == []

    def test_main_fix_flag_accepted(self, tmp_path, capsys):
        mod = _load("doctor")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch("sys.argv", ["doctor.py", "--fix"]):
                with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
                    mod.main()
        out = capsys.readouterr().out
        assert "FIX MODE" in out or "Doctor" in out


# ---------------------------------------------------------------------------
# semantic-search.py — TF-IDF helpers
# ---------------------------------------------------------------------------


class TestSemanticTfIdf:
    def test_tokenize_removes_stop_words(self):
        mod = _load("semantic-search")
        tokens = mod._tokenize("the quick brown fox and the lazy dog")
        assert "the" not in tokens
        assert "and" not in tokens
        assert "quick" in tokens or "brown" in tokens

    def test_tokenize_lowercases(self):
        mod = _load("semantic-search")
        tokens = mod._tokenize("Python API Kubernetes")
        assert "python" in tokens
        assert "api" in tokens

    def test_tf_sums_to_less_than_one(self):
        mod = _load("semantic-search")
        tf = mod._tf(["python", "api", "python", "kubernetes"])
        assert all(0 < v <= 1 for v in tf.values())
        assert tf["python"] == pytest.approx(0.5)

    def test_build_idf_rare_terms_higher(self):
        mod = _load("semantic-search")
        docs = [["python", "api"], ["python", "java"], ["python", "rust"]]
        idf = mod._build_idf(docs)
        # "python" appears in all 3 docs, others in 1 → idf(other) > idf(python)
        assert idf["api"] > idf["python"]

    def test_cosine_identical_vectors(self):
        mod = _load("semantic-search")
        v = {"python": 0.5, "api": 0.3}
        assert mod._cosine(v, v) == pytest.approx(1.0)

    def test_cosine_orthogonal_vectors(self):
        mod = _load("semantic-search")
        a = {"python": 1.0}
        b = {"java": 1.0}
        assert mod._cosine(a, b) == pytest.approx(0.0)

    def test_cosine_zero_vector(self):
        mod = _load("semantic-search")
        assert mod._cosine({}, {"python": 1.0}) == 0.0


class TestSearchBullets:
    def _make_cv(self, tmp_path: Path) -> Path:
        cv = {
            "experience": [{
                "company": "Acme",
                "position": "SRE",
                "items": [
                    {"text": "Led team of 12 engineers to deliver cloud platform"},
                    {"text": "Reduced infrastructure costs by 40% using spot instances"},
                    {"text": "Implemented CI/CD pipelines with GitHub Actions"},
                ],
            }],
            "projects": [],
        }
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text(yaml.dump(cv), encoding="utf-8")
        return cv_path

    def test_returns_results(self, tmp_path):
        mod = _load("semantic-search")
        cv_path = self._make_cv(tmp_path)
        results = mod.search_bullets("led engineering team delivery", cv_path, top_n=5)
        assert len(results) > 0
        assert all("score" in r for r in results)

    def test_sorted_by_score_desc(self, tmp_path):
        mod = _load("semantic-search")
        cv_path = self._make_cv(tmp_path)
        results = mod.search_bullets("led engineering team", cv_path, top_n=10)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_respected(self, tmp_path):
        mod = _load("semantic-search")
        cv_path = self._make_cv(tmp_path)
        results = mod.search_bullets("cloud platform", cv_path, top_n=2)
        assert len(results) <= 2

    def test_best_match_relevant(self, tmp_path):
        mod = _load("semantic-search")
        cv_path = self._make_cv(tmp_path)
        results = mod.search_bullets("CI/CD GitHub Actions pipelines", cv_path, top_n=3)
        # Top result should mention CI/CD or GitHub Actions
        top_text = results[0]["text"].lower()
        assert any(kw in top_text for kw in ["ci", "cd", "github", "pipeline"])


class TestSearchJobs:
    def _make_apps(self, tmp_path: Path) -> Path:
        apps = tmp_path / "applications"
        apps.mkdir()
        for name, text in [
            ("2026-01-stripe", "Python API platform engineer kubernetes cloud"),
            ("2026-02-figma", "Design engineer React TypeScript frontend product"),
            ("2026-03-datadog", "SRE monitoring kubernetes prometheus observability"),
        ]:
            d = apps / name
            d.mkdir()
            meta = {"company": name.split("-")[-1].title(), "outcome": "applied"}
            (d / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")
            (d / "job.txt").write_text(text, encoding="utf-8")
        return apps

    def test_returns_results(self, tmp_path):
        mod = _load("semantic-search")
        apps = self._make_apps(tmp_path)
        results = mod.search_jobs("kubernetes cloud monitoring SRE", apps, top_n=5)
        assert len(results) > 0

    def test_sorted_by_score(self, tmp_path):
        mod = _load("semantic-search")
        apps = self._make_apps(tmp_path)
        results = mod.search_jobs("kubernetes monitoring prometheus", apps, top_n=10)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_sre_query_matches_sre_app(self, tmp_path):
        mod = _load("semantic-search")
        apps = self._make_apps(tmp_path)
        results = mod.search_jobs("SRE observability monitoring kubernetes", apps, top_n=3)
        # datadog (SRE/kubernetes/observability) should rank highest
        assert results[0]["name"] == "2026-03-datadog"


class TestSearchKeywords:
    def test_keyword_overlap_scoring(self, tmp_path):
        mod = _load("semantic-search")
        apps = tmp_path / "applications"
        apps.mkdir()
        d = apps / "2026-01-test"
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({"company": "Test", "outcome": "applied"}), encoding="utf-8")
        (d / "job.txt").write_text("python kubernetes api microservices", encoding="utf-8")
        results = mod.search_keywords("python kubernetes java", apps, top_n=5)
        assert len(results) > 0
        assert results[0]["score"] > 0
        assert "python" in results[0]["matched_keywords"] or "kubernetes" in results[0]["matched_keywords"]


# ---------------------------------------------------------------------------
# smart-followup.py
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_yyyy_mm_dd(self):
        mod = _load("smart-followup")
        d = mod._parse_date("2026-01-15")
        assert d == date(2026, 1, 15)

    def test_yyyy_mm(self):
        mod = _load("smart-followup")
        d = mod._parse_date("2026-01")
        assert d == date(2026, 1, 1)

    def test_none_returns_none(self):
        mod = _load("smart-followup")
        assert mod._parse_date(None) is None

    def test_invalid_returns_none(self):
        mod = _load("smart-followup")
        assert mod._parse_date("not-a-date") is None


class TestDaysSince:
    def test_recent(self):
        mod = _load("smart-followup")
        d = date.today() - timedelta(days=5)
        assert mod._days_since(d) == 5

    def test_zero(self):
        mod = _load("smart-followup")
        assert mod._days_since(date.today()) == 0


class TestLoadFollowupApplications:
    def _make_app(self, apps_dir: Path, name: str, days_ago: int,
                  outcome: str = "applied") -> None:
        d = apps_dir / name
        d.mkdir()
        applied = (date.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        meta = {
            "company": "Test Co",
            "position": "Engineer",
            "outcome": outcome,
            "applied": applied,
        }
        (d / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")

    def test_returns_stale_apps(self, tmp_path):
        mod = _load("smart-followup")
        apps = tmp_path / "applications"
        apps.mkdir()
        self._make_app(apps, "2026-01-old", days_ago=20)
        with patch.object(mod, "REPO_ROOT", tmp_path):
            records = mod.load_applications(apps)
        assert len(records) == 1
        assert records[0]["days"] == 20

    def test_skips_closed_outcomes(self, tmp_path):
        mod = _load("smart-followup")
        apps = tmp_path / "applications"
        apps.mkdir()
        self._make_app(apps, "2026-01-rejected", days_ago=20, outcome="rejected")
        self._make_app(apps, "2026-01-ghosted", days_ago=20, outcome="ghosted")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            records = mod.load_applications(apps)
        assert records == []

    def test_skips_fresh_apps(self, tmp_path):
        mod = _load("smart-followup")
        apps = tmp_path / "applications"
        apps.mkdir()
        self._make_app(apps, "2026-01-new", days_ago=3)
        with patch.object(mod, "REPO_ROOT", tmp_path):
            records = mod.load_applications(apps)
        # days=3 < lowest threshold (7) → skipped entirely
        assert records == []

    def test_tier_assigned_correctly(self, tmp_path):
        mod = _load("smart-followup")
        apps = tmp_path / "applications"
        apps.mkdir()
        self._make_app(apps, "2026-01-d14", days_ago=14)
        with patch.object(mod, "REPO_ROOT", tmp_path):
            records = mod.load_applications(apps)
        non_none = [r for r in records if r["tier"] is not None]
        assert len(non_none) == 1
        assert non_none[0]["tier"] == 14  # Highest triggered threshold


class TestIssueContent:
    def _sample_rec(self) -> dict:
        return {
            "name": "2026-02-acme",
            "company": "Acme",
            "position": "SRE",
            "outcome": "applied",
            "provider": "gemini",
            "app_date": "2026-02-01",
            "days": 14,
            "tier": 14,
            "tier_label": "D+14",
            "tier_desc": "stale",
            "tier_emoji": "🟠",
            "has_issue": False,
            "followup_issue": None,
        }

    def test_issue_title_contains_company(self):
        mod = _load("smart-followup")
        title = mod._issue_title(self._sample_rec())
        assert "Acme" in title
        assert "D+14" in title

    def test_issue_body_contains_app_info(self):
        mod = _load("smart-followup")
        body = mod._issue_body(self._sample_rec())
        assert "Acme" in body
        assert "SRE" in body
        assert "2026-02-01" in body
        assert "2026-02-acme" in body


class TestSmartFollowupMain:
    def test_main_no_apps_dir(self, tmp_path):
        mod = _load("smart-followup")
        with patch.object(mod, "REPO_ROOT", tmp_path / "nonexistent"):
            with patch("sys.argv", ["smart-followup.py"]):
                rc = mod.main()
        assert rc == 1

    def test_main_no_stale_apps(self, tmp_path, capsys):
        mod = _load("smart-followup")
        apps = tmp_path / "applications"
        apps.mkdir()
        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch("sys.argv", ["smart-followup.py"]):
                rc = mod.main()
        out = capsys.readouterr().out
        assert rc == 0
        assert "No applications" in out

    def test_main_json_output(self, tmp_path, capsys):
        mod = _load("smart-followup")
        apps = tmp_path / "applications"
        apps.mkdir()
        # Add one stale app
        d = apps / "2026-01-acme"
        d.mkdir()
        applied = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        meta = {"company": "Acme", "position": "SRE", "outcome": "applied", "applied": applied}
        (d / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch("sys.argv", ["smart-followup.py", "--json"]):
                rc = mod.main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert rc == 0

    def test_dry_run_does_not_call_gh(self, tmp_path, capsys):
        mod = _load("smart-followup")
        rec = {
            "name": "app", "company": "X", "position": "Y",
            "outcome": "applied", "provider": "gemini",
            "app_date": "2026-01-01", "days": 14,
            "tier": 14, "tier_label": "D+14", "tier_desc": "stale",
            "tier_emoji": "🟠", "has_issue": False, "followup_issue": None,
        }
        with patch("subprocess.run") as mock_run:
            issue_num = mod.create_github_issue(rec, tmp_path, dry_run=True)
        assert issue_num is None
        mock_run.assert_not_called()
