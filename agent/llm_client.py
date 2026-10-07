"""
agent/llm_client.py — shared LLM-calling infrastructure for every LLM-powered
node in the pipeline (currently Domain/KPI and Reflector).

Provides:
  - call_llm(system_prompt, user_content, provider, response_model): the
    single entry point every node should use to get a structured response
    back from whichever provider LLM_PROVIDER selects.
  - Per-provider model fallback: each provider has a primary model (from
    GEMINI_MODEL / MISTRAL_MODEL) and one fallback model (from
    GEMINI_MODEL_FALLBACK / MISTRAL_MODEL_FALLBACK), used if the primary
    model is unavailable after retries.
  - Retry-with-backoff on transient errors (503/429/"overloaded"/etc.) for
    each model before moving to the fallback model.

This module has no knowledge of any specific node's response schema —
response_model is always supplied by the caller. It does not know what a
DataProfile, KPISpec, or ReflectionNote is; it only knows how to get a
validated Pydantic object back from Gemini or Mistral.
"""
from __future__ import annotations

import os
import time

# ---------------------------------------------------------------------------
# Retry / fallback configuration
# ---------------------------------------------------------------------------

# Hardcoded last-resort defaults, used only if the corresponding env var
# isn't set. The .env.example ships GEMINI_MODEL / MISTRAL_MODEL /
# GEMINI_MODEL_FALLBACK / MISTRAL_MODEL_FALLBACK explicitly, so in normal
# operation these defaults are rarely what actually gets used.
#
# Canonical IDs (reconciled 2026-10-07 during flagship hardening so
# llm_client.py, .env.example, and the README tech-stack table agree
# byte-for-byte; historically the three places disagreed on the Gemini
# primary). The Gemini primary matches .env.example's long-standing value;
# per Google's model-lifecycle docs gemini-3.5-flash is GA with retirement
# no earlier than May 2027, while the 2.x Flash IDs are retiring
# 2026-10-20 -- hence 3.5-flash, not a 2.x ID, is canonical. Live API
# verification of these IDs was not performed in this environment (no keys
# available); if a future run reports an unknown-model error, update all
# three places together.
_DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
_DEFAULT_GEMINI_MODEL_FALLBACK = "gemini-3.1-pro"
_DEFAULT_MISTRAL_MODEL = "mistral-large-latest"
_DEFAULT_MISTRAL_MODEL_FALLBACK = "mistral-medium-latest"

# Retry-with-backoff parameters for transient (server-overload / rate-limit)
# errors, applied per model before moving to the fallback model. Only two
# models per provider (primary + one fallback) — a longer chain would add
# meaningfully more worst-case latency on top of the backoff retries
# themselves, for diminishing benefit.
MAX_RETRIES_PER_MODEL = 3
BACKOFF_BASE_SECONDS = 2  # 2s, 4s, 8s

# Substrings that indicate a transient, retryable error when the SDK doesn't
# expose a clean typed status code (varies by SDK version — see
# https://github.com/google-gemini/cookbook/issues/1091 for why relying on
# exception type alone isn't fully reliable across google-genai versions).
_TRANSIENT_ERROR_MARKERS = ("503", "429", "unavailable", "overloaded", "rate limit", "resource_exhausted")


def _is_transient_error(exc: Exception) -> bool:
    """
    Best-effort detection of a transient (retryable) API error, checking a
    typed status code where the SDK exposes one, falling back to substring
    matching on the error message otherwise.
    """
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)


def _call_with_model_fallback(call_fn, model_chain: list[str], provider_label: str):
    """
    Try each model in model_chain in order. For each model, retry up to
    MAX_RETRIES_PER_MODEL times with exponential backoff on transient errors
    before moving to the next model. Non-transient errors (bad API key,
    invalid request, etc.) are raised immediately without retrying or
    falling through — retrying those would just fail the same way every time.

    call_fn: a callable taking a single model_name argument and returning
    the parsed structured response.

    Raises a RuntimeError with a clear summary (including a suggestion to
    switch LLM_PROVIDER) if every model in the chain is exhausted.

    Prints a message immediately before every attempt (not just on retry or
    failure) and immediately after a successful call completes, with elapsed
    time — so the console is never silent while a call is in flight. Without
    this, a slow-but-working call and a hung one look identical from the
    outside.
    """
    last_exc: Exception | None = None

    for model_name in model_chain:
        for attempt in range(1, MAX_RETRIES_PER_MODEL + 1):
            attempt_label = f"attempt {attempt}/{MAX_RETRIES_PER_MODEL}" if attempt > 1 or len(model_chain) > 1 else ""
            print(
                f"[{provider_label}] Calling '{model_name}'"
                + (f" ({attempt_label})" if attempt_label else "")
                + "... (waiting for response)"
            )
            start = time.monotonic()
            try:
                result = call_fn(model_name)
                elapsed = time.monotonic() - start
                print(f"[{provider_label}] '{model_name}' responded in {elapsed:.1f}s.")
                return result
            except Exception as exc:
                elapsed = time.monotonic() - start
                last_exc = exc
                if not _is_transient_error(exc):
                    # Not a transient/overload error — retrying or falling
                    # back to another model won't help (e.g. bad request,
                    # auth failure). Raise immediately.
                    print(f"[{provider_label}] '{model_name}' failed after {elapsed:.1f}s with a non-retryable error: {exc}")
                    raise
                if attempt < MAX_RETRIES_PER_MODEL:
                    wait_seconds = BACKOFF_BASE_SECONDS ** attempt
                    print(
                        f"[{provider_label}] '{model_name}' transient error after {elapsed:.1f}s on attempt "
                        f"{attempt}/{MAX_RETRIES_PER_MODEL} ({exc}); retrying in {wait_seconds}s..."
                    )
                    time.sleep(wait_seconds)
                else:
                    print(
                        f"[{provider_label}] '{model_name}' exhausted {MAX_RETRIES_PER_MODEL} "
                        f"attempts (last failure after {elapsed:.1f}s), all transient errors. "
                        f"Trying fallback model, if any."
                    )

    other_provider = "mistral" if provider_label == "gemini" else "gemini"
    raise RuntimeError(
        f"{provider_label} models {model_chain} all failed after retries with backoff "
        f"(last error: {last_exc}). This looks like a sustained provider-side outage or "
        f"capacity issue, not a code problem. Consider switching LLM_PROVIDER to "
        f"'{other_provider}' and retrying, or waiting and trying '{provider_label}' again shortly."
    )


