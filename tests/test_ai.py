"""Unit tests for scripts/lib/ai.py."""

import io
import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from lib.ai import (
    KEY_ENV,
    PROVIDER_MODELS,
    VALID_PROVIDERS,
    call_ai,
    call_claude,
    call_gemini,
)


# ---------------------------------------------------------------------------
# Static metadata
# ---------------------------------------------------------------------------


class TestValidProviders:
    def test_is_set(self):
        assert isinstance(VALID_PROVIDERS, set)

    def test_contains_expected_providers(self):
        assert VALID_PROVIDERS == {"gemini", "claude", "openai", "mistral", "ollama"}

    def test_all_providers_have_key_env_entry(self):
        for provider in VALID_PROVIDERS:
            assert provider in KEY_ENV

    def test_all_providers_have_model_entry(self):
        for provider in VALID_PROVIDERS:
            assert provider in PROVIDER_MODELS


class TestKeyEnv:
    def test_gemini_maps_to_gemini_api_key(self):
        assert KEY_ENV["gemini"] == "GEMINI_API_KEY"

    def test_claude_maps_to_anthropic_api_key(self):
        assert KEY_ENV["claude"] == "ANTHROPIC_API_KEY"

    def test_openai_maps_to_openai_api_key(self):
        assert KEY_ENV["openai"] == "OPENAI_API_KEY"

    def test_mistral_maps_to_mistral_api_key(self):
        assert KEY_ENV["mistral"] == "MISTRAL_API_KEY"

    def test_ollama_has_no_key(self):
        assert KEY_ENV["ollama"] is None


class TestProviderModels:
    def test_gemini_has_models(self):
        assert len(PROVIDER_MODELS["gemini"]) > 0

    def test_claude_has_models(self):
        assert len(PROVIDER_MODELS["claude"]) > 0

    def test_openai_has_models(self):
        assert len(PROVIDER_MODELS["openai"]) > 0

    def test_mistral_has_models(self):
        assert len(PROVIDER_MODELS["mistral"]) > 0

    def test_all_model_entries_are_lists(self):
        for provider, models in PROVIDER_MODELS.items():
            assert isinstance(models, list), f"{provider} models should be a list"

    def test_model_strings_are_nonempty(self):
        for provider, models in PROVIDER_MODELS.items():
            for model in models:
                assert isinstance(model, str) and len(model) > 0


# ---------------------------------------------------------------------------
# call_ai — dispatcher validation
# ---------------------------------------------------------------------------


class TestCallAiDispatcher:
    def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            call_ai("prompt", "nonexistent_provider")

    def test_gemini_without_api_key_raises_value_error(self):
        with pytest.raises(ValueError, match="gemini requires an API key"):
            call_ai("prompt", "gemini", api_key=None)

    def test_claude_without_api_key_raises_value_error(self):
        with pytest.raises(ValueError, match="claude requires an API key"):
            call_ai("prompt", "claude", api_key=None)

    def test_openai_does_not_raise_without_api_key(self):
        # openai/mistral are allowed to proceed without an API key at the dispatcher
        # level (the HTTP call itself would fail). We just check no ValueError is raised.
        mock_resp = _make_mock_response({
            "choices": [{"message": {"content": "ok"}}]
        })
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = call_ai("prompt", "openai", api_key=None)
        assert result == "ok"


# ---------------------------------------------------------------------------
# call_gemini — mocked HTTP
# ---------------------------------------------------------------------------


def _make_mock_response(payload: dict, status: int = 200):
    """Return a context-manager mock that simulates urllib.request.urlopen."""
    body = json.dumps(payload).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _make_http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.com",
        code=code,
        msg=f"HTTP {code}",
        hdrs=None,
        fp=io.BytesIO(b""),
    )


class TestCallGemini:
    def test_successful_response(self):
        payload = {
            "candidates": [
                {"content": {"parts": [{"text": "Hello from Gemini"}]}}
            ]
        }
        mock_resp = _make_mock_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = call_gemini("test prompt", api_key="fake-key", retries=1)
        assert result == "Hello from Gemini"

    def test_invalid_json_raises_runtime_error(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not-json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="invalid JSON"):
                call_gemini("prompt", api_key="fake-key", model="gemini-2.5-flash", retries=1)

    def test_unexpected_response_structure_raises_runtime_error(self):
        payload = {"unexpected": "shape"}
        mock_resp = _make_mock_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="unexpected response structure"):
                call_gemini("prompt", api_key="fake-key", model="gemini-2.5-flash", retries=1)

    def test_retry_on_429_then_success(self):
        payload = {
            "candidates": [
                {"content": {"parts": [{"text": "retry worked"}]}}
            ]
        }
        success_resp = _make_mock_response(payload)
        http_error_429 = _make_http_error(429)

        call_count = {"n": 0}

        def side_effect(req, timeout):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise http_error_429
            return success_resp

        with patch("urllib.request.urlopen", side_effect=side_effect), \
             patch("time.sleep") as mock_sleep:
            result = call_gemini(
                "prompt", api_key="fake-key",
                model="gemini-2.5-flash", retries=3,
            )

        assert result == "retry worked"
        # sleep must have been called once for the first 429.
        mock_sleep.assert_called_once()

    def test_exhausted_retries_propagate_http_error(self):
        # When the fallback model is also rate-limited and has no further fallback,
        # the last HTTPError propagates (the function re-raises it).
        http_error_429 = _make_http_error(429)
        with patch("urllib.request.urlopen", side_effect=http_error_429), \
             patch("time.sleep"):
            with pytest.raises(urllib.error.HTTPError):
                call_gemini("prompt", api_key="fake-key", retries=1)


# ---------------------------------------------------------------------------
# call_claude — mocked HTTP
# ---------------------------------------------------------------------------


class TestCallClaude:
    def test_successful_response(self):
        payload = {"content": [{"text": "Hello from Claude"}]}
        mock_resp = _make_mock_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = call_claude("test prompt", api_key="fake-key", retries=1)
        assert result == "Hello from Claude"

    def test_invalid_json_raises_runtime_error(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not-json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="invalid JSON"):
                call_claude("prompt", api_key="fake-key", model="claude-sonnet-4-6", retries=1)

    def test_unexpected_response_structure_raises_runtime_error(self):
        payload = {"wrong": "structure"}
        mock_resp = _make_mock_response(payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="unexpected response structure"):
                call_claude("prompt", api_key="fake-key", model="claude-sonnet-4-6", retries=1)

    def test_retry_on_429_then_success(self):
        payload = {"content": [{"text": "retry worked"}]}
        success_resp = _make_mock_response(payload)
        http_error_429 = _make_http_error(429)

        call_count = {"n": 0}

        def side_effect(req, timeout):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise http_error_429
            return success_resp

        with patch("urllib.request.urlopen", side_effect=side_effect), \
             patch("time.sleep") as mock_sleep:
            result = call_claude(
                "prompt", api_key="fake-key",
                model="claude-sonnet-4-6", retries=3,
            )

        assert result == "retry worked"
        mock_sleep.assert_called_once()

    def test_exhausted_retries_propagate_http_error(self):
        # When the fallback model is also rate-limited and has no further fallback,
        # the last HTTPError propagates (the function re-raises it).
        http_error_429 = _make_http_error(429)
        with patch("urllib.request.urlopen", side_effect=http_error_429), \
             patch("time.sleep"):
            with pytest.raises(urllib.error.HTTPError):
                call_claude("prompt", api_key="fake-key", retries=1)

    def test_non_429_http_error_propagates(self):
        http_error_500 = _make_http_error(500)
        with patch("urllib.request.urlopen", side_effect=http_error_500):
            with pytest.raises(urllib.error.HTTPError):
                call_claude("prompt", api_key="fake-key", model="claude-sonnet-4-6", retries=1)
