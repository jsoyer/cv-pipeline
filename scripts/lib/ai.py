"""Shared AI provider module -- call LLMs via Gemini, Claude, OpenAI, Mistral, or Ollama.

Usage::

    from lib.ai import call_ai, KEY_ENV, VALID_PROVIDERS

    text = call_ai(prompt, "gemini", api_key)
    text = call_ai(prompt, "claude", api_key, model="claude-opus-4-6", temperature=0.7)
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

__all__ = [
    "call_ai",
    "call_gemini",
    "call_claude",
    "call_openai_compat",
    "call_ollama",
    "VALID_PROVIDERS",
    "KEY_ENV",
    "PROVIDER_MODELS",
]

# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_FALLBACK = "gemini-2.0-flash-lite"

CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_FALLBACK = "claude-haiku-4-5-20251001"

OPENAI_MODEL = "gpt-4o"
OPENAI_FALLBACK = "gpt-4o-mini"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"

MISTRAL_MODEL = "mistral-large-latest"
MISTRAL_FALLBACK = "mistral-small-latest"
MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"

VALID_PROVIDERS: set[str] = {"gemini", "claude", "openai", "mistral", "ollama"}

PROVIDER_MODELS: dict[str, list[str]] = {
    "gemini": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro"],
    "claude": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o1-mini"],
    "mistral": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
    "ollama": [],
}

KEY_ENV: dict[str, str | None] = {
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "ollama": None,
}

# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


def call_gemini(
    prompt: str,
    api_key: str,
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 8192,
    retries: int = 6,
) -> str:
    """Call Gemini API with exponential backoff on 429 and model fallback."""
    models_to_try = [model] if model else [GEMINI_MODEL, GEMINI_FALLBACK]
    for m in models_to_try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{m}:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = resp.read()
                try:
                    result = json.loads(body)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"Gemini returned invalid JSON: {e}")
                if m != models_to_try[0]:
                    log.debug("Used fallback model: %s", m)
                try:
                    return result["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError, TypeError) as e:
                    raise RuntimeError(
                        f"Gemini unexpected response structure: {e}"
                        f" — {str(result)[:200]}"
                    )
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    wait = min(2 ** (attempt + 2), 120)
                    log.warning(
                        "Rate limited (429) on %s, retrying in %ds... (%d/%d)",
                        m, wait, attempt + 1, retries,
                    )
                    time.sleep(wait)
                elif e.code == 429 and m != models_to_try[-1]:
                    log.warning(
                        "%s still rate-limited, switching to %s...",
                        m, models_to_try[-1],
                    )
                    break
                else:
                    raise
    tried = model or f"{GEMINI_MODEL} and {GEMINI_FALLBACK}"
    raise RuntimeError(f"Gemini API rate-limited on {tried}. Try again later.")


def call_claude(
    prompt: str,
    api_key: str,
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 8192,
    retries: int = 6,
) -> str:
    """Call Anthropic Claude API with exponential backoff and model fallback."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    models_to_try = [model] if model else [CLAUDE_MODEL, CLAUDE_FALLBACK]
    for m in models_to_try:
        payload = json.dumps({
            "model": m,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = resp.read()
                try:
                    result = json.loads(body)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"Claude returned invalid JSON: {e}")
                if m != models_to_try[0]:
                    log.debug("Used fallback model: %s", m)
                try:
                    return result["content"][0]["text"]
                except (KeyError, IndexError, TypeError) as e:
                    raise RuntimeError(
                        f"Claude unexpected response structure: {e}"
                        f" — {str(result)[:200]}"
                    )
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    wait = min(2 ** (attempt + 2), 120)
                    log.warning(
                        "Rate limited (429) on %s, retrying in %ds... (%d/%d)",
                        m, wait, attempt + 1, retries,
                    )
                    time.sleep(wait)
                elif e.code == 429 and m != models_to_try[-1]:
                    log.warning(
                        "%s still rate-limited, switching to %s...",
                        m, models_to_try[-1],
                    )
                    break
                else:
                    raise
    tried = model or f"{CLAUDE_MODEL} and {CLAUDE_FALLBACK}"
    raise RuntimeError(
        f"Claude API rate-limited on {tried}. Try again later."
    )


def call_openai_compat(
    prompt: str,
    endpoint: str,
    api_key: str | None,
    models: tuple[str, str],
    *,
    temperature: float = 0.4,
    max_tokens: int = 8192,
    retries: int = 6,
) -> str:
    """Call an OpenAI-compatible chat completions endpoint (OpenAI / Mistral)."""
    primary, fallback = models
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }
    for m in (primary, fallback):
        payload = json.dumps({
            "model": m,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode()
        for attempt in range(retries):
            req = urllib.request.Request(
                endpoint, data=payload, headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = resp.read()
                try:
                    result = json.loads(body)
                except json.JSONDecodeError as e:
                    raise RuntimeError(
                        f"OpenAI-compat ({endpoint}) returned invalid JSON: {e}"
                    )
                if m != primary:
                    log.debug("Used fallback model: %s", m)
                try:
                    return result["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    raise RuntimeError(
                        f"OpenAI-compat ({endpoint}) unexpected response structure:"
                        f" {e} — {str(result)[:200]}"
                    )
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    wait = min(2 ** (attempt + 2), 120)
                    log.warning(
                        "Rate limited (429) on %s, retrying in %ds... (%d/%d)",
                        m, wait, attempt + 1, retries,
                    )
                    time.sleep(wait)
                elif e.code == 429 and m != fallback:
                    log.warning(
                        "%s still rate-limited, switching to %s...",
                        m, fallback,
                    )
                    break
                else:
                    raise
    raise RuntimeError(
        f"API rate-limited on both {primary} and {fallback}. Try again later."
    )


def call_ollama(
    prompt: str,
    *,
    temperature: float = 0.4,
    retries: int = 3,
) -> str:
    """Call a local Ollama instance (no API key required).

    Configure via OLLAMA_HOST (default: http://localhost:11434)
    and OLLAMA_MODEL (default: llama3).
    """
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3")
    url = f"{host}/api/chat"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature},
    }).encode()
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=payload,
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = resp.read()
            try:
                result = json.loads(body)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Ollama returned invalid JSON: {e}")
            try:
                return result["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                raise RuntimeError(
                    f"Ollama unexpected response structure: {e}"
                    f" — {str(result)[:200]}"
                )
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError(
                    f"Model '{model}' not found in Ollama. "
                    f"Pull it first: ollama pull {model}"
                ) from e
            raise
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                log.warning(
                    "Ollama unreachable, retrying in %ds... (%d/%d)",
                    wait, attempt + 1, retries,
                )
                time.sleep(wait)
            else:
                raise RuntimeError(
                    f"Cannot connect to Ollama at {host}. "
                    f"Is Ollama running? Try: ollama serve"
                ) from e
    raise RuntimeError(f"Cannot connect to Ollama at {host}")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def call_ai(
    prompt: str,
    provider: str,
    api_key: str | None = None,
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
) -> str:
    """Dispatch to the appropriate AI provider.

    Parameters
    ----------
    prompt : str
    provider : str  -- one of VALID_PROVIDERS
    api_key : str | None
    model : str | None -- override the default model for the provider
    temperature : float
    max_tokens : int
    """
    if provider in ("gemini", "claude") and not api_key:
        key_name = KEY_ENV.get(provider, "API_KEY")
        raise ValueError(f"{provider} requires an API key (set {key_name})")

    if provider == "gemini":
        assert api_key is not None  # guarded above
        return call_gemini(
            prompt, api_key, model=model,
            temperature=temperature, max_tokens=max_tokens,
        )
    if provider == "claude":
        assert api_key is not None  # guarded above
        return call_claude(
            prompt, api_key, model=model,
            temperature=temperature, max_tokens=max_tokens,
        )
    if provider == "openai":
        primary = model or OPENAI_MODEL
        models = (primary, primary) if model else (OPENAI_MODEL, OPENAI_FALLBACK)
        return call_openai_compat(
            prompt, OPENAI_ENDPOINT, api_key, models,
            temperature=temperature, max_tokens=max_tokens,
        )
    if provider == "mistral":
        primary = model or MISTRAL_MODEL
        models = (primary, primary) if model else (MISTRAL_MODEL, MISTRAL_FALLBACK)
        return call_openai_compat(
            prompt, MISTRAL_ENDPOINT, api_key, models,
            temperature=temperature, max_tokens=max_tokens,
        )
    if provider == "ollama":
        return call_ollama(prompt, temperature=temperature)
    raise ValueError(
        f"Unknown provider: '{provider}'. Valid: {sorted(VALID_PROVIDERS)}"
    )
