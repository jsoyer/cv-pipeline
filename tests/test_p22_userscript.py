"""
Phase 22 — Userscript and cv-api integration tests.

Covers:
  - cv-pipeline.user.js metadata and structure (parsed in Python)
  - Platform URL regex patterns (PLATFORMS dict)
  - cv-api.py _handle_pipeline with description field
  - cv-api.py _handle_pipeline description-skips-fetch path
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

SCRIPTS = Path(__file__).parent.parent / "scripts"
USERSCRIPT = SCRIPTS / "cv-pipeline.user.js"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    module_name = name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Userscript metadata parser
# ---------------------------------------------------------------------------


def _parse_userscript_header(path: Path) -> dict:
    """Extract ==UserScript== header fields into a dict (list for multi-value keys)."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"// ==UserScript==(.*?)// ==/UserScript==", text, re.DOTALL)
    assert m, "UserScript header not found"
    meta: dict[str, list[str]] = {}
    for line in m.group(1).splitlines():
        line = line.strip().lstrip("//").strip()
        if not line:
            continue
        match = re.match(r"@(\S+)\s+(.*)", line)
        if match:
            key, val = match.group(1), match.group(2).strip()
            meta.setdefault(key, []).append(val)
    return meta


class TestUserscriptMetadata:
    def test_header_present(self):
        text = USERSCRIPT.read_text(encoding="utf-8")
        assert "==UserScript==" in text
        assert "==/UserScript==" in text

    def test_name_set(self):
        meta = _parse_userscript_header(USERSCRIPT)
        assert meta["name"] == ["CV Pipeline"]

    def test_version_semver(self):
        meta = _parse_userscript_header(USERSCRIPT)
        assert re.match(r"\d+\.\d+\.\d+", meta["version"][0])

    def test_match_linkedin_view(self):
        meta = _parse_userscript_header(USERSCRIPT)
        matches = meta.get("match", [])
        assert any("linkedin.com/jobs/view/" in m for m in matches)

    def test_match_linkedin_collections(self):
        meta = _parse_userscript_header(USERSCRIPT)
        matches = meta.get("match", [])
        assert any("linkedin.com/jobs/collections/" in m for m in matches)

    def test_match_indeed(self):
        meta = _parse_userscript_header(USERSCRIPT)
        matches = meta.get("match", [])
        assert any("indeed.com/viewjob" in m for m in matches)

    def test_match_wttj(self):
        meta = _parse_userscript_header(USERSCRIPT)
        matches = meta.get("match", [])
        assert any("welcometothejungle.com" in m for m in matches)

    def test_grants_gm_value(self):
        meta = _parse_userscript_header(USERSCRIPT)
        grants = meta.get("grant", [])
        assert "GM_getValue" in grants
        assert "GM_setValue" in grants

    def test_grants_gm_xmlhttp(self):
        meta = _parse_userscript_header(USERSCRIPT)
        grants = meta.get("grant", [])
        assert "GM_xmlhttpRequest" in grants

    def test_grants_gm_menu(self):
        meta = _parse_userscript_header(USERSCRIPT)
        grants = meta.get("grant", [])
        assert "GM_registerMenuCommand" in grants

    def test_connect_localhost(self):
        meta = _parse_userscript_header(USERSCRIPT)
        connects = meta.get("connect", [])
        assert "localhost" in connects or "127.0.0.1" in connects

    def test_run_at_document_idle(self):
        meta = _parse_userscript_header(USERSCRIPT)
        assert meta.get("run-at", []) == ["document-idle"]


# ---------------------------------------------------------------------------
# Platform URL pattern tests (mirrors the PLATFORMS dict in the userscript)
# ---------------------------------------------------------------------------

PLATFORM_PATTERNS = {
    "linkedin": re.compile(r"linkedin\.com/jobs/(view|collections)/"),
    "indeed":   re.compile(r"indeed\.com/viewjob"),
    "wttj":     re.compile(r"welcometothejungle\.com.*/jobs/"),
}


