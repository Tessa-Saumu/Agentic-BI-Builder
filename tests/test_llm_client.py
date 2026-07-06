"""
Tests for agent/llm_client.py — the shared LLM-calling infrastructure used
by every LLM-powered node (Domain/KPI, Reflector, ...).

Covers: transient-error detection, retry-with-backoff + same-provider model
fallback, model chain construction from GEMINI_MODEL/GEMINI_MODEL_FALLBACK
and MISTRAL_MODEL/MISTRAL_MODEL_FALLBACK env vars, and provider dispatch.
time.sleep is monkeypatched out throughout so these run instantly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent.llm_client as llm_client  # noqa: E402
from agent.llm_client import (  # noqa: E402
    _call_with_model_fallback,
    _gemini_model_chain,
    _is_transient_error,
    _mistral_model_chain,
    call_llm,
    MAX_RETRIES_PER_MODEL,
)


# ---------------------------------------------------------------------------
# Transient error detection
# ---------------------------------------------------------------------------

class TestIsTransientError:
    def test_detects_typed_status_code_attribute(self):
        class FakeServerError(Exception):
            code = 503

        assert _is_transient_error(FakeServerError("unavailable"))

    def test_detects_typed_status_code_attribute_alt_name(self):
        class FakeHTTPError(Exception):
            status_code = 429

        assert _is_transient_error(FakeHTTPError("rate limited"))

    def test_detects_string_markers_when_no_typed_code(self):
        assert _is_transient_error(Exception("503 UNAVAILABLE high demand"))
        assert _is_transient_error(Exception("429 rate limit exceeded"))
        assert _is_transient_error(Exception("the model is currently overloaded"))
        assert _is_transient_error(Exception("RESOURCE_EXHAUSTED"))

    def test_rejects_non_transient_errors(self):
        assert not _is_transient_error(Exception("400 invalid request"))
        assert not _is_transient_error(Exception("invalid api key"))
        assert not _is_transient_error(Exception("permission denied"))

    def test_typed_code_takes_precedence_and_400_is_not_transient(self):
        class FakeClientError(Exception):
            code = 400

        assert not _is_transient_error(FakeClientError("bad request"))


# ---------------------------------------------------------------------------
# Retry-with-backoff + model fallback
# ---------------------------------------------------------------------------

class TestCallWithModelFallback:
    def test_succeeds_immediately_with_no_retry_needed(self):
        result = _call_with_model_fallback(lambda model: f"ok:{model}", ["model-a", "model-b"], "test")
        assert result == "ok:model-a"

    def test_succeeds_after_transient_retry_without_falling_back(self, monkeypatch):
        monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)

        call_log = []

        def flaky(model_name):
            call_log.append(model_name)
            if len(call_log) < 2:
                raise Exception("503 UNAVAILABLE")
            return "ok"

        result = _call_with_model_fallback(flaky, ["model-a", "model-b"], "test")
        assert result == "ok"
        assert call_log == ["model-a", "model-a"]  # never reached model-b

    def test_falls_back_to_next_model_after_exhausting_retries(self, monkeypatch):
        monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)

        call_log = []

        def fails_only_on_model_a(model_name):
            call_log.append(model_name)
            if model_name == "model-a":
                raise Exception("503 UNAVAILABLE")
            return "ok from b"

        result = _call_with_model_fallback(fails_only_on_model_a, ["model-a", "model-b"], "test")
        assert result == "ok from b"
        assert call_log.count("model-a") == MAX_RETRIES_PER_MODEL
        assert call_log[-1] == "model-b"

    def test_non_transient_error_raises_immediately_without_retry_or_fallback(self, monkeypatch):
        monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)

        call_log = []

        def bad_request(model_name):
            call_log.append(model_name)
            raise Exception("400 invalid request format")

        with pytest.raises(Exception, match="invalid request"):
            _call_with_model_fallback(bad_request, ["model-a", "model-b"], "test")

        assert call_log == ["model-a"]  # no retries, no fallback attempted

    def test_all_models_exhausted_raises_clear_provider_switch_suggestion(self, monkeypatch):
        monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)

        def always_fails(model_name):
            raise Exception("503 UNAVAILABLE")

        with pytest.raises(RuntimeError) as exc_info:
            _call_with_model_fallback(always_fails, ["model-a", "model-b"], "gemini")

        message = str(exc_info.value)
        assert "gemini" in message
        assert "mistral" in message.lower()
        assert "LLM_PROVIDER" in message

    def test_single_model_chain_exhausts_without_fallback_attempt(self, monkeypatch):
        # If only one model is configured (primary == fallback, so the chain
        # collapses to length 1 — see TestModelChainConstruction), exhausting
        # its retries should raise directly, not silently succeed.
        monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)

        def always_fails(model_name):
            raise Exception("503 UNAVAILABLE")

        with pytest.raises(RuntimeError):
            _call_with_model_fallback(always_fails, ["only-model"], "test")


# ---------------------------------------------------------------------------
# Model chain construction from env vars
# ---------------------------------------------------------------------------

class TestModelChainConstruction:
    def test_gemini_chain_uses_env_vars_when_set(self, monkeypatch):
        monkeypatch.setenv("GEMINI_MODEL", "gemini-custom-primary")
        monkeypatch.setenv("GEMINI_MODEL_FALLBACK", "gemini-custom-fallback")
        assert _gemini_model_chain() == ["gemini-custom-primary", "gemini-custom-fallback"]

    def test_gemini_chain_falls_back_to_defaults_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        monkeypatch.delenv("GEMINI_MODEL_FALLBACK", raising=False)
        chain = _gemini_model_chain()
        assert len(chain) == 2
        assert chain[0] != chain[1]

    def test_gemini_chain_collapses_to_one_model_if_primary_equals_fallback(self, monkeypatch):
        monkeypatch.setenv("GEMINI_MODEL", "same-model")
        monkeypatch.setenv("GEMINI_MODEL_FALLBACK", "same-model")
        assert _gemini_model_chain() == ["same-model"]

    def test_mistral_chain_uses_env_vars_when_set(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_MODEL", "mistral-custom-primary")
        monkeypatch.setenv("MISTRAL_MODEL_FALLBACK", "mistral-custom-fallback")
        assert _mistral_model_chain() == ["mistral-custom-primary", "mistral-custom-fallback"]

    def test_mistral_chain_falls_back_to_defaults_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_MODEL", raising=False)
        monkeypatch.delenv("MISTRAL_MODEL_FALLBACK", raising=False)
        chain = _mistral_model_chain()
        assert len(chain) == 2
        assert chain[0] != chain[1]


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------

class TestCallLlmDispatch:
    def test_unsupported_provider_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
            call_llm("system", "user", "openai", response_model=dict)

    def test_response_model_is_required_not_defaulted(self):
        # call_llm has no default response_model (unlike the old
        # domain_kpi._call_llm) — this module has no knowledge of any
        # specific node's schema, so omitting response_model is a TypeError,
        # not a silent fallback to some node-specific default.
        with pytest.raises(TypeError):
            call_llm("system", "user", "gemini")


class TestMistralImportCompatibility:
    def test_mistral_client_class_is_importable(self):
        # Regression test: mistralai v2.0.0 moved the Mistral client class
        # from `mistralai.Mistral` to `mistralai.client.Mistral`. This must
        # resolve regardless of which major version is installed, matching
        # the fallback logic in call_mistral.
        try:
            from mistralai import Mistral
        except ImportError:
            from mistralai.client import Mistral
        assert Mistral is not None
        # Must be constructible with just an api_key kwarg (no network call).
        client = Mistral(api_key="test-key-not-used")
        assert client is not None