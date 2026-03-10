"""
Phase 18 — Application analytics tests.

Covers: ats-score._record_ats_history, ats-history.py, funnel-analytics.py
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(name: str):
    path = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(path))
    module_name = name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, path / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SAMPLE_META = {
    "company": "Acme",
    "position": "Engineer",
    "outcome": "interview",
    "tailor_provider": "gemini",
    "response_days": 7,
    "ats_history": [
        {"date": "2026-01-01T00:00:00Z", "score": 62.0, "found": 20, "total": 32},
        {"date": "2026-01-10T00:00:00Z", "score": 74.0, "found": 24, "total": 32},
    ],
}

SAMPLE_META_APPLIED = {
    "company": "Beta Corp",
    "position": "Manager",
    "outcome": "applied",
    "tailor_provider": "claude",
    "ats_history": [
        {"date": "2026-02-01T00:00:00Z", "score": 55.0, "found": 18, "total": 33},
    ],
}


def _make_app(tmp_path: Path, name: str, meta: dict) -> Path:
    app_dir = tmp_path / name
    app_dir.mkdir()
    (app_dir / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")
    return app_dir


# ---------------------------------------------------------------------------
# _record_ats_history (ats-score.py)
# ---------------------------------------------------------------------------

class TestRecordAtsHistory:
    def _import_record(self):
        path = Path(__file__).parent.parent / "scripts"
        sys.path.insert(0, str(path))
        import importlib.util
        spec = importlib.util.spec_from_file_location("ats_score", path / "ats-score.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod._record_ats_history

    def test_creates_history_entry(self, tmp_path):
        record = self._import_record()
        meta_path = tmp_path / "meta.yml"
        meta_path.write_text(yaml.dump({"company": "Test"}), encoding="utf-8")
        record(str(tmp_path), 72.5, 23, 32)
        result = yaml.safe_load(meta_path.read_text())
        assert "ats_history" in result
        assert len(result["ats_history"]) == 1
        assert result["ats_history"][0]["score"] == 72.5
        assert result["ats_history"][0]["found"] == 23
        assert result["ats_history"][0]["total"] == 32

    def test_appends_to_existing_history(self, tmp_path):
        record = self._import_record()
        meta = {"company": "Test", "ats_history": [
            {"date": "2026-01-01T00:00:00Z", "score": 60.0, "found": 19, "total": 32}
        ]}
        meta_path = tmp_path / "meta.yml"
        meta_path.write_text(yaml.dump(meta), encoding="utf-8")
        record(str(tmp_path), 75.0, 24, 32)
        result = yaml.safe_load(meta_path.read_text())
        assert len(result["ats_history"]) == 2
        assert result["ats_history"][-1]["score"] == 75.0

    def test_no_meta_yml_is_silent(self, tmp_path):
        record = self._import_record()
        # Should not raise, just return silently
        record(str(tmp_path), 70.0, 22, 32)

    def test_date_iso_format(self, tmp_path):
        record = self._import_record()
        meta_path = tmp_path / "meta.yml"
        meta_path.write_text(yaml.dump({"company": "Test"}), encoding="utf-8")
        record(str(tmp_path), 65.0, 21, 32)
        result = yaml.safe_load(meta_path.read_text())
        date_str = result["ats_history"][0]["date"]
        assert "T" in date_str and "Z" in date_str


# ---------------------------------------------------------------------------
# ats-history.py
# ---------------------------------------------------------------------------

class TestLoadHistory:
    def test_empty_dir_returns_empty_list(self, tmp_path):
        mod = _load("ats-history")
        result = mod.load_history(tmp_path)
        assert result == []

    def test_no_meta_yml_skipped(self, tmp_path):
        (tmp_path / "2026-02-company").mkdir()
        mod = _load("ats-history")
        result = mod.load_history(tmp_path)
        assert result == []

    def test_meta_without_history_skipped(self, tmp_path):
        _make_app(tmp_path, "2026-02-company", {"company": "X", "outcome": "applied"})
        mod = _load("ats-history")
        result = mod.load_history(tmp_path)
        assert result == []

    def test_loads_history_correctly(self, tmp_path):
        _make_app(tmp_path, "2026-02-acme", SAMPLE_META)
        mod = _load("ats-history")
        result = mod.load_history(tmp_path)
        assert len(result) == 1
        assert result[0]["company"] == "Acme"
        assert len(result[0]["history"]) == 2
        assert result[0]["provider"] == "gemini"

    def test_multiple_apps(self, tmp_path):
        _make_app(tmp_path, "2026-01-acme", SAMPLE_META)
        _make_app(tmp_path, "2026-02-beta", SAMPLE_META_APPLIED)
        mod = _load("ats-history")
        result = mod.load_history(tmp_path)
        assert len(result) == 2


class TestPrintHistory:
    def test_empty_records_shows_message(self, capsys):
        mod = _load("ats-history")
        mod.print_history([])
        out = capsys.readouterr().out
        assert "No ATS history" in out

    def test_single_run_shows_score(self, capsys, tmp_path):
        mod = _load("ats-history")
        records = [
            {
                "name": "2026-02-acme",
                "company": "Acme",
                "position": "Engineer",
                "outcome": "interview",
                "provider": "gemini",
                "history": [{"date": "2026-01-01T00:00:00Z", "score": 72.0, "found": 23, "total": 32}],
            }
        ]
        mod.print_history(records)
        out = capsys.readouterr().out
        assert "Acme" in out
        assert "72" in out

    def test_trend_up_arrow(self):
        mod = _load("ats-history")
        assert "↑" in mod._trend_arrow([60.0, 65.0, 75.0])

    def test_trend_down_arrow(self):
        mod = _load("ats-history")
        assert "↓" in mod._trend_arrow([75.0, 60.0])

    def test_trend_flat_arrow(self):
        mod = _load("ats-history")
        assert "→" in mod._trend_arrow([70.0, 71.0])

    def test_single_score_no_arrow(self):
        mod = _load("ats-history")
        assert mod._trend_arrow([70.0]) == "  "

    def test_filter_by_app_name(self, capsys, tmp_path):
        mod = _load("ats-history")
        records = [
            {"name": "2026-02-acme", "company": "Acme", "position": "Eng", "outcome": "applied",
             "provider": "gemini", "history": [{"date": "2026-01-01T00:00:00Z", "score": 60.0, "found": 19, "total": 32}]},
            {"name": "2026-03-beta", "company": "Beta", "position": "Eng", "outcome": "applied",
             "provider": "claude", "history": [{"date": "2026-02-01T00:00:00Z", "score": 55.0, "found": 18, "total": 33}]},
        ]
        mod.print_history(records, app_filter="acme")
        out = capsys.readouterr().out
        assert "Acme" in out
        assert "Beta" not in out


class TestAtsHistoryMain:
    def test_main_no_apps_dir(self, tmp_path):
        mod = _load("ats-history")
        with patch.object(mod, "REPO_ROOT", tmp_path / "nonexistent"):
            with patch("sys.argv", ["ats-history.py"]):
                rc = mod.main()
        assert rc == 1

    def test_main_empty_apps(self, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        mod = _load("ats-history")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch("sys.argv", ["ats-history.py"]):
                rc = mod.main()
        assert rc == 0

    def test_main_json_output(self, tmp_path, capsys):
        apps = tmp_path / "applications"
        apps.mkdir()
        _make_app(apps, "2026-02-acme", SAMPLE_META)
        mod = _load("ats-history")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch("sys.argv", ["ats-history.py", "--json"]):
                rc = mod.main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert rc == 0


# ---------------------------------------------------------------------------
# funnel-analytics.py
# ---------------------------------------------------------------------------

class TestStageLevel:
    def test_applied_is_zero(self):
        mod = _load("funnel-analytics")
        assert mod._stage_level("applied") == 0

    def test_interview_is_positive(self):
        mod = _load("funnel-analytics")
        assert mod._stage_level("interview") > 0

    def test_rejected_is_negative(self):
        mod = _load("funnel-analytics")
        assert mod._stage_level("rejected") < 0

    def test_offer_higher_than_interview(self):
        mod = _load("funnel-analytics")
        assert mod._stage_level("offer") > mod._stage_level("interview")

    def test_unknown_defaults_to_zero(self):
        mod = _load("funnel-analytics")
        assert mod._stage_level("pending") == 0


class TestPearsonCorrelation:
    def test_perfect_positive(self):
        mod = _load("funnel-analytics")
        r = mod._pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        assert abs(r - 1.0) < 1e-9

    def test_perfect_negative(self):
        mod = _load("funnel-analytics")
        r = mod._pearson([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
        assert abs(r + 1.0) < 1e-9

    def test_uncorrelated(self):
        mod = _load("funnel-analytics")
        r = mod._pearson([1, 2, 3, 4, 5], [3, 3, 3, 3, 3])
        assert r is None  # zero std dev

    def test_too_few_points_returns_none(self):
        mod = _load("funnel-analytics")
        assert mod._pearson([1.0, 2.0], [1.0, 2.0]) is None


class TestLoadApplications:
    def test_empty_dir_returns_empty(self, tmp_path):
        mod = _load("funnel-analytics")
        assert mod.load_applications(tmp_path) == []

    def test_no_meta_skipped(self, tmp_path):
        (tmp_path / "app").mkdir()
        mod = _load("funnel-analytics")
        assert mod.load_applications(tmp_path) == []

    def test_loads_basic_fields(self, tmp_path):
        _make_app(tmp_path, "2026-02-acme", SAMPLE_META)
        mod = _load("funnel-analytics")
        recs = mod.load_applications(tmp_path)
        assert len(recs) == 1
        r = recs[0]
        assert r["company"] == "Acme"
        assert r["outcome"] == "interview"
        assert r["provider"] == "gemini"
        assert r["stage_level"] > 0

    def test_ats_score_from_history(self, tmp_path):
        _make_app(tmp_path, "2026-02-acme", SAMPLE_META)
        mod = _load("funnel-analytics")
        recs = mod.load_applications(tmp_path)
        assert recs[0]["ats_score"] == 74.0  # last history entry

    def test_ats_score_from_legacy_field(self, tmp_path):
        meta = {"company": "X", "outcome": "applied", "ats_score": 65.0}
        _make_app(tmp_path, "2026-02-x", meta)
        mod = _load("funnel-analytics")
        recs = mod.load_applications(tmp_path)
        assert recs[0]["ats_score"] == 65.0

    def test_response_days_loaded(self, tmp_path):
        _make_app(tmp_path, "2026-02-acme", SAMPLE_META)
        mod = _load("funnel-analytics")
        recs = mod.load_applications(tmp_path)
        assert recs[0]["response_days"] == 7

    def test_multiple_apps(self, tmp_path):
        _make_app(tmp_path, "2026-01-acme", SAMPLE_META)
        _make_app(tmp_path, "2026-02-beta", SAMPLE_META_APPLIED)
        mod = _load("funnel-analytics")
        recs = mod.load_applications(tmp_path)
        assert len(recs) == 2


class TestPrintReport:
    def test_no_records(self, capsys):
        mod = _load("funnel-analytics")
        mod.print_report([])
        assert "No applications" in capsys.readouterr().out

    def test_shows_funnel_stages(self, capsys, tmp_path):
        mod = _load("funnel-analytics")
        records = [
            {"name": "app1", "company": "A", "position": "Eng", "outcome": "interview",
             "stage_level": 2, "provider": "gemini", "theme": "", "ats_score": 72.0,
             "response_days": 5, "ats_history_count": 2},
            {"name": "app2", "company": "B", "position": "Eng", "outcome": "rejected",
             "stage_level": -1, "provider": "claude", "theme": "", "ats_score": 55.0,
             "response_days": None, "ats_history_count": 1},
        ]
        mod.print_report(records)
        out = capsys.readouterr().out
        assert "FUNNEL" in out
        assert "interview" in out or "applied" in out

    def test_shows_ats_correlation(self, capsys):
        mod = _load("funnel-analytics")
        # Need >=3 scored records for Pearson
        records = [
            {"name": f"app{i}", "company": "X", "position": "E", "outcome": o,
             "stage_level": s, "provider": "gemini", "theme": "", "ats_score": a,
             "response_days": None, "ats_history_count": 1}
            for i, (o, s, a) in enumerate([
                ("interview", 2, 75.0), ("rejected", -1, 50.0), ("offer", 4, 88.0)
            ])
        ]
        mod.print_report(records)
        out = capsys.readouterr().out
        assert "Pearson" in out or "ATS" in out


class TestFunnelMain:
    def test_main_no_apps_dir(self, tmp_path):
        mod = _load("funnel-analytics")
        with patch.object(mod, "REPO_ROOT", tmp_path / "nonexistent"):
            with patch("sys.argv", ["funnel-analytics.py"]):
                rc = mod.main()
        assert rc == 1

    def test_main_empty(self, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        mod = _load("funnel-analytics")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch("sys.argv", ["funnel-analytics.py"]):
                rc = mod.main()
        assert rc == 0

    def test_main_json_output(self, tmp_path, capsys):
        apps = tmp_path / "applications"
        apps.mkdir()
        _make_app(apps, "2026-02-acme", SAMPLE_META)
        mod = _load("funnel-analytics")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch("sys.argv", ["funnel-analytics.py", "--json"]):
                rc = mod.main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "total" in data
        assert data["total"] == 1
        assert rc == 0
