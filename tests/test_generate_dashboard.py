"""Tests for generate-dashboard.py — data collection, stage derivation, HTML output."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
dashboard = importlib.import_module("generate-dashboard")


# ── get_stage ─────────────────────────────────────────────────────────────────

class TestGetStage:
    def test_outcome_interview(self):
        assert dashboard.get_stage({}, {"outcome": "interview"}) == "Interview"

    def test_outcome_offer(self):
        assert dashboard.get_stage({}, {"outcome": "offer"}) == "Offer"

    def test_outcome_rejected(self):
        assert dashboard.get_stage({}, {"outcome": "rejected"}) == "Rejected"

    def test_outcome_ghosted(self):
        assert dashboard.get_stage({}, {"outcome": "ghosted"}) == "Rejected"

    def test_no_pr_draft(self):
        assert dashboard.get_stage({}, {}) == "Draft"

    def test_pr_label_offer(self):
        pr = {"state": "MERGED", "labels": [{"name": "status:offer"}]}
        assert dashboard.get_stage(pr, {}) == "Offer"

    def test_pr_label_interview(self):
        pr = {"state": "OPEN", "labels": [{"name": "status:interview"}]}
        assert dashboard.get_stage(pr, {}) == "Interview"

    def test_pr_label_rejected(self):
        pr = {"state": "MERGED", "labels": [{"name": "status:rejected"}]}
        assert dashboard.get_stage(pr, {}) == "Rejected"

    def test_pr_merged_applied(self):
        pr = {"state": "MERGED", "labels": []}
        assert dashboard.get_stage(pr, {}) == "Applied"

    def test_pr_open_applied(self):
        pr = {"state": "OPEN", "labels": []}
        assert dashboard.get_stage(pr, {}) == "Applied"

    def test_pr_closed_draft(self):
        pr = {"state": "CLOSED", "labels": []}
        assert dashboard.get_stage(pr, {}) == "Draft"

    def test_outcome_takes_precedence_over_label(self):
        pr = {"state": "OPEN", "labels": [{"name": "status:interview"}]}
        assert dashboard.get_stage(pr, {"outcome": "offer"}) == "Offer"


# ── collect_data ──────────────────────────────────────────────────────────────

class TestCollectData:
    def test_no_applications_dir(self, tmp_path):
        with patch.object(dashboard, "REPO_ROOT", tmp_path):
            data = dashboard.collect_data(no_gh=True)
        assert data["applications"] == []
        assert "generated" in data

    def test_empty_applications_dir(self, tmp_path):
        (tmp_path / "applications").mkdir()
        with patch.object(dashboard, "REPO_ROOT", tmp_path):
            data = dashboard.collect_data(no_gh=True)
        assert data["applications"] == []

    def test_app_without_meta_skipped(self, tmp_path):
        app_dir = tmp_path / "applications" / "2026-01-acme"
        app_dir.mkdir(parents=True)
        with patch.object(dashboard, "REPO_ROOT", tmp_path):
            data = dashboard.collect_data(no_gh=True)
        assert data["applications"] == []

    def test_app_with_meta_collected(self, tmp_path):
        app_dir = tmp_path / "applications" / "2026-01-acme"
        app_dir.mkdir(parents=True)
        (app_dir / "meta.yml").write_text(
            "company: Acme\nposition: Engineer\ncreated: 2026-01-15\n"
        )
        with patch.object(dashboard, "REPO_ROOT", tmp_path), \
             patch.object(dashboard, "get_ats_score", return_value=75.0):
            data = dashboard.collect_data(no_gh=True)
        assert len(data["applications"]) == 1
        app = data["applications"][0]
        assert app["company"] == "Acme"
        assert app["position"] == "Engineer"
        assert app["ats_score"] == 75.0
        assert app["stage"] == "Draft"

    def test_stats_computed(self, tmp_path):
        apps_dir = tmp_path / "applications"
        for name, outcome in [("2026-01-a", ""), ("2026-01-b", "interview"), ("2026-02-c", "rejected")]:
            d = apps_dir / name
            d.mkdir(parents=True)
            (d / "meta.yml").write_text(f"company: {name}\ncreated: {name[:7]}-01\noutcome: {outcome}\n")
        with patch.object(dashboard, "REPO_ROOT", tmp_path), \
             patch.object(dashboard, "get_ats_score", return_value=None):
            data = dashboard.collect_data(no_gh=True)
        assert data["stats"]["total"] == 3
        assert "by_stage" in data["stats"]
        assert "monthly" in data

    def test_monthly_breakdown(self, tmp_path):
        apps_dir = tmp_path / "applications"
        for i, month in enumerate(["2026-01", "2026-01", "2026-02"]):
            d = apps_dir / f"{month}-app{i}"
            d.mkdir(parents=True)
            (d / "meta.yml").write_text(f"company: app{i}\ncreated: {month}-01\n")
        with patch.object(dashboard, "REPO_ROOT", tmp_path), \
             patch.object(dashboard, "get_ats_score", return_value=None):
            data = dashboard.collect_data(no_gh=True)
        assert data["monthly"]["2026-01"] == 2
        assert data["monthly"]["2026-02"] == 1


# ── HTML generation ───────────────────────────────────────────────────────────

class TestHTMLGeneration:
    def test_html_template_has_placeholder(self):
        assert "__DATA__" in dashboard.HTML_TEMPLATE

    def test_html_contains_chart_elements(self):
        assert "funnelChart" in dashboard.HTML_TEMPLATE
        assert "monthlyChart" in dashboard.HTML_TEMPLATE
        assert "atsChart" in dashboard.HTML_TEMPLATE
        assert "appsTable" in dashboard.HTML_TEMPLATE

    def test_data_injection(self):
        data = {"applications": [], "stats": {"total": 0}, "generated": "2026-01-01"}
        html = dashboard.HTML_TEMPLATE.replace("__DATA__", json.dumps(data))
        assert '"total": 0' in html
        assert "__DATA__" not in html

    def test_html_is_valid_structure(self):
        assert "<!DOCTYPE html>" in dashboard.HTML_TEMPLATE
        assert "</html>" in dashboard.HTML_TEMPLATE
        assert "<table" in dashboard.HTML_TEMPLATE


# ── main (integration) ────────────────────────────────────────────────────────

class TestMain:
    def test_json_data_mode(self, tmp_path, capsys):
        (tmp_path / "applications").mkdir()
        with patch.object(dashboard, "REPO_ROOT", tmp_path), \
             patch("sys.argv", ["generate-dashboard.py", "--json-data", "--no-gh"]):
            result = dashboard.main()
        assert result == 0
        output = capsys.readouterr().out
        assert '"applications"' in output

    def test_html_output(self, tmp_path):
        (tmp_path / "applications").mkdir()
        out_dir = tmp_path / "out"
        with patch.object(dashboard, "REPO_ROOT", tmp_path), \
             patch("sys.argv", ["generate-dashboard.py", "--output-dir", str(out_dir), "--no-gh"]):
            result = dashboard.main()
        assert result == 0
        html_file = out_dir / "index.html"
        assert html_file.exists()
        content = html_file.read_text()
        assert "<!DOCTYPE html>" in content
        assert "__DATA__" not in content
