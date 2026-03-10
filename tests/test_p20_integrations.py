"""
Phase 20 — Integrations tests.

Covers: notion-twoway.py, job-boards.py, cv-api.py, notify.py Slack Block Kit
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
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
# notify.py — Slack Block Kit
# ---------------------------------------------------------------------------

class TestSlackBlocks:
    def test_returns_dict_with_text(self):
        mod = _load("notify")
        result = mod._slack_blocks("Acme", "SE", "interview", "", "2026-02-acme")
        assert "text" in result
        assert "Acme" in result["text"]

    def test_has_attachments_with_color(self):
        mod = _load("notify")
        result = mod._slack_blocks("Acme", "SE", "offer", "", "2026-02-acme")
        assert "attachments" in result
        assert result["attachments"][0]["color"] == "#22C55E"

    def test_rejected_color(self):
        mod = _load("notify")
        result = mod._slack_blocks("Acme", "SE", "rejected", "", "2026-02-acme")
        assert result["attachments"][0]["color"] == "#EF4444"

    def test_blocks_contain_company(self):
        mod = _load("notify")
        result = mod._slack_blocks("Acme Corp", "SRE", "interview", "great call", "app")
        blocks = result["attachments"][0]["blocks"]
        header_text = blocks[0]["text"]["text"]
        assert "Acme Corp" in header_text

    def test_message_block_added_when_present(self):
        mod = _load("notify")
        result = mod._slack_blocks("X", "Y", "applied", "custom note", "app")
        blocks = result["attachments"][0]["blocks"]
        texts = [b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"]
        assert any("custom note" in t for t in texts)

    def test_no_message_no_extra_section(self):
        mod = _load("notify")
        result = mod._slack_blocks("X", "Y", "applied", "", "app")
        blocks = result["attachments"][0]["blocks"]
        # Should not have an empty message section
        for b in blocks:
            if b.get("type") == "section" and "text" in b:
                assert b["text"].get("text", "") != ""

    def test_dry_run_skips_http(self):
        mod = _load("notify")
        with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            result = mod.notify_slack("Acme", "SRE", "interview", "", "app", dry_run=True)
        assert result is True


# ---------------------------------------------------------------------------
# notion-twoway.py
# ---------------------------------------------------------------------------

class TestNotionGetText:
    def test_title_property(self):
        mod = _load("notion-twoway")
        prop = {"type": "title", "title": [{"plain_text": "Stripe"}]}
        assert mod._get_text(prop) == "Stripe"

    def test_rich_text_property(self):
        mod = _load("notion-twoway")
        prop = {"type": "rich_text", "rich_text": [{"plain_text": "SRE"}]}
        assert mod._get_text(prop) == "SRE"

    def test_select_property(self):
        mod = _load("notion-twoway")
        prop = {"type": "select", "select": {"name": "Interview"}}
        assert mod._get_text(prop) == "Interview"

    def test_select_none(self):
        mod = _load("notion-twoway")
        prop = {"type": "select", "select": None}
        assert mod._get_text(prop) == ""

    def test_url_property(self):
        mod = _load("notion-twoway")
        prop = {"type": "url", "url": "https://example.com"}
        assert mod._get_text(prop) == "https://example.com"

    def test_unknown_type_returns_empty(self):
        mod = _load("notion-twoway")
        prop = {"type": "formula", "formula": {}}
        assert mod._get_text(prop) == ""


class TestNotionStatusMapping:
    def test_notion_to_local(self):
        mod = _load("notion-twoway")
        assert mod.NOTION_TO_LOCAL["Interview"] == "interview"
        assert mod.NOTION_TO_LOCAL["Offer"] == "offer"
        assert mod.NOTION_TO_LOCAL["Rejected"] == "rejected"

    def test_local_to_notion(self):
        mod = _load("notion-twoway")
        assert mod.LOCAL_TO_NOTION["interview"] == "Interview"
        assert mod.LOCAL_TO_NOTION["offer"] == "Offer"
        assert mod.LOCAL_TO_NOTION["rejected"] == "Rejected"


class TestLoadApps:
    def test_empty_dir(self, tmp_path):
        mod = _load("notion-twoway")
        assert mod._load_apps(tmp_path) == {}

    def test_loads_apps_with_meta(self, tmp_path):
        app_dir = tmp_path / "2026-02-acme"
        app_dir.mkdir()
        (app_dir / "meta.yml").write_text(
            yaml.dump({"company": "Acme", "outcome": "interview"}), encoding="utf-8"
        )
        mod = _load("notion-twoway")
        result = mod._load_apps(tmp_path)
        assert "2026-02-acme" in result
        assert result["2026-02-acme"]["meta"]["company"] == "Acme"

    def test_skips_dir_without_meta(self, tmp_path):
        (tmp_path / "no-meta").mkdir()
        mod = _load("notion-twoway")
        assert mod._load_apps(tmp_path) == {}


class TestDoPull:
    def test_pull_updates_meta_when_notion_differs(self, tmp_path, capsys):
        mod = _load("notion-twoway")
        # Setup local app at "applied"
        app_dir = tmp_path / "2026-02-acme"
        app_dir.mkdir()
        meta = {"company": "Acme", "outcome": "applied"}
        (app_dir / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")

        # Mock Notion client returning Interview status
        mock_client = MagicMock()
        mock_client.query_db.return_value = [{
            "id": "page-1",
            "properties": {
                "Company": {"type": "title", "title": [{"plain_text": "Acme"}]},
                "Position": {"type": "rich_text", "rich_text": [{"plain_text": "SRE"}]},
                "Branch": {"type": "rich_text", "rich_text": [{"plain_text": "apply/2026-02-acme"}]},
                "Status": {"type": "select", "select": {"name": "Interview"}},
                "PR": {"type": "url", "url": ""},
            },
        }]

        apps = mod._load_apps(tmp_path)
        mod.do_pull(mock_client, apps, dry_run=False)

        # Check meta.yml was updated
        updated = yaml.safe_load((app_dir / "meta.yml").read_text())
        assert updated["outcome"] == "interview"

    def test_pull_dry_run_does_not_write(self, tmp_path, capsys):
        mod = _load("notion-twoway")
        app_dir = tmp_path / "2026-02-acme"
        app_dir.mkdir()
        meta = {"company": "Acme", "outcome": "applied"}
        (app_dir / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")

        mock_client = MagicMock()
        mock_client.query_db.return_value = [{
            "id": "page-1",
            "properties": {
                "Company": {"type": "title", "title": [{"plain_text": "Acme"}]},
                "Position": {"type": "rich_text", "rich_text": []},
                "Branch": {"type": "rich_text", "rich_text": [{"plain_text": "apply/2026-02-acme"}]},
                "Status": {"type": "select", "select": {"name": "Offer"}},
                "PR": {"type": "url", "url": ""},
            },
        }]

        apps = mod._load_apps(tmp_path)
        mod.do_pull(mock_client, apps, dry_run=True)

        # Should NOT have updated
        unchanged = yaml.safe_load((app_dir / "meta.yml").read_text())
        assert unchanged["outcome"] == "applied"

    def test_pull_skips_when_in_sync(self, tmp_path, capsys):
        mod = _load("notion-twoway")
        app_dir = tmp_path / "2026-02-acme"
        app_dir.mkdir()
        meta = {"company": "Acme", "outcome": "interview"}
        (app_dir / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")

        mock_client = MagicMock()
        mock_client.query_db.return_value = [{
            "id": "page-1",
            "properties": {
                "Company": {"type": "title", "title": [{"plain_text": "Acme"}]},
                "Position": {"type": "rich_text", "rich_text": []},
                "Branch": {"type": "rich_text", "rich_text": [{"plain_text": "apply/2026-02-acme"}]},
                "Status": {"type": "select", "select": {"name": "Interview"}},
                "PR": {"type": "url", "url": ""},
            },
        }]

        apps = mod._load_apps(tmp_path)
        rc = mod.do_pull(mock_client, apps, dry_run=False)
        assert rc == 0


class TestDoPush:
    def test_push_updates_existing_page(self, tmp_path, capsys):
        mod = _load("notion-twoway")
        app_dir = tmp_path / "2026-02-acme"
        app_dir.mkdir()
        meta = {"company": "Acme", "outcome": "offer"}
        (app_dir / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")

        mock_client = MagicMock()
        mock_client.query_db.return_value = [{
            "id": "page-1",
            "properties": {
                "Company": {"type": "title", "title": [{"plain_text": "Acme"}]},
                "Position": {"type": "rich_text", "rich_text": []},
                "Branch": {"type": "rich_text", "rich_text": []},
                "Status": {"type": "select", "select": {"name": "Applied"}},
                "PR": {"type": "url", "url": ""},
            },
        }]

        apps = mod._load_apps(tmp_path)
        rc = mod.do_push(mock_client, apps, dry_run=False)
        assert rc == 0
        mock_client.update_page.assert_called_once()

    def test_push_creates_new_page(self, tmp_path, capsys):
        mod = _load("notion-twoway")
        app_dir = tmp_path / "2026-02-newco"
        app_dir.mkdir()
        meta = {"company": "NewCo", "position": "SRE", "outcome": "applied"}
        (app_dir / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")

        mock_client = MagicMock()
        mock_client.query_db.return_value = []  # No existing pages

        apps = mod._load_apps(tmp_path)
        rc = mod.do_push(mock_client, apps, dry_run=False)
        assert rc == 0
        mock_client.create_page.assert_called_once()

    def test_push_dry_run_skips_api(self, tmp_path, capsys):
        mod = _load("notion-twoway")
        app_dir = tmp_path / "2026-02-acme"
        app_dir.mkdir()
        meta = {"company": "Acme", "outcome": "interview"}
        (app_dir / "meta.yml").write_text(yaml.dump(meta), encoding="utf-8")

        mock_client = MagicMock()
        mock_client.query_db.return_value = []

        apps = mod._load_apps(tmp_path)
        mod.do_push(mock_client, apps, dry_run=True)
        mock_client.create_page.assert_not_called()


# ---------------------------------------------------------------------------
# job-boards.py
# ---------------------------------------------------------------------------

class TestJobBoardsGreenhouse:
    def test_fetch_greenhouse_returns_list(self):
        mod = _load("job-boards")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jobs": [
                {
                    "id": 123,
                    "title": "Solutions Engineer",
                    "location": {"name": "Remote"},
                    "departments": [{"name": "Sales"}],
                    "absolute_url": "https://boards.greenhouse.io/stripe/jobs/123",
                    "content": "<p>Join our team. <strong>Python</strong> required.</p>",
                    "updated_at": "2026-01-01",
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            jobs = mod.fetch_greenhouse("stripe")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Solutions Engineer"
        assert jobs[0]["board"] == "greenhouse"
        assert "<p>" not in jobs[0]["description"]  # HTML stripped

    def test_fetch_greenhouse_404_returns_empty(self):
        mod = _load("job-boards")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        import requests as req_lib
        err = req_lib.HTTPError(response=mock_resp)
        with patch("requests.get", side_effect=err):
            jobs = mod.fetch_greenhouse("nonexistent-company")
        assert jobs == []


class TestJobBoardsLever:
    def test_fetch_lever_returns_list(self):
        mod = _load("job-boards")
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "id": "abc-123",
                "text": "Senior Solutions Engineer",
                "hostedUrl": "https://jobs.lever.co/vercel/abc-123",
                "categories": {"location": "Paris", "department": "Sales"},
                "lists": [{"text": "Requirements", "content": ["Python", "APIs"]}],
                "updatedAt": 1700000000000,
            }
        ]
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            jobs = mod.fetch_lever("vercel")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Senior Solutions Engineer"
        assert jobs[0]["board"] == "lever"
        assert jobs[0]["location"] == "Paris"

    def test_fetch_lever_404_returns_empty(self):
        mod = _load("job-boards")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        import requests as req_lib
        err = req_lib.HTTPError(response=mock_resp)
        with patch("requests.get", side_effect=err):
            jobs = mod.fetch_lever("nonexistent")
        assert jobs == []


class TestKeywordScore:
    def test_all_keywords_found(self):
        mod = _load("job-boards")
        job = {"title": "Solutions Engineer", "description": "python api sales enterprise"}
        score = mod.keyword_score(job, ["python", "api", "sales"])
        assert score == 100.0

    def test_no_keywords_returns_100(self):
        mod = _load("job-boards")
        job = {"title": "X", "description": "Y"}
        assert mod.keyword_score(job, []) == 100.0

    def test_partial_match(self):
        mod = _load("job-boards")
        job = {"title": "Engineer", "description": "python"}
        score = mod.keyword_score(job, ["python", "java", "rust"])
        assert score == pytest.approx(33.3, abs=0.5)

    def test_no_match_returns_zero(self):
        mod = _load("job-boards")
        job = {"title": "Chef", "description": "cooking"}
        score = mod.keyword_score(job, ["python", "api", "cloud"])
        assert score == 0.0


class TestCreateApplication:
    def test_creates_app_dir(self, tmp_path):
        mod = _load("job-boards")
        job = {
            "company_slug": "stripe",
            "title": "Solutions Engineer",
            "board": "greenhouse",
            "id": "123",
            "description": "Join our team with Python skills.",
            "location": "Remote",
            "url": "https://boards.greenhouse.io/stripe/jobs/123",
        }
        result = mod.create_application(job, tmp_path, dry_run=False)
        assert result is not None
        assert result.is_dir()
        assert (result / "meta.yml").exists()
        assert (result / "job.txt").exists()
        assert (result / "job.url").exists()

    def test_dry_run_returns_none(self, tmp_path):
        mod = _load("job-boards")
        job = {
            "company_slug": "stripe",
            "title": "Engineer",
            "board": "greenhouse",
            "id": "1",
            "description": "test",
            "location": "",
            "url": "",
        }
        result = mod.create_application(job, tmp_path, dry_run=True)
        assert result is None
        # No directory created
        assert not any(tmp_path.iterdir())

    def test_existing_dir_skips(self, tmp_path):
        mod = _load("job-boards")
        job = {
            "company_slug": "stripe",
            "title": "Engineer",
            "board": "greenhouse",
            "id": "1",
            "description": "test",
            "location": "",
            "url": "",
        }
        # First create
        mod.create_application(job, tmp_path, dry_run=False)
        dirs_before = list(tmp_path.iterdir())
        # Second create should skip
        mod.create_application(job, tmp_path, dry_run=False)
        assert list(tmp_path.iterdir()) == dirs_before

    def test_meta_yml_content(self, tmp_path):
        mod = _load("job-boards")
        job = {
            "company_slug": "stripe",
            "title": "Platform Engineer",
            "board": "lever",
            "id": "xyz",
            "description": "Build our platform.",
            "location": "Paris",
            "url": "https://jobs.lever.co/stripe/xyz",
        }
        app_dir = mod.create_application(job, tmp_path, dry_run=False)
        meta = yaml.safe_load((app_dir / "meta.yml").read_text())
        assert meta["board"] == "lever"
        assert meta["position"] == "Platform Engineer"
        assert meta["location"] == "Paris"


# ---------------------------------------------------------------------------
# cv-api.py
# ---------------------------------------------------------------------------

class TestCvApiHelpers:
    def test_slugify_basic(self):
        mod = _load("cv-api")
        assert mod._slugify("Acme Corp") == "acme-corp"

    def test_slugify_strips_special_chars(self):
        mod = _load("cv-api")
        result = mod._slugify("Hello, World!")
        assert "," not in result
        assert "!" not in result

    def test_list_applications_empty_dir(self, tmp_path):
        mod = _load("cv-api")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            # Create empty applications/
            (tmp_path / "applications").mkdir()
            result = mod._list_applications()
        assert result == []

    def test_list_applications_with_meta(self, tmp_path):
        mod = _load("cv-api")
        apps_dir = tmp_path / "applications"
        apps_dir.mkdir()
        app_dir = apps_dir / "2026-02-acme"
        app_dir.mkdir()
        (app_dir / "meta.yml").write_text(
            yaml.dump({"company": "Acme", "position": "SRE", "outcome": "interview"}),
            encoding="utf-8",
        )
        with patch.object(mod, "REPO_ROOT", tmp_path):
            result = mod._list_applications()
        assert len(result) == 1
        assert result[0]["company"] == "Acme"

    def test_get_meta_not_found(self, tmp_path):
        mod = _load("cv-api")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            (tmp_path / "applications").mkdir()
            result = mod._get_meta("nonexistent")
        assert result is None

    def test_get_meta_found(self, tmp_path):
        mod = _load("cv-api")
        apps = tmp_path / "applications"
        apps.mkdir()
        app = apps / "2026-02-acme"
        app.mkdir()
        (app / "meta.yml").write_text(yaml.dump({"company": "Acme"}), encoding="utf-8")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            result = mod._get_meta("2026-02-acme")
        assert result["company"] == "Acme"