class TestPlatformPatterns:
    def _matches(self, platform: str, url: str) -> bool:
        return bool(PLATFORM_PATTERNS[platform].search(url))

    # LinkedIn
    def test_linkedin_view_matches(self):
        assert self._matches("linkedin", "https://www.linkedin.com/jobs/view/1234567890/")

    def test_linkedin_collections_matches(self):
        assert self._matches("linkedin", "https://www.linkedin.com/jobs/collections/recommended/")

    def test_linkedin_search_no_match(self):
        assert not self._matches("linkedin", "https://www.linkedin.com/jobs/search/?keywords=python")

    def test_linkedin_profile_no_match(self):
        assert not self._matches("linkedin", "https://www.linkedin.com/in/janedoe/")

    # Indeed
    def test_indeed_viewjob_matches(self):
        assert self._matches("indeed", "https://fr.indeed.com/viewjob?jk=abc123")

    def test_indeed_en_matches(self):
        assert self._matches("indeed", "https://www.indeed.com/viewjob?jk=abc123")

    def test_indeed_search_no_match(self):
        assert not self._matches("indeed", "https://fr.indeed.com/emplois?q=python")

    # WTTJ
    def test_wttj_fr_matches(self):
        assert self._matches("wttj", "https://www.welcometothejungle.com/fr/companies/acme/jobs/senior-engineer")

    def test_wttj_en_matches(self):
        assert self._matches("wttj", "https://www.welcometothejungle.com/en/companies/beta/jobs/vp-engineering")

    def test_wttj_top_level_matches(self):
        assert self._matches("wttj", "https://www.welcometothejungle.com/jobs/abc123")

    def test_wttj_home_no_match(self):
        assert not self._matches("wttj", "https://www.welcometothejungle.com/fr/companies/acme")


# ---------------------------------------------------------------------------
# cv-api.py — _handle_pipeline with description field
# ---------------------------------------------------------------------------


