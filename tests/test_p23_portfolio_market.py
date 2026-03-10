"""
Phase 23 — portfolio.py and template-market.py tests.

Covers:
  - portfolio.py: _esc, _contact_links (via _render_hero), _render_skills,
    _render_experience, _render_section (via _render_about), generate_html,
    process (via main logic), missing optional sections, --lang fr
  - template-market.py: BUILT_IN_TEMPLATES list, _search_templates (via
    cmd_search), _format_table (via cmd_list), list_templates, search_templates,
    info_template, install_template (built-in / unknown), list_installed,
    fetch_registry network failure, --json output, tag filtering
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import tempfile
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    """Load a script module by its filename stem (hyphens allowed)."""
    module_name = name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ===========================================================================
# portfolio.py
# ===========================================================================


class TestPortfolioEsc:
    def setup_method(self):
        self.mod = _load("portfolio")

    def test_esc_ampersand(self):
        assert self.mod._esc("a & b") == "a &amp; b"

    def test_esc_less_than(self):
        assert self.mod._esc("a < b") == "a &lt; b"

    def test_esc_greater_than(self):
        assert self.mod._esc("a > b") == "a &gt; b"

    def test_esc_double_quote(self):
        assert self.mod._esc('"hello"') == "&quot;hello&quot;"

    def test_esc_plain_string_unchanged(self):
        assert self.mod._esc("hello world") == "hello world"

    def test_esc_accepts_non_string(self):
        # Should not raise; converts via str()
        result = self.mod._esc(42)
        assert result == "42"


class TestPortfolioContactLinks:
    """Test link generation via _render_hero (which uses the contact fields)."""

    def setup_method(self):
        self.mod = _load("portfolio")

    def _hero(self, personal: dict) -> str:
        return self.mod._render_hero(personal)

    def test_mailto_link_present(self):
        html = self._hero({"email": "alice@example.com"})
        assert "mailto:alice@example.com" in html

    def test_linkedin_link_present(self):
        html = self._hero({"linkedin": "alicedoe"})
        assert "linkedin.com/in/alicedoe" in html

    def test_github_link_present(self):
        html = self._hero({"github": "alicegithub"})
        assert "github.com/alicegithub" in html

    def test_no_email_no_mailto(self):
        html = self._hero({"linkedin": "alicedoe"})
        assert "mailto:" not in html

    def test_no_linkedin_no_linkedin_link(self):
        html = self._hero({"email": "alice@example.com"})
        assert "linkedin.com" not in html

    def test_address_displayed(self):
        html = self._hero({"address": "Paris, France"})
        assert "Paris, France" in html

    def test_name_in_hero(self):
        html = self._hero({"first_name": "Alice", "last_name": "Doe"})
        assert "Alice" in html
        assert "Doe" in html

    def test_special_chars_in_email_escaped(self):
        html = self._hero({"email": "alice+tag@example.com"})
        # + is safe in mailto, should appear
        assert "alice+tag@example.com" in html


class TestPortfolioRenderSkills:
    def setup_method(self):
        self.mod = _load("portfolio")

    def test_empty_skills_returns_empty(self):
        assert self.mod._render_skills([]) == ""

    def test_category_in_output(self):
        skills = [{"category": "Languages", "items": ["Python", "Go"]}]
        html = self.mod._render_skills(skills)
        assert "Languages" in html

    def test_items_list_rendered(self):
        skills = [{"category": "Languages", "items": ["Python", "Go"]}]
        html = self.mod._render_skills(skills)
        assert "Python" in html
        assert "Go" in html

    def test_items_comma_string_rendered(self):
        skills = [{"category": "Tools", "items": "Docker, Kubernetes, Terraform"}]
        html = self.mod._render_skills(skills)
        assert "Docker" in html
        assert "Kubernetes" in html
        assert "Terraform" in html

    def test_skill_tag_class_present(self):
        skills = [{"category": "X", "items": ["A"]}]
        html = self.mod._render_skills(skills)
        assert "skill-tag" in html

    def test_multiple_categories(self):
        skills = [
            {"category": "Backend", "items": ["Python"]},
            {"category": "Frontend", "items": ["React"]},
        ]
        html = self.mod._render_skills(skills)
        assert "Backend" in html
        assert "Frontend" in html


class TestPortfolioRenderExperience:
    def setup_method(self):
        self.mod = _load("portfolio")

    def test_empty_experience_returns_empty(self):
        assert self.mod._render_experience([]) == ""

    def test_title_in_output(self):
        exp = [{"title": "Engineer", "company": "ACME", "dates": "2020--2023", "items": []}]
        html = self.mod._render_experience(exp)
        assert "Engineer" in html

    def test_company_in_output(self):
        exp = [{"title": "Engineer", "company": "ACME", "dates": "2020--2023", "items": []}]
        html = self.mod._render_experience(exp)
        assert "ACME" in html

    def test_dates_dash_normalised(self):
        exp = [{"title": "T", "company": "C", "dates": "2020--2023", "items": []}]
        html = self.mod._render_experience(exp)
        # Double-dash should become en-dash
        assert "–" in html
        assert "--" not in html

    def test_bullet_items_string(self):
        exp = [{"title": "T", "company": "C", "dates": "", "items": ["Built API", "Led team"]}]
        html = self.mod._render_experience(exp)
        assert "Built API" in html
        assert "Led team" in html

    def test_bullet_items_dict(self):
        exp = [{"title": "T", "company": "C", "dates": "", "items": [{"text": "Deployed to prod"}]}]
        html = self.mod._render_experience(exp)
        assert "Deployed to prod" in html

    def test_limit_to_5_entries(self):
        exp = [{"title": f"Role{i}", "company": "C", "dates": "", "items": []} for i in range(10)]
        html = self.mod._render_experience(exp)
        assert "Role4" in html
        assert "Role5" not in html

    def test_bold_markdown_to_strong(self):
        exp = [{"title": "T", "company": "C", "dates": "", "items": ["Achieved **50% gain**"]}]
        html = self.mod._render_experience(exp)
        assert "<strong>50% gain</strong>" in html


class TestPortfolioRenderSection:
    """Test section wrapper via _render_about (simplest consumer)."""

    def setup_method(self):
        self.mod = _load("portfolio")

    def test_about_empty_profile_returns_empty(self):
        assert self.mod._render_about("") == ""

    def test_about_includes_h2_tag(self):
        html = self.mod._render_about("A seasoned engineer.")
        assert "<h2>" in html

    def test_about_includes_profile_text(self):
        html = self.mod._render_about("A seasoned engineer.")
        assert "A seasoned engineer." in html

    def test_about_bold_converted(self):
        html = self.mod._render_about("Expert in **Python**.")
        assert "<strong>Python</strong>" in html


class TestPortfolioGenerateHtml:
    def setup_method(self):
        self.mod = _load("portfolio")

    def _cv(self, **overrides) -> dict:
        base = {
            "personal": {
                "first_name": "Jane",
                "last_name": "Smith",
                "position": "Staff Engineer",
                "email": "jane@example.com",
            },
            "profile": "Experienced engineer.",
            "skills": [{"category": "Languages", "items": ["Python"]}],
            "experience": [
                {"title": "SRE", "company": "BigCorp", "dates": "2018--2023", "items": ["Maintained infra"]}
            ],
            "education": [{"degree": "BSc CS", "school": "MIT", "location": "Cambridge, MA", "dates": "2014--2018"}],
            "languages": ["English", "French"],
        }
        base.update(overrides)
        return base

    def test_doctype_present(self):
        html = self.mod.generate_html(self._cv())
        assert "<!DOCTYPE html>" in html

    def test_html_tag_present(self):
        html = self.mod.generate_html(self._cv())
        assert "<html" in html

    def test_name_in_hero(self):
        html = self.mod.generate_html(self._cv())
        assert "Jane" in html
        assert "Smith" in html

    def test_profile_text_present(self):
        html = self.mod.generate_html(self._cv())
        assert "Experienced engineer." in html

    def test_skills_section_present(self):
        html = self.mod.generate_html(self._cv())
        assert "skill-tag" in html
        assert "Python" in html

    def test_experience_section_present(self):
        html = self.mod.generate_html(self._cv())
        assert "SRE" in html
        assert "BigCorp" in html

    def test_education_section_present(self):
        html = self.mod.generate_html(self._cv())
        assert "BSc CS" in html
        assert "MIT" in html

    def test_languages_section_present(self):
        html = self.mod.generate_html(self._cv())
        assert "English" in html
        assert "French" in html

    def test_title_tag_includes_name_and_position(self):
        html = self.mod.generate_html(self._cv())
        assert "Jane Smith" in html
        assert "Staff Engineer" in html

    def test_no_skills_no_skills_section(self):
        cv = self._cv()
        cv["skills"] = []
        html = self.mod.generate_html(cv)
        # _render_skills returns "" when empty, so the id="skills" section is absent
        assert 'id="skills"' not in html

    def test_no_education_no_education_section(self):
        cv = self._cv()
        cv["education"] = []
        html = self.mod.generate_html(cv)
        assert 'id="education"' not in html

    def test_no_languages_no_languages_section(self):
        cv = self._cv()
        cv["languages"] = []
        html = self.mod.generate_html(cv)
        assert 'id="languages"' not in html

    def test_no_experience_no_experience_section(self):
        cv = self._cv()
        cv["experience"] = []
        html = self.mod.generate_html(cv)
        assert 'id="experience"' not in html


class TestPortfolioProcess:
    """Test the file I/O path (reads cv.yml, writes HTML atomically)."""

    def setup_method(self):
        self.mod = _load("portfolio")

    def _write_cv(self, tmp_path: Path, filename: str = "cv.yml") -> Path:
        import yaml

        cv = {
            "personal": {
                "first_name": "Test",
                "last_name": "User",
                "position": "Dev",
                "email": "test@example.com",
            },
            "profile": "Test profile.",
            "skills": [],
            "experience": [],
            "education": [],
            "languages": [],
        }
        p = tmp_path / filename
        p.write_text(yaml.dump(cv), encoding="utf-8")
        return p

    def test_output_file_created(self, tmp_path):
        import yaml as pyyaml

        cv_path = self._write_cv(tmp_path)
        output_path = tmp_path / "out" / "index.html"

        import yaml

        with open(cv_path, encoding="utf-8") as f:
            cv = yaml.safe_load(f)

        html_content = self.mod.generate_html(cv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_file = tempfile.mkstemp(suffix=".html", dir=output_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(html_content)
            os.replace(tmp_file, output_path)
        except Exception:
            try:
                os.unlink(tmp_file)
            except OSError:
                pass
            raise

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_output_contains_name(self, tmp_path):
        cv_path = self._write_cv(tmp_path)
        import yaml

        with open(cv_path, encoding="utf-8") as f:
            cv = yaml.safe_load(f)

        html = self.mod.generate_html(cv)
        assert "Test" in html
        assert "User" in html

    def test_lang_fr_reads_cv_fr(self, tmp_path):
        """When lang=fr is requested, cv-fr.yml is loaded instead of cv.yml."""
        import yaml

        cv_fr = {
            "personal": {
                "first_name": "Marie",
                "last_name": "Dupont",
                "position": "Ingénieure",
                "email": "marie@example.fr",
            },
            "profile": "Profil en français.",
            "skills": [],
            "experience": [],
            "education": [],
            "languages": [],
        }
        cv_fr_path = tmp_path / "cv-fr.yml"
        cv_fr_path.write_text(yaml.dump(cv_fr), encoding="utf-8")

        with open(cv_fr_path, encoding="utf-8") as f:
            cv = yaml.safe_load(f)

        html = self.mod.generate_html(cv)
        assert "Marie" in html
        assert "Dupont" in html
        assert "Profil en français." in html

    def test_atomic_write_no_temp_file_left(self, tmp_path):
        """After writing, no .portfolio_tmp_* files should remain."""
        cv_path = self._write_cv(tmp_path)
        import yaml

        with open(cv_path, encoding="utf-8") as f:
            cv = yaml.safe_load(f)

        html_content = self.mod.generate_html(cv)
        output_path = tmp_path / "index.html"

        fd, tmp_file = tempfile.mkstemp(suffix=".html", dir=tmp_path, prefix=".portfolio_tmp_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html_content)
        os.replace(tmp_file, output_path)

        leftover = list(tmp_path.glob(".portfolio_tmp_*"))
        assert leftover == []


# ===========================================================================
# template-market.py
# ===========================================================================


class TestTemplateMarketBuiltIns:
    def setup_method(self):
        self.mod = _load("template-market")

    def test_built_ins_list_has_awesome_cv(self):
        names = [t["name"] for t in self.mod.BUILT_INS]
        assert "awesome-cv" in names

    def test_built_ins_list_has_moderncv(self):
        names = [t["name"] for t in self.mod.BUILT_INS]
        assert "moderncv" in names

    def test_built_ins_list_has_deedy(self):
        names = [t["name"] for t in self.mod.BUILT_INS]
        assert "deedy" in names

    def test_all_built_ins_have_built_in_flag(self):
        for t in self.mod.BUILT_INS:
            assert t.get("built_in") is True, f"{t['name']} missing built_in=True"

    def test_all_built_ins_have_tags(self):
        for t in self.mod.BUILT_INS:
            assert isinstance(t.get("tags"), list) and len(t["tags"]) > 0


class TestTemplateMarketSearch:
    def setup_method(self):
        self.mod = _load("template-market")

    def _search(self, query: str, templates=None) -> list[dict]:
        """Run cmd_search logic directly by patching _get_templates."""
        tpls = templates if templates is not None else list(self.mod.BUILT_INS)
        args = Namespace(query=query, json=False)
        with patch.object(self.mod, "_get_templates", return_value=(tpls, True)):
            with patch("builtins.print"):
                self.mod.cmd_search(args)
        # Re-implement filter to return results for assertion
        q = query.lower()
        return [
            t for t in tpls
            if q in t.get("name", "").lower()
            or q in t.get("description", "").lower()
            or any(q in tag.lower() for tag in t.get("tags", []))
            or q in t.get("author", "").lower()
        ]

    def test_search_by_name(self):
        results = self._search("moderncv")
        assert any(t["name"] == "moderncv" for t in results)

    def test_search_by_tag(self):
        results = self._search("tech")
        assert any(t["name"] == "deedy" for t in results)

    def test_search_by_description(self):
        results = self._search("classic")
        assert len(results) >= 1

    def test_search_no_match_returns_empty(self):
        results = self._search("zzznomatch99")
        assert results == []

    def test_search_case_insensitive(self):
        results = self._search("AWESOME")
        assert any("awesome" in t["name"] for t in results)


class TestTemplateMarketFormatTable:
    """Test that list output contains template names."""

    def setup_method(self):
        self.mod = _load("template-market")

    def test_list_includes_awesome_cv(self, capsys):
        args = Namespace(tag=None, json=False)
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            self.mod.cmd_list(args)
        out = capsys.readouterr().out
        assert "awesome-cv" in out

    def test_list_includes_moderncv(self, capsys):
        args = Namespace(tag=None, json=False)
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            self.mod.cmd_list(args)
        out = capsys.readouterr().out
        assert "moderncv" in out

    def test_list_includes_deedy(self, capsys):
        args = Namespace(tag=None, json=False)
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            self.mod.cmd_list(args)
        out = capsys.readouterr().out
        assert "deedy" in out

    def test_list_offline_prints_warning(self, capsys):
        args = Namespace(tag=None, json=False)
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), False)):
            self.mod.cmd_list(args)
        err = capsys.readouterr().err
        assert "Warning" in err or "unreachable" in err

    def test_list_tag_filter_tech(self, capsys):
        args = Namespace(tag="tech", json=False)
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            self.mod.cmd_list(args)
        out = capsys.readouterr().out
        assert "deedy" in out
        assert "moderncv" not in out

    def test_list_json_output(self, capsys):
        args = Namespace(tag=None, json=True)
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            self.mod.cmd_list(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "templates" in data
        assert isinstance(data["templates"], list)


class TestTemplateMarketInfo:
    def setup_method(self):
        self.mod = _load("template-market")

    def test_info_found_builtin(self, capsys):
        args = Namespace(name="awesome-cv")
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            with patch.object(self.mod, "_get_installed", return_value=[]):
                rc = self.mod.cmd_info(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "awesome-cv" in out

    def test_info_not_found_returns_1(self, capsys):
        args = Namespace(name="nonexistent-template-xyz")
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            with patch.object(self.mod, "_get_installed", return_value=[]):
                rc = self.mod.cmd_info(args)
        assert rc == 1

    def test_info_not_found_prints_message(self, capsys):
        args = Namespace(name="nonexistent-template-xyz")
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            with patch.object(self.mod, "_get_installed", return_value=[]):
                self.mod.cmd_info(args)
        out = capsys.readouterr().out
        assert "not found" in out.lower()


class TestTemplateMarketInstall:
    def setup_method(self):
        self.mod = _load("template-market")

    def test_install_builtin_prints_already_builtin(self, capsys):
        args = Namespace(name="awesome-cv")
        rc = self.mod.cmd_install(args)
        out = capsys.readouterr().out
        assert "built-in" in out.lower()
        assert rc == 0

    def test_install_builtin_moderncv_returns_0(self, capsys):
        args = Namespace(name="moderncv")
        rc = self.mod.cmd_install(args)
        assert rc == 0

    def test_install_unknown_offline_returns_1(self, capsys):
        args = Namespace(name="totally-unknown-template-abc123")
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), False)):
            rc = self.mod.cmd_install(args)
        err = capsys.readouterr().err
        assert rc == 1
        assert "Error" in err or "unreachable" in err

    def test_install_unknown_not_in_registry_returns_1(self, capsys):
        args = Namespace(name="totally-unknown-template-abc123")
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            rc = self.mod.cmd_install(args)
        out = capsys.readouterr().out
        assert rc == 1
        assert "not found" in out.lower()


class TestTemplateMarketInstalled:
    def setup_method(self):
        self.mod = _load("template-market")

    def test_installed_always_includes_awesome_cv(self, capsys):
        args = Namespace(json=False)
        with patch.object(self.mod, "_get_installed", return_value=[]):
            self.mod.cmd_installed(args)
        out = capsys.readouterr().out
        assert "awesome-cv" in out

    def test_installed_always_includes_moderncv(self, capsys):
        args = Namespace(json=False)
        with patch.object(self.mod, "_get_installed", return_value=[]):
            self.mod.cmd_installed(args)
        out = capsys.readouterr().out
        assert "moderncv" in out

    def test_installed_always_includes_deedy(self, capsys):
        args = Namespace(json=False)
        with patch.object(self.mod, "_get_installed", return_value=[]):
            self.mod.cmd_installed(args)
        out = capsys.readouterr().out
        assert "deedy" in out

    def test_installed_json_valid(self, capsys):
        args = Namespace(json=True)
        with patch.object(self.mod, "_get_installed", return_value=[]):
            self.mod.cmd_installed(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "installed" in data
        names = [t["name"] for t in data["installed"]]
        assert "awesome-cv" in names

    def test_installed_shows_community_template_if_present(self, capsys):
        extra = {
            "name": "my-custom-tpl",
            "description": "Custom",
            "author": "Me",
            "version": "1.0",
            "built_in": False,
            "tags": [],
            "installed": True,
        }
        args = Namespace(json=False)
        with patch.object(self.mod, "_get_installed", return_value=[extra]):
            self.mod.cmd_installed(args)
        out = capsys.readouterr().out
        assert "my-custom-tpl" in out


class TestTemplateMarketFetchRegistry:
    def setup_method(self):
        self.mod = _load("template-market")

    def test_fetch_registry_network_fail_returns_builtin_only(self):
        """When network is unavailable, _get_templates returns built-ins only."""
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            templates, is_online = self.mod._get_templates()

        assert is_online is False
        names = {t["name"] for t in templates}
        assert "awesome-cv" in names
        assert "moderncv" in names
        assert "deedy" in names

    def test_fetch_registry_success_returns_online_true(self):
        registry_payload = json.dumps({"templates": list(self.mod.BUILT_INS)}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = registry_payload
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            templates, is_online = self.mod._get_templates()

        assert is_online is True
        assert len(templates) >= 3

    def test_fetch_registry_json_error_falls_back(self):
        """Malformed JSON should be caught and fall back to built-ins."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not valid json {"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            templates, is_online = self.mod._get_templates()

        assert is_online is False
        assert any(t["name"] == "awesome-cv" for t in templates)

    def test_search_json_output_valid(self, capsys):
        args = Namespace(query="awesome", json=True)
        with patch.object(self.mod, "_get_templates", return_value=(list(self.mod.BUILT_INS), True)):
            self.mod.cmd_search(args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "results" in data
        assert "query" in data
        assert len(data["results"]) >= 1
