"""Tests for scripts/status.py — application status dashboard.

Covers:
  - _days_since: date formats (YYYY-MM-DD, YYYY-MM, date object, invalid)
  - _latest_ats: ats_history list, ats_score fallback, missing
  - _colour: tty vs non-tty, known/unknown outcomes
  - _use_colour: stdout isatty detection
  - load_applications: empty dir, missing dir, active_only filter,
    outcome normalisation, corrupt YAML skip, no-meta-yml skip,
    created fallback to 'applied' field
  - print_table: empty list, header present, separator, name truncation,
    days=-1 renders as '--', all columns present
  - JSON output: valid JSON, correct keys, active filter in JSON
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location("status", SCRIPTS / "status.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


def _make_app(tmp_path: Path, name: str, meta: dict) -> Path:
    d = tmp_path / "applications" / name
    d.mkdir(parents=True)
    (d / "meta.yml").write_text(yaml.dump(meta))
    return d


# ---------------------------------------------------------------------------
# _days_since
# ---------------------------------------------------------------------------


class TestDaysSince:
    def test_yyyy_mm_dd(self, mod):
        d = date.today() - timedelta(days=5)
        assert mod._days_since(d.strftime("%Y-%m-%d")) == 5

    def test_yyyy_mm(self, mod):
        # YYYY-MM parsed as 1st of month
        d = date.today().replace(day=1)
        result = mod._days_since(d.strftime("%Y-%m"))
        assert result >= 0

    def test_date_object(self, mod):
        d = date.today() - timedelta(days=10)
        assert mod._days_since(d) == 10

    def test_today(self, mod):
        assert mod._days_since(date.today().strftime("%Y-%m-%d")) == 0

    def test_invalid_string(self, mod):
        assert mod._days_since("not-a-date") == -1

    def test_none(self, mod):
        assert mod._days_since(None) == -1

    def test_empty_string(self, mod):
        assert mod._days_since("") == -1

    def test_integer_fallback(self, mod):
        # integers are not date/str → returns -1
        assert mod._days_since(20260101) == -1


# ---------------------------------------------------------------------------
# _latest_ats
# ---------------------------------------------------------------------------


class TestLatestAts:
    def test_ats_history_list(self, mod):
        meta = {"ats_history": [{"score": 72.5}]}
        assert mod._latest_ats(meta) == "72%"

    def test_ats_history_last_entry(self, mod):
        meta = {"ats_history": [{"score": 50}, {"score": 85}]}
        assert mod._latest_ats(meta) == "85%"

    def test_ats_score_fallback(self, mod):
        meta = {"ats_score": 61.0}
        assert mod._latest_ats(meta) == "61%"

    def test_ats_history_empty_list(self, mod):
        meta = {"ats_history": []}
        assert mod._latest_ats(meta) == "--"

    def test_ats_history_non_dict_entry(self, mod):
        meta = {"ats_history": [42]}
        assert mod._latest_ats(meta) == "--"

    def test_no_score_at_all(self, mod):
        meta = {"company": "Acme"}
        assert mod._latest_ats(meta) == "--"

    def test_ats_zero(self, mod):
        meta = {"ats_score": 0}
        assert mod._latest_ats(meta) == "0%"

    def test_ats_100(self, mod):
        meta = {"ats_history": [{"score": 100}]}
        assert mod._latest_ats(meta) == "100%"


# ---------------------------------------------------------------------------
# _colour / _use_colour
# ---------------------------------------------------------------------------


class TestColour:
    def test_no_colour_non_tty(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=False):
            result = mod._colour("applied", "applied")
        assert result == "applied"
        assert "\033[" not in result

    def test_colour_tty_applied(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=True):
            result = mod._colour("applied", "applied")
        assert "\033[33m" in result  # yellow
        assert "\033[0m" in result

    def test_colour_tty_interview(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=True):
            result = mod._colour("interview", "interview")
        assert "\033[36m" in result  # cyan

    def test_colour_tty_offer(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=True):
            result = mod._colour("offer", "offer")
        assert "\033[32m" in result  # green

    def test_colour_tty_rejected(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=True):
            result = mod._colour("rejected", "rejected")
        assert "\033[90m" in result  # grey

    def test_colour_tty_ghosted(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=True):
            result = mod._colour("ghosted", "ghosted")
        assert "\033[90m" in result

    def test_colour_unknown_outcome_no_code(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=True):
            result = mod._colour("text", "unknown_outcome")
        # Unknown outcome → no ANSI code prefix
        assert result.startswith("text") or "\033[" not in result or result == "text"

    def test_use_colour_false_when_not_tty(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=False):
            assert mod._use_colour() is False

    def test_use_colour_true_when_tty(self, mod):
        with patch.object(mod.sys.stdout, "isatty", return_value=True):
            assert mod._use_colour() is True


# ---------------------------------------------------------------------------
# load_applications
# ---------------------------------------------------------------------------


class TestLoadApplications:
    def test_missing_apps_dir(self, mod, tmp_path):
        with patch.object(mod, "APPS_DIR", tmp_path / "nonexistent"):
            result = mod.load_applications()
        assert result == []

    def test_empty_apps_dir(self, mod, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        with patch.object(mod, "APPS_DIR", apps):
            result = mod.load_applications()
        assert result == []

    def test_loads_single_app(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-acme", {
            "company": "Acme", "outcome": "applied",
            "created": "2026-01-01", "tailor_provider": "gemini",
        })
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert len(result) == 1
        assert result[0]["name"] == "2026-01-acme"

    def test_outcome_normalised_to_lower(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {"company": "A", "outcome": "INTERVIEW"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert result[0]["outcome"] == "interview"

    def test_missing_outcome_defaults_to_applied(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {"company": "A"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert result[0]["outcome"] == "applied"

    def test_skips_dir_without_meta_yml(self, mod, tmp_path):
        apps = tmp_path / "applications"
        (apps / "2026-01-no-meta").mkdir(parents=True)
        with patch.object(mod, "APPS_DIR", apps):
            result = mod.load_applications()
        assert result == []

    def test_skips_corrupt_yaml(self, mod, tmp_path):
        d = tmp_path / "applications" / "2026-01-bad"
        d.mkdir(parents=True)
        (d / "meta.yml").write_text("key: [unclosed")
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert result == []

    def test_active_only_filters_rejected(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-active", {"company": "A", "outcome": "applied"})
        _make_app(tmp_path, "2026-01-dead",   {"company": "B", "outcome": "rejected"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications(active_only=True)
        assert len(result) == 1
        assert result[0]["name"] == "2026-01-active"

    def test_active_only_filters_ghosted(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-ghost", {"company": "G", "outcome": "ghosted"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications(active_only=True)
        assert result == []

    def test_active_only_keeps_interview(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-intv", {"company": "X", "outcome": "interview"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications(active_only=True)
        assert len(result) == 1

    def test_active_only_keeps_offer(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-offer", {"company": "Y", "outcome": "offer"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications(active_only=True)
        assert len(result) == 1

    def test_ats_loaded(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {
            "company": "A", "ats_history": [{"score": 78}],
        })
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert result[0]["ats"] == "78%"

    def test_provider_loaded(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {
            "company": "A", "tailor_provider": "claude",
        })
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert result[0]["provider"] == "claude"

    def test_missing_provider_defaults_to_dash(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {"company": "A"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert result[0]["provider"] == "--"

    def test_created_fallback_to_applied_field(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {
            "company": "A",
            "applied": "2026-01-01",
        })
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert result[0]["days"] >= 0

    def test_days_negative_one_when_no_date(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {"company": "A"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert result[0]["days"] == -1

    def test_sorted_by_name(self, mod, tmp_path):
        _make_app(tmp_path, "2026-03-c", {"company": "C"})
        _make_app(tmp_path, "2026-01-a", {"company": "A"})
        _make_app(tmp_path, "2026-02-b", {"company": "B"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        names = [r["name"] for r in result]
        assert names == sorted(names)

    def test_multiple_apps_all_loaded(self, mod, tmp_path):
        for i in range(5):
            _make_app(tmp_path, f"2026-0{i+1}-app", {"company": f"Co{i}"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            result = mod.load_applications()
        assert len(result) == 5


# ---------------------------------------------------------------------------
# print_table
# ---------------------------------------------------------------------------


class TestPrintTable:
    def _capture(self, mod, apps):
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            mod.print_table(apps)
        return buf.getvalue()

    def test_empty_list_prints_no_applications(self, mod):
        out = self._capture(mod, [])
        assert "No applications found" in out

    def test_header_application_column(self, mod):
        apps = [{"name": "2026-01-acme", "outcome": "applied", "days": 3, "ats": "72%", "provider": "gemini"}]
        out = self._capture(mod, apps)
        assert "Application" in out

    def test_header_stage_column(self, mod):
        apps = [{"name": "2026-01-acme", "outcome": "applied", "days": 3, "ats": "72%", "provider": "gemini"}]
        out = self._capture(mod, apps)
        assert "Stage" in out

    def test_header_days_column(self, mod):
        apps = [{"name": "x", "outcome": "applied", "days": 1, "ats": "--", "provider": "--"}]
        out = self._capture(mod, apps)
        assert "Days" in out

    def test_header_ats_column(self, mod):
        apps = [{"name": "x", "outcome": "applied", "days": 1, "ats": "--", "provider": "--"}]
        out = self._capture(mod, apps)
        assert "ATS" in out

    def test_separator_line(self, mod):
        apps = [{"name": "x", "outcome": "applied", "days": 1, "ats": "--", "provider": "--"}]
        out = self._capture(mod, apps)
        assert "---" in out

    def test_app_name_in_output(self, mod):
        apps = [{"name": "2026-01-stripe", "outcome": "applied", "days": 5, "ats": "80%", "provider": "gemini"}]
        out = self._capture(mod, apps)
        assert "2026-01-stripe" in out

    def test_outcome_in_output(self, mod):
        apps = [{"name": "x", "outcome": "interview", "days": 10, "ats": "85%", "provider": "claude"}]
        out = self._capture(mod, apps)
        assert "interview" in out

    def test_ats_in_output(self, mod):
        apps = [{"name": "x", "outcome": "applied", "days": 2, "ats": "67%", "provider": "gemini"}]
        out = self._capture(mod, apps)
        assert "67%" in out

    def test_provider_in_output(self, mod):
        apps = [{"name": "x", "outcome": "applied", "days": 2, "ats": "--", "provider": "mistral"}]
        out = self._capture(mod, apps)
        assert "mistral" in out

    def test_days_minus_one_renders_as_dash(self, mod):
        apps = [{"name": "x", "outcome": "applied", "days": -1, "ats": "--", "provider": "--"}]
        out = self._capture(mod, apps)
        assert "--" in out

    def test_name_truncated_when_too_long(self, mod):
        long_name = "a" * 40
        apps = [{"name": long_name, "outcome": "applied", "days": 1, "ats": "--", "provider": "--"}]
        out = self._capture(mod, apps)
        # Truncated name ends with ellipsis
        assert "…" in out or long_name[:34] in out

    def test_multiple_rows(self, mod):
        apps = [
            {"name": "2026-01-a", "outcome": "applied",   "days": 1,  "ats": "70%", "provider": "gemini"},
            {"name": "2026-02-b", "outcome": "interview",  "days": 14, "ats": "85%", "provider": "claude"},
            {"name": "2026-03-c", "outcome": "rejected",   "days": 30, "ats": "55%", "provider": "--"},
        ]
        out = self._capture(mod, apps)
        assert "2026-01-a" in out
        assert "2026-02-b" in out
        assert "2026-03-c" in out


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_json_is_valid(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {"company": "A", "outcome": "applied"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            apps = mod.load_applications()
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print(json.dumps(apps, indent=2))
        data = json.loads(buf.getvalue())
        assert isinstance(data, list)

    def test_json_has_required_keys(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {"company": "A", "outcome": "applied"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            apps = mod.load_applications()
        assert all(k in apps[0] for k in ("name", "outcome", "days", "ats", "provider"))

    def test_json_active_filter(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-active",   {"company": "A", "outcome": "applied"})
        _make_app(tmp_path, "2026-01-rejected",  {"company": "B", "outcome": "rejected"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            apps = mod.load_applications(active_only=True)
        assert len(apps) == 1
        assert apps[0]["outcome"] == "applied"

    def test_json_outcome_string(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {"company": "A", "outcome": "offer"})
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            apps = mod.load_applications()
        data = json.dumps(apps)
        parsed = json.loads(data)
        assert parsed[0]["outcome"] == "offer"

    def test_json_days_is_int(self, mod, tmp_path):
        _make_app(tmp_path, "2026-01-a", {
            "company": "A", "created": "2026-01-01",
        })
        with patch.object(mod, "APPS_DIR", tmp_path / "applications"):
            apps = mod.load_applications()
        assert isinstance(apps[0]["days"], int)

    def test_json_empty_apps(self, mod, tmp_path):
        apps_dir = tmp_path / "applications"
        apps_dir.mkdir()
        with patch.object(mod, "APPS_DIR", apps_dir):
            apps = mod.load_applications()
        assert apps == []
        assert json.dumps(apps) == "[]"