def _gemini_model_chain() -> list[str]:
    primary = os.environ.get("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
    fallback = os.environ.get("GEMINI_MODEL_FALLBACK", _DEFAULT_GEMINI_MODEL_FALLBACK)
    return [primary] if primary == fallback else [primary, fallback]


def _mistral_model_chain() -> list[str]:
    primary = os.environ.get("MISTRAL_MODEL", _DEFAULT_MISTRAL_MODEL)
    fallback = os.environ.get("MISTRAL_MODEL_FALLBACK", _DEFAULT_MISTRAL_MODEL_FALLBACK)
    return [primary] if primary == fallback else [primary, fallback]


# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------

def call_gemini(system_prompt: str, user_content: str, response_model: type):
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Set it in your environment or .env file "
            "(e.g. `$env:GEMINI_API_KEY = \"...\"` in PowerShell, or `export "
            "GEMINI_API_KEY=...` in bash) before calling a node with "
            "LLM_PROVIDER=gemini. Get a key at https://aistudio.google.com/apikey."
        )

    client = genai.Client(api_key=api_key)
    model_chain = _gemini_model_chain()

    def _do_call(model_name: str):
        response = client.models.generate_content(
            model=model_name,
            contents=user_content,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": response_model,
                # temperature=0 for cross-provider determinism; matches Mistral path
                "temperature": 0,
            },
        )
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed
        return response_model.model_validate_json(response.text)

    return _call_with_model_fallback(_do_call, model_chain, provider_label="gemini")


def call_mistral(system_prompt: str, user_content: str, response_model: type):
    # mistralai v2.0.0 (2026-03) moved the Mistral client class's import path.
    # v1.x: `from mistralai import Mistral`
    # v2.x: `from mistralai.client import Mistral`
    # Support both so this doesn't break on whichever version is installed.
    #
    # NOTE: this is deliberately NOT covered by a unit test. Verifying which
    # import path a specific mistralai version exposes is checking a
    # third-party package's internal structure, not this application's
    # behavior — such a test would fail the moment mistralai ships a v3 with
    # yet another layout, which is a dependency-version event, not a bug
    # here. If mistralai is upgraded, verify this manually:
    #   python -c "from mistralai import Mistral" (v1.x)
    #   python -c "from mistralai.client import Mistral" (v2.x)
    # and update this try/except if a new major version changes the path
    # again.
    try:
        from mistralai import Mistral  # v1.x
    except ImportError:
        from mistralai.client import Mistral  # v2.x

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MISTRAL_API_KEY is not set. Set it in your environment or .env file "
            "(e.g. `$env:MISTRAL_API_KEY = \"...\"` in PowerShell, or `export "
            "MISTRAL_API_KEY=...` in bash) before calling a node with "
            "LLM_PROVIDER=mistral. Get a key at https://console.mistral.ai/api-keys."
        )

    client = Mistral(api_key=api_key)
    model_chain = _mistral_model_chain()

    def _do_call(model_name: str):
        chat_response = client.chat.parse(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format=response_model,
            temperature=0,
        )
        parsed = chat_response.choices[0].message.parsed
        if parsed is not None:
            return parsed
        return response_model.model_validate_json(chat_response.choices[0].message.content)

    return _call_with_model_fallback(_do_call, model_chain, provider_label="mistral")


def call_llm(system_prompt: str, user_content: str, provider: str, response_model: type):
    """
    Dispatch a structured-output LLM call to the configured provider.

    response_model is required — this module has no default response schema
    of its own, since it has no knowledge of any particular node's data. Every
    caller (agent/domain_kpi.py, agent/reflector.py, ...) supplies its own
    Pydantic model to parse the response into.
    """
    if provider == "gemini":
        return call_gemini(system_prompt, user_content, response_model)
    elif provider == "mistral":
        return call_mistral(system_prompt, user_content, response_model)
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Expected 'gemini' or 'mistral'."
        )