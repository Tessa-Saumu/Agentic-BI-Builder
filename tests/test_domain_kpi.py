"""
Tests for agent/domain_kpi.py.

The actual LLM call (_call_llm) is mocked in all orchestration tests — these
tests verify the deterministic guarantees the acceptance criteria depend on:
metadata-only prompting, SQL column validation, and structured-output
constraints. They do not make real API calls and do not require API keys.
"""
import json
import os
import sys
from unittest.mock import patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.models import (  # noqa: E402
    ColumnProfile,
    DataProfile,
    DomainHypothesis,
    DomainKPIResponse,
    KPISpec,
)
from agent.state import AgentState  # noqa: E402
from agent.domain_kpi import (  # noqa: E402
    _profile_to_prompt_context,
    _validate_sql_columns,
    run_domain_kpi,
)


@pytest.fixture
def retail_profile() -> DataProfile:
    fixture_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "profiles", "online_retail_profile.json"
    )
    with open(fixture_path) as f:
        raw = json.load(f)
    return DataProfile(**raw)


def _make_kpi(sql_query: str, name: str = "Test KPI") -> KPISpec:
    return KPISpec(
        name=name,
        description="A test KPI.",
        sql_query=sql_query,
        chart_type="card",
        reasoning="Because it's a test.",
    )


def _make_response(kpi_specs=None, confidence: float = 0.85) -> DomainKPIResponse:
    if kpi_specs is None:
        kpi_specs = [
            _make_kpi("SELECT Country, SUM(Quantity * UnitPrice) AS revenue FROM data GROUP BY Country", f"KPI {i}")
            for i in range(5)
        ]
    return DomainKPIResponse(
        domain_hypothesis=DomainHypothesis(
            domain="e-commerce retail", confidence=confidence, reasoning="Invoice/Quantity/UnitPrice/Country pattern."
        ),
        kpi_specs=kpi_specs,
    )


# ---------------------------------------------------------------------------
# Prompt construction: must be metadata-only
# ---------------------------------------------------------------------------

class TestPromptContext:
    def test_excludes_sample_values(self, retail_profile):
        ctx = _profile_to_prompt_context(retail_profile)
        assert "WHITE HANGING HEART" not in ctx
        assert "536365" not in ctx

    def test_excludes_min_max_values(self, retail_profile):
        ctx = _profile_to_prompt_context(retail_profile)
        assert "-80995" not in ctx
        assert "38970" not in ctx

    def test_includes_column_metadata(self, retail_profile):
        ctx = _profile_to_prompt_context(retail_profile)
        assert "Country" in ctx
        assert "distinct_count: 38" in ctx
        assert "row_count: 541909" in ctx

    def test_adapts_to_missing_optional_field(self):
        # A profile with a source_table set (unlike the CSV fixture) should
        # still serialize cleanly — context builder must not hardcode "None".
        profile = DataProfile(
            source_path="db.sqlite",
            source_table="orders",
            row_count=10,
            column_count=1,
            columns={"id": ColumnProfile(inferred_dtype="integer", null_count=0, null_rate=0.0, distinct_count=10)},
        )
        ctx = _profile_to_prompt_context(profile)
        assert "orders" in ctx


# ---------------------------------------------------------------------------
# SQL column validation
# ---------------------------------------------------------------------------

class TestSQLColumnValidation:
    def test_valid_columns_pass(self, retail_profile):
        kpi = _make_kpi("SELECT Country, SUM(Quantity * UnitPrice) AS revenue FROM data GROUP BY Country")
        assert _validate_sql_columns([kpi], retail_profile) == []

    def test_hallucinated_column_is_flagged(self, retail_profile):
        kpi = _make_kpi("SELECT AVG(DiscountPercent) FROM data")
        violations = _validate_sql_columns([kpi], retail_profile)
        assert len(violations) == 1
        assert "DiscountPercent" in violations[0]

    def test_alias_is_not_flagged_as_unknown_column(self, retail_profile):
        kpi = _make_kpi("SELECT Country, SUM(Quantity) AS total_qty FROM data GROUP BY Country")
        assert _validate_sql_columns([kpi], retail_profile) == []

    def test_sql_keywords_not_flagged(self, retail_profile):
        kpi = _make_kpi(
            "SELECT Country, COUNT(DISTINCT InvoiceNo) FROM data "
            "WHERE Quantity > 0 GROUP BY Country ORDER BY Country ASC LIMIT 10"
        )
        assert _validate_sql_columns([kpi], retail_profile) == []

    def test_multiple_kpis_each_checked_independently(self, retail_profile):
        good = _make_kpi("SELECT Country FROM data", "Good")
        bad = _make_kpi("SELECT FakeColumn FROM data", "Bad")
        violations = _validate_sql_columns([good, bad], retail_profile)
        assert len(violations) == 1
        assert "Bad" in violations[0]

    def test_strftime_format_string_not_flagged_as_column(self, retail_profile):
        # Regression test: strftime('%Y-%m', InvoiceDate) contains letters
        # ('Y', 'm') inside a string literal that are format codes, not column
        # references. These must not be flagged as hallucinated columns.
        kpi = _make_kpi(
            "SELECT strftime('%Y-%m', InvoiceDate) AS invoice_month, "
            "SUM(Quantity * UnitPrice) AS monthly_revenue FROM data "
            "GROUP BY invoice_month ORDER BY invoice_month ASC"
        )
        assert _validate_sql_columns([kpi], retail_profile) == []

    def test_string_literal_with_fake_column_name_not_flagged(self, retail_profile):
        # A string literal's contents should never be tokenized as an
        # identifier at all, even if it happens to contain a plausible-looking
        # "column-like" word.
        kpi = _make_kpi("SELECT Country FROM data WHERE Country = 'NotARealColumn'")
        assert _validate_sql_columns([kpi], retail_profile) == []


