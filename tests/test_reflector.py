"""
Tests for agent/reflector.py.

The LLM call (_call_reflection_llm) is mocked throughout — these tests
verify the deterministic orchestration: prompt assembly, the one-retry-only
cycle, correct dropping of unfixable KPIs, and logging. They do not make
real API calls.
"""
import json
import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.models import (  # noqa: E402
    ColumnProfile,
    DataProfile,
    KPISpec,
    ReflectionNote,
    ReflectionResponse,
)
from agent.state import AgentState  # noqa: E402
from agent.sql_executor import run_sql_executor  # noqa: E402
from agent.reflector import run_reflector, _build_reflection_prompt  # noqa: E402


def _make_kpi(sql_query: str, name: str = "Test KPI") -> KPISpec:
    return KPISpec(
        name=name, description="d", sql_query=sql_query, chart_type="card", reasoning="r"
    )


@pytest.fixture
def retail_csv(tmp_path):
    df = pd.DataFrame(
        {
            "Country": ["UK", "UK", "France", "Germany", "UK"],
            "Quantity": [5, 3, None, 10, 2],
            "UnitPrice": [2.5, 3.0, 1.5, 4.0, 2.0],
        }
    )
    path = tmp_path / "retail.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def retail_profile() -> DataProfile:
    return DataProfile(
        source_path="retail.csv",
        row_count=5,
        column_count=3,
        columns={
            "Country": ColumnProfile(inferred_dtype="string", null_count=0, null_rate=0.0, distinct_count=3),
            "Quantity": ColumnProfile(inferred_dtype="integer", null_count=1, null_rate=0.2, distinct_count=4),
            "UnitPrice": ColumnProfile(inferred_dtype="float", null_count=0, null_rate=0.0, distinct_count=4),
        },
    )


@pytest.fixture
def executed_state(retail_csv, retail_profile):
    """A state that has already been through the Profiler + SQL Executor."""
    kpis = [
        _make_kpi("SELECT SUM(Quantity * UnitPrice) AS revenue FROM data", "Total Revenue"),
        _make_kpi("SELECT Country, SUM(Quantity) AS total_qty FROM data GROUP BY Country", "Qty By Country"),
    ]
    state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=kpis)
    return run_sql_executor(state)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

class TestPromptConstruction:
    def test_includes_kpi_sql_and_execution_results(self, executed_state):
        prompt = _build_reflection_prompt(
            executed_state.data_profile, executed_state.kpi_specs, executed_state.query_results
        )
        assert "Total Revenue" in prompt
        assert "SELECT SUM(Quantity * UnitPrice)" in prompt
        assert "status: pass" in prompt

    def test_includes_error_message_for_failed_kpi(self, retail_profile):
        from agent.models import QueryResult

        kpi = _make_kpi("SELECT SUM(FakeCol) FROM data", "Broken")
        qr = QueryResult(
            kpi_name="Broken", sql_query=kpi.sql_query, status="fail",
            error_message="no such column: FakeCol",
        )
        prompt = _build_reflection_prompt(retail_profile, [kpi], [qr])
        assert "no such column: FakeCol" in prompt


# ---------------------------------------------------------------------------
# Node-level prerequisite checks
# ---------------------------------------------------------------------------