class TestPipelineWithDescription:
    def _make_handler(self, tmp_path: Path, body: dict):
        """Create a CVApiHandler instance with mocked rfile for a given body."""
        mod = _load("cv-api")

        handler = object.__new__(mod.CVApiHandler)
        handler.wfile = MagicMock()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        # Capture JSON response
        responses = []

        def fake_json_response(h, status, data):
            responses.append({"status": status, "data": data})

        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch.object(mod, "_json_response", side_effect=fake_json_response):
                with patch.object(mod, "_run_make", return_value=(0, "tailor ok")):
                    handler._handle_pipeline(body)

        return responses

    def test_description_writes_job_txt(self, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        responses = self._make_handler(tmp_path, {
            "company": "Acme",
            "position": "SRE",
            "description": "We need a senior SRE with Kubernetes experience.",
            "url": "https://example.com/job",
        })
        job_txt = list(tmp_path.glob("applications/*/job.txt"))
        assert len(job_txt) == 1
        assert "Kubernetes" in job_txt[0].read_text()

    def test_description_skips_fetch_step(self, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        responses = self._make_handler(tmp_path, {
            "company": "Beta",
            "position": "Engineer",
            "description": "Python API backend engineer.",
            "url": "https://example.com/job",
        })
        assert len(responses) == 1
        steps = responses[0]["data"]["steps"]
        step_names = [s["step"] for s in steps]
        assert "description" in step_names
        assert "fetch" not in step_names
        assert "tailor" in step_names

    def test_description_step_has_rc_zero(self, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        responses = self._make_handler(tmp_path, {
            "company": "Gamma",
            "position": "PM",
            "description": "Product manager role.",
        })
        desc_step = next(s for s in responses[0]["data"]["steps"] if s["step"] == "description")
        assert desc_step["rc"] == 0

    def test_no_url_no_description_returns_400(self, tmp_path):
        mod = _load("cv-api")
        apps = tmp_path / "applications"
        apps.mkdir()

        handler = object.__new__(mod.CVApiHandler)
        responses = []

        def fake_json_response(h, status, data):
            responses.append({"status": status, "data": data})

        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch.object(mod, "_json_response", side_effect=fake_json_response):
                handler._handle_pipeline({})

        assert responses[0]["status"] == 400

    def test_auto_name_from_company(self, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        responses = self._make_handler(tmp_path, {
            "company": "Stripe Inc",
            "position": "SRE",
            "description": "SRE role at Stripe.",
        })
        assert responses[0]["status"] == 200
        name = responses[0]["data"]["name"]
        assert "stripe" in name.lower()

    def test_meta_yml_created(self, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        self._make_handler(tmp_path, {
            "company": "Notion",
            "position": "Backend Engineer",
            "description": "Backend role.",
        })
        meta_files = list(tmp_path.glob("applications/*/meta.yml"))
        assert len(meta_files) == 1
        meta = yaml.safe_load(meta_files[0].read_text())
        assert meta["company"] == "Notion"
        assert meta["position"] == "Backend Engineer"

    def test_url_written_to_job_url_file(self, tmp_path):
        apps = tmp_path / "applications"
        apps.mkdir()
        self._make_handler(tmp_path, {
            "company": "Vercel",
            "position": "Engineer",
            "description": "Vercel job.",
            "url": "https://vercel.com/careers/123",
        })
        url_files = list(tmp_path.glob("applications/*/job.url"))
        assert len(url_files) == 1
        assert "vercel.com" in url_files[0].read_text()

    def test_without_description_falls_back_to_fetch(self, tmp_path):
        mod = _load("cv-api")
        apps = tmp_path / "applications"
        apps.mkdir()

        handler = object.__new__(mod.CVApiHandler)
        responses = []
        fetch_called = []

        def fake_json_response(h, status, data):
            responses.append({"status": status, "data": data})

        def fake_run_make(target, env_extra=None):
            fetch_called.append(target)
            return (0, "ok")

        with patch.object(mod, "REPO_ROOT", tmp_path):
            with patch.object(mod, "_json_response", side_effect=fake_json_response):
                with patch.object(mod, "_run_make", side_effect=fake_run_make):
                    handler._handle_pipeline({
                        "company": "Datadog",
                        "position": "SRE",
                        "url": "https://datadog.com/jobs/123",
                    })

        assert any("fetch" in c for c in fetch_called)


# ---------------------------------------------------------------------------
# Userscript structural checks (JS source analysis)
# ---------------------------------------------------------------------------


class TestUserscriptStructure:
    def _src(self) -> str:
        return USERSCRIPT.read_text(encoding="utf-8")

    def test_iife_wrapper(self):
        src = self._src()
        assert "(function ()" in src or "(function()" in src
        assert "})();" in src

    def test_use_strict(self):
        assert "'use strict';" in self._src()

    def test_settings_object_present(self):
        assert "SETTINGS" in self._src()
        assert "cv_api_url" in self._src()
        assert "cv_provider" in self._src()

    def test_platforms_object_present(self):
        assert "PLATFORMS" in self._src()
        assert "linkedin" in self._src()
        assert "indeed" in self._src()
        assert "wttj" in self._src()

    def test_extractors_per_platform(self):
        src = self._src()
        assert "extractLinkedIn" in src
        assert "extractIndeed" in src
        assert "extractWTTJ" in src

    def test_show_toast_function(self):
        assert "showToast" in self._src()

    def test_trigger_pipeline_function(self):
        assert "triggerPipeline" in self._src()

    def test_inject_button_function(self):
        assert "injectButton" in self._src()

    def test_show_settings_function(self):
        assert "showSettings" in self._src()

    def test_description_sent_in_pipeline_call(self):
        src = self._src()
        assert "description" in src

    def test_health_check_before_pipeline(self):
        src = self._src()
        assert "/health" in src

    def test_spa_observer_for_linkedin(self):
        src = self._src()
        assert "MutationObserver" in src

    def test_menu_command_settings(self):
        src = self._src()
        assert "GM_registerMenuCommand" in src
        assert "Settings" in src

    def test_providers_listed(self):
        src = self._src()
        for p in ("gemini", "claude", "openai", "mistral", "ollama"):
            assert p in src