# ---------------------------------------------------------------------------
# Pydantic model constraints
# ---------------------------------------------------------------------------

class TestModelConstraints:
    def test_chart_type_rejects_invalid_literal(self):
        with pytest.raises(ValidationError):
            KPISpec(name="x", description="y", sql_query="SELECT 1", chart_type="pieChart", reasoning="z")

    def test_chart_type_accepts_all_four_valid_literals(self):
        for ct in ("card", "barChart", "lineChart", "table"):
            KPISpec(name="x", description="y", sql_query="SELECT 1", chart_type=ct, reasoning="z")

    def test_confidence_out_of_bounds_rejected(self):
        with pytest.raises(ValidationError):
            DomainHypothesis(domain="retail", confidence=1.5, reasoning="z")

    def test_sql_query_must_be_select(self):
        with pytest.raises(ValidationError):
            KPISpec(name="x", description="y", sql_query="DROP TABLE data", chart_type="card", reasoning="z")

    def test_response_requires_exactly_five_kpis(self):
        kpi = _make_kpi("SELECT 1")
        dh = DomainHypothesis(domain="retail", confidence=0.9, reasoning="z")
        with pytest.raises(ValidationError):
            DomainKPIResponse(domain_hypothesis=dh, kpi_specs=[kpi, kpi])
        # exactly 5 is fine
        DomainKPIResponse(domain_hypothesis=dh, kpi_specs=[kpi] * 5)


# ---------------------------------------------------------------------------
# run_domain_kpi orchestration (LLM call mocked)
# ---------------------------------------------------------------------------

class TestMistralImportCompatibility:
    def test_mistral_client_class_is_importable(self):
        # Regression test: mistralai v2.0.0 moved the Mistral client class
        # from `mistralai.Mistral` to `mistralai.client.Mistral`. This must
        # resolve regardless of which major version is installed, matching
        # the fallback logic in _call_mistral.
        try:
            from mistralai import Mistral
        except ImportError:
            from mistralai.client import Mistral
        assert Mistral is not None
        # Must be constructible with just an api_key kwarg (no network call).
        client = Mistral(api_key="test-key-not-used")
        assert client is not None


class TestRunDomainKpi:
    def test_missing_profile_records_error(self):
        state = AgentState()
        result = run_domain_kpi(state)
        assert result.domain_hypothesis is None
        assert result.kpi_specs == []
        assert any("data_profile is None" in e for e in result.errors)

    def test_unsupported_provider_records_error(self, retail_profile, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        state = AgentState(data_profile=retail_profile)
        result = run_domain_kpi(state)
        assert result.domain_hypothesis is None
        assert any("Unsupported LLM_PROVIDER" in e for e in result.errors)

    def test_successful_call_populates_state(self, retail_profile, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        with patch("agent.domain_kpi._call_llm", return_value=_make_response()) as mock_call:
            state = AgentState(data_profile=retail_profile)
            result = run_domain_kpi(state)

        assert mock_call.call_count == 1
        assert result.domain_hypothesis is not None
        assert result.domain_hypothesis.domain == "e-commerce retail"
        assert len(result.kpi_specs) == 5
        assert result.errors == []

    def test_hallucinated_column_triggers_repair_then_succeeds(self, retail_profile, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mistral")
        bad_response = _make_response(
            kpi_specs=[_make_kpi("SELECT FakeColumn FROM data", f"KPI {i}") for i in range(5)]
        )
        good_response = _make_response()

        with patch("agent.domain_kpi._call_llm", side_effect=[bad_response, good_response]) as mock_call:
            state = AgentState(data_profile=retail_profile)
            result = run_domain_kpi(state)

        assert mock_call.call_count == 2
        assert result.domain_hypothesis is not None
        assert result.errors == []

    def test_hallucinated_column_persists_after_repair_records_error(self, retail_profile, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        bad_response = _make_response(
            kpi_specs=[_make_kpi("SELECT FakeColumn FROM data", f"KPI {i}") for i in range(5)]
        )

        with patch("agent.domain_kpi._call_llm", side_effect=[bad_response, bad_response]):
            state = AgentState(data_profile=retail_profile)
            result = run_domain_kpi(state)

        assert result.domain_hypothesis is None
        assert result.kpi_specs == []
        assert any("unresolved SQL column violations" in e for e in result.errors)

    def test_llm_exception_records_error_without_raising(self, retail_profile, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        with patch("agent.domain_kpi._call_llm", side_effect=RuntimeError("API timeout")):
            state = AgentState(data_profile=retail_profile)
            result = run_domain_kpi(state)  # must not raise

        assert result.domain_hypothesis is None
        assert any("API timeout" in e for e in result.errors)