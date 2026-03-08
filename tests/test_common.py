"""Unit tests for scripts/lib/common.py."""

import os
from pathlib import Path
from types import ModuleType

import pytest

from lib.common import (
    REPO_ROOT,
    SCRIPTS_DIR,
    STOP_WORDS,
    TIMEOUT_GIT,
    TIMEOUT_HTTP,
    TIMEOUT_SUBPROCESS,
    TIMEOUT_SUBPROCESS_LONG,
    USER_AGENT,
    company_from_dirname,
    load_env,
    require_yaml,
)


# ---------------------------------------------------------------------------
# company_from_dirname
# ---------------------------------------------------------------------------


class TestCompanyFromDirname:
    def test_simple_slug(self):
        assert company_from_dirname("2026-02-anthropic") == "Anthropic"

    def test_multi_word_slug(self):
        assert company_from_dirname("2026-02-orange-cyberdefense") == "Orange Cyberdefense"

    def test_single_char_slug(self):
        assert company_from_dirname("2026-02-a") == "A"

    def test_three_word_slug(self):
        assert company_from_dirname("2025-11-big-tech-corp") == "Big Tech Corp"

    def test_no_suffix_returns_original(self):
        # Only one or two segments — fallback to the whole name unchanged.
        assert company_from_dirname("anthropic") == "anthropic"

    def test_two_segments_returns_original(self):
        assert company_from_dirname("2026-anthropic") == "2026-anthropic"


# ---------------------------------------------------------------------------
# require_yaml
# ---------------------------------------------------------------------------


class TestRequireYaml:
    def test_returns_module(self):
        mod = require_yaml()
        assert isinstance(mod, ModuleType)

    def test_has_safe_load(self):
        mod = require_yaml()
        assert hasattr(mod, "safe_load")
        assert callable(mod.safe_load)

    def test_safe_load_works(self):
        mod = require_yaml()
        result = mod.safe_load("key: value")
        assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# REPO_ROOT / SCRIPTS_DIR
# ---------------------------------------------------------------------------


class TestPaths:
    def test_repo_root_is_path(self):
        assert isinstance(REPO_ROOT, Path)

    def test_repo_root_exists(self):
        assert REPO_ROOT.exists(), f"REPO_ROOT does not exist: {REPO_ROOT}"

    def test_repo_root_is_directory(self):
        assert REPO_ROOT.is_dir()

    def test_scripts_dir_is_path(self):
        assert isinstance(SCRIPTS_DIR, Path)

    def test_scripts_dir_exists(self):
        assert SCRIPTS_DIR.exists(), f"SCRIPTS_DIR does not exist: {SCRIPTS_DIR}"

    def test_scripts_dir_is_directory(self):
        assert SCRIPTS_DIR.is_dir()

    def test_scripts_dir_is_child_of_repo_root(self):
        assert SCRIPTS_DIR.parent == REPO_ROOT

    def test_repo_root_contains_makefile(self):
        # Sanity-check that we landed in the right repo.
        assert (REPO_ROOT / "Makefile").exists()


# ---------------------------------------------------------------------------
# STOP_WORDS
# ---------------------------------------------------------------------------


class TestStopWords:
    def test_is_frozenset(self):
        assert isinstance(STOP_WORDS, frozenset)

    def test_common_english_words_present(self):
        expected = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "to"}
        assert expected.issubset(STOP_WORDS)

    def test_job_posting_fillers_present(self):
        assert "requirements" in STOP_WORDS
        assert "responsibilities" in STOP_WORDS
        assert "experience" in STOP_WORDS

    def test_technical_terms_not_present(self):
        # Words that should NOT be stop words.
        for word in ("python", "api", "cloud", "kubernetes", "security"):
            assert word not in STOP_WORDS

    def test_nonempty(self):
        assert len(STOP_WORDS) > 50


# ---------------------------------------------------------------------------
# USER_AGENT
# ---------------------------------------------------------------------------


class TestUserAgent:
    def test_is_string(self):
        assert isinstance(USER_AGENT, str)

    def test_nonempty(self):
        assert len(USER_AGENT) > 0

    def test_looks_like_browser_ua(self):
        assert "Mozilla" in USER_AGENT


# ---------------------------------------------------------------------------
# load_env
# ---------------------------------------------------------------------------


class TestLoadEnv:
    def test_does_not_crash_without_env_file(self, tmp_path, monkeypatch):
        # Point REPO_ROOT at a temp dir that has no .env file.
        import lib.common as common_mod
        monkeypatch.setattr(common_mod, "REPO_ROOT", tmp_path)
        # Should return None silently.
        result = load_env()
        assert result is None

    def test_loads_key_value_pairs(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text('TEST_KEY_XYZ=hello_world\n# comment\nANOTHER=42\n')
        import lib.common as common_mod
        monkeypatch.setattr(common_mod, "REPO_ROOT", tmp_path)
        # Ensure keys are absent before calling.
        monkeypatch.delenv("TEST_KEY_XYZ", raising=False)
        monkeypatch.delenv("ANOTHER", raising=False)
        load_env()
        assert os.environ.get("TEST_KEY_XYZ") == "hello_world"
        assert os.environ.get("ANOTHER") == "42"

    def test_setdefault_does_not_override(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("PRESET_VAR=from_file\n")
        import lib.common as common_mod
        monkeypatch.setattr(common_mod, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("PRESET_VAR", "already_set")
        load_env()
        # setdefault must not overwrite an existing env var.
        assert os.environ["PRESET_VAR"] == "already_set"

    def test_strips_quotes_from_values(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text('QUOTED_VAR="quoted_value"\n')
        import lib.common as common_mod
        monkeypatch.setattr(common_mod, "REPO_ROOT", tmp_path)
        monkeypatch.delenv("QUOTED_VAR", raising=False)
        load_env()
        assert os.environ.get("QUOTED_VAR") == "quoted_value"


# ---------------------------------------------------------------------------
# Timeout constants
# ---------------------------------------------------------------------------


class TestTimeoutConstants:
    def test_timeout_http_positive(self):
        assert isinstance(TIMEOUT_HTTP, int)
        assert TIMEOUT_HTTP > 0

    def test_timeout_subprocess_positive(self):
        assert isinstance(TIMEOUT_SUBPROCESS, int)
        assert TIMEOUT_SUBPROCESS > 0

    def test_timeout_subprocess_long_positive(self):
        assert isinstance(TIMEOUT_SUBPROCESS_LONG, int)
        assert TIMEOUT_SUBPROCESS_LONG > 0

    def test_timeout_git_positive(self):
        assert isinstance(TIMEOUT_GIT, int)
        assert TIMEOUT_GIT > 0

    def test_timeout_ordering(self):
        # Long subprocess timeout should be the largest; HTTP should be smallest.
        assert TIMEOUT_HTTP <= TIMEOUT_SUBPROCESS
        assert TIMEOUT_SUBPROCESS <= TIMEOUT_SUBPROCESS_LONG