class TestPrerequisites:
    def test_missing_data_profile_records_error(self):
        state = AgentState()
        result = run_reflector(state)
        assert any("data_profile is None" in e for e in result.errors)

    def test_missing_kpi_specs_records_error(self, retail_profile):
        state = AgentState(data_profile=retail_profile)
        result = run_reflector(state)
        assert any("kpi_specs is empty" in e for e in result.errors)

    def test_missing_query_results_records_error(self, retail_profile):
        kpi = _make_kpi("SELECT 1", "x")
        state = AgentState(data_profile=retail_profile, kpi_specs=[kpi])
        result = run_reflector(state)
        assert any("query_results is empty" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Core reflection + retry orchestration (LLM mocked)
# ---------------------------------------------------------------------------

class TestRunReflector:
    def test_no_issues_found_is_a_valid_clean_pass_through(self, executed_state, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        empty_response = ReflectionResponse(notes=[])
        with patch("agent.reflector._call_reflection_llm", return_value=empty_response):
            result = run_reflector(executed_state, dataset_name="clean_run")

        assert result.reflection_notes == []
        # Nothing should have been dropped or altered.
        assert len(result.kpi_specs) == 2
        assert len(result.query_results) == 2

    def test_flagged_kpi_with_fix_is_retried_and_only_that_kpi(self, executed_state, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        response = ReflectionResponse(notes=[
            ReflectionNote(
                kpi_name="Qty By Country",
                issue_type="null_heavy",
                description="France total_qty is NULL.",
                fix_instruction="Use COALESCE.",
                fixed_sql_query="SELECT Country, SUM(COALESCE(Quantity, 0)) AS total_qty FROM data GROUP BY Country",
            )
        ])
        with patch("agent.reflector._call_reflection_llm", return_value=response) as mock_call:
            result = run_reflector(executed_state, dataset_name="fix_run")

        # Only one LLM call total — the retry itself is deterministic SQL
        # execution, not a second LLM round-trip.
        assert mock_call.call_count == 1

        assert len(result.kpi_specs) == 2  # nothing dropped
        fixed_kpi = next(k for k in result.kpi_specs if k.name == "Qty By Country")
        assert "COALESCE" in fixed_kpi.sql_query

        fixed_result = next(qr for qr in result.query_results if qr.kpi_name == "Qty By Country")
        assert fixed_result.status == "pass"
        france_row = next(r for r in fixed_result.result_rows if r["Country"] == "France")
        assert france_row["total_qty"] == 0  # no longer None after the fix

        # The untouched KPI's result must be unchanged.
        untouched = next(qr for qr in result.query_results if qr.kpi_name == "Total Revenue")
        assert untouched.result_rows == [{"revenue": 65.5}]

    def test_kpi_dropped_when_retry_still_fails(self, retail_csv, retail_profile, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        kpis = [
            _make_kpi("SELECT SUM(FakeCol) FROM data", "Broken"),
            _make_kpi("SELECT Country FROM data", "Good"),
        ]
        state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=kpis)
        state = run_sql_executor(state)

        response = ReflectionResponse(notes=[
            ReflectionNote(
                kpi_name="Broken", issue_type="sql_error", description="bad column",
                fix_instruction="try again", fixed_sql_query="SELECT SUM(StillFakeCol) FROM data",
            )
        ])
        with patch("agent.reflector._call_reflection_llm", return_value=response):
            result = run_reflector(state, dataset_name="drop_run")

        remaining_names = {k.name for k in result.kpi_specs}
        assert remaining_names == {"Good"}
        assert {qr.kpi_name for qr in result.query_results} == {"Good"}
        # After the retry cycle, every KPI still present must have passed.
        assert all(qr.status == "pass" for qr in result.query_results)

    def test_kpi_dropped_when_no_fix_offered(self, executed_state, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        response = ReflectionResponse(notes=[
            ReflectionNote(
                kpi_name="Qty By Country",
                issue_type="null_heavy",
                description="Genuinely unfixable — data is null for this dimension.",
                fix_instruction="No query rewrite would help; the source data lacks this value.",
                fixed_sql_query=None,
            )
        ])
        with patch("agent.reflector._call_reflection_llm", return_value=response):
            result = run_reflector(executed_state, dataset_name="unfixable_run")

        remaining_names = {k.name for k in result.kpi_specs}
        assert remaining_names == {"Total Revenue"}
        assert {qr.kpi_name for qr in result.query_results} == {"Total Revenue"}

    def test_llm_exception_records_error_without_raising(self, executed_state):
        with patch("agent.reflector._call_reflection_llm", side_effect=RuntimeError("API down")):
            result = run_reflector(executed_state)  # must not raise

        assert any("API down" in e for e in result.errors)
        # Original state should be untouched since reflection never completed.
        assert len(result.kpi_specs) == 2


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class TestReflectionLogging:
    def test_log_file_written_when_notes_exist(self, executed_state, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        response = ReflectionResponse(notes=[
            ReflectionNote(
                kpi_name="Qty By Country", issue_type="null_heavy",
                description="d", fix_instruction="f",
                fixed_sql_query="SELECT Country, SUM(COALESCE(Quantity, 0)) AS total_qty FROM data GROUP BY Country",
            )
        ])
        with patch("agent.reflector._call_reflection_llm", return_value=response):
            run_reflector(executed_state, dataset_name="log_test")

        log_path = tmp_path / "data" / "profiles" / "log_test_reflection.json"
        assert log_path.exists()
        with open(log_path) as f:
            payload = json.load(f)
        assert payload["dataset"] == "log_test"
        assert len(payload["notes"]) == 1

    def test_no_log_file_written_when_no_notes(self, executed_state, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        empty_response = ReflectionResponse(notes=[])
        with patch("agent.reflector._call_reflection_llm", return_value=empty_response):
            run_reflector(executed_state, dataset_name="no_notes_test")

        log_path = tmp_path / "data" / "profiles" / "no_notes_test_reflection.json"
        assert not log_path.exists()