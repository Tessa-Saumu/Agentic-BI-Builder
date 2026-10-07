"""
Tests for agent/graph.py and agent/sql_executor.py (run_sql_executor_retry).

Verifies:
  - Conditional routing after reflection (_route_after_reflection)
  - The topological one-retry-no-loop invariant on the compiled LangGraph
  - run_sql_executor_retry clear/keep/drop semantics
  - Full graph node invocation order (with and without retry) using mocked LLM calls
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.graph import _route_after_reflection, build_graph, time_node  # noqa: E402
from agent.models import (  # noqa: E402
    ColumnProfile,
    DataProfile,
    DomainHypothesis,
    DomainKPIResponse,
    KPISpec,
    ReflectionNote,
    ReflectionResponse,
)
from agent.sql_executor import run_sql_executor, run_sql_executor_retry  # noqa: E402
from agent.state import AgentState  # noqa: E402


def _make_kpi(
    sql_query: str,
    name: str = "Test KPI",
    chart_type: str = "card",
) -> KPISpec:
    return KPISpec(
        name=name,
        description="A test KPI.",
        sql_query=sql_query,
        chart_type=chart_type,
        reasoning="Test reasoning.",
    )


@pytest.fixture
def sample_csv(tmp_path):
    df = pd.DataFrame(
        {
            "Country": ["UK", "UK", "France", "Germany", "UK"],
            "Quantity": [5, 3, 2, 10, 2],
            "UnitPrice": [2.5, 3.0, 1.5, 4.0, 2.0],
            "InvoiceDate": [
                "2026-01-01",
                "2026-01-15",
                "2026-02-01",
                "2026-02-10",
                "2026-03-01",
            ],
        }
    )
    path = tmp_path / "sample.csv"
    df.to_csv(path, index=False)
    return str(path)


@pytest.fixture
def sample_profile(sample_csv) -> DataProfile:
    return DataProfile(
        source_path=sample_csv,
        row_count=5,
        column_count=4,
        columns={
            "Country": ColumnProfile(
                inferred_dtype="string", null_count=0, null_rate=0.0, distinct_count=3
            ),
            "Quantity": ColumnProfile(
                inferred_dtype="integer", null_count=0, null_rate=0.0, distinct_count=4
            ),
            "UnitPrice": ColumnProfile(
                inferred_dtype="float", null_count=0, null_rate=0.0, distinct_count=4
            ),
            "InvoiceDate": ColumnProfile(
                inferred_dtype="string", null_count=0, null_rate=0.0, distinct_count=5
            ),
        },
    )


def _five_valid_kpis() -> list[KPISpec]:
    return [
        _make_kpi("SELECT SUM(Quantity * UnitPrice) AS total_revenue FROM data", "Total Revenue", "card"),
        _make_kpi("SELECT SUM(Quantity) AS total_units FROM data", "Total Units", "card"),
        _make_kpi(
            "SELECT Country, SUM(Quantity * UnitPrice) AS revenue FROM data GROUP BY Country",
            "Revenue by Country",
            "barChart",
        ),
        _make_kpi(
            "SELECT strftime('%Y-%m', InvoiceDate) AS month, SUM(Quantity) AS qty FROM data GROUP BY month",
            "Monthly Quantity Trend",
            "lineChart",
        ),
        _make_kpi(
            "SELECT Country, COUNT(*) AS orders, AVG(UnitPrice) AS avg_price FROM data GROUP BY Country",
            "Country Summary",
            "table",
        ),
    ]


# ---------------------------------------------------------------------------
# Conditional edge routing
# ---------------------------------------------------------------------------

class TestRouteAfterReflection:
    def test_routes_to_pbir_compiler_when_kpis_to_retry_empty(self):
        state = AgentState(kpis_to_retry=[])
        assert _route_after_reflection(state) == "pbir_compiler"

    def test_routes_to_sql_executor_retry_when_kpis_to_retry_non_empty(self):
        state = AgentState(kpis_to_retry=["Total Revenue"])
        assert _route_after_reflection(state) == "sql_executor_retry"


# ---------------------------------------------------------------------------
# Topological one-retry-no-loop invariant
# ---------------------------------------------------------------------------

class TestGraphTopology:
    def test_compiled_graph_has_expected_nodes(self):
        graph_structure = build_graph().get_graph()
        expected = {
            "__start__",
            "profiler",
            "domain_kpi",
            "sql_executor",
            "reflector",
            "sql_executor_retry",
            "pbir_compiler",
            "__end__",
        }
        assert set(graph_structure.nodes.keys()) == expected

    def test_one_retry_no_loop_invariant_no_edge_back_to_reflector(self):
        graph_structure = build_graph().get_graph()
        edges = [(e.source, e.target) for e in graph_structure.edges]

        # sql_executor_retry must go ONLY to pbir_compiler — never back to
        # reflector, sql_executor, or itself.
        retry_outgoing = [target for source, target in edges if source == "sql_executor_retry"]
        assert retry_outgoing == ["pbir_compiler"]
        assert ("sql_executor_retry", "reflector") not in edges
        assert ("sql_executor_retry", "sql_executor") not in edges
        assert ("sql_executor_retry", "sql_executor_retry") not in edges

        # reflector's conditional edges must only target sql_executor_retry or pbir_compiler.
        reflector_outgoing = {target for source, target in edges if source == "reflector"}
        assert reflector_outgoing == {"sql_executor_retry", "pbir_compiler"}


# ---------------------------------------------------------------------------
# run_sql_executor_retry semantics
# ---------------------------------------------------------------------------

class TestRunSqlExecutorRetry:
    def test_noop_when_kpis_to_retry_is_empty(self, sample_csv, sample_profile):
        kpi = _make_kpi("SELECT SUM(Quantity) AS qty FROM data", "Total Units")
        state = AgentState(input_path=sample_csv, data_profile=sample_profile, kpi_specs=[kpi])
        state = run_sql_executor(state)

        result = run_sql_executor_retry(state)
        assert result.kpis_to_retry == []
        assert len(result.kpi_specs) == 1
        assert len(result.query_results) == 1

    def test_passing_retry_updates_query_result_and_clears_kpis_to_retry(
        self, sample_csv, sample_profile
    ):
        kpis = [
            _make_kpi("SELECT SUM(NonExistent) FROM data", "Broken KPI"),
            _make_kpi("SELECT SUM(Quantity) AS qty FROM data", "Good KPI"),
        ]
        state = AgentState(input_path=sample_csv, data_profile=sample_profile, kpi_specs=kpis)
        state = run_sql_executor(state)
        assert state.query_results[0].status == "fail"

        # Simulate reflector applying a valid fix and flagging for retry
        state.kpi_specs[0] = state.kpi_specs[0].model_copy(
            update={"sql_query": "SELECT SUM(Quantity * UnitPrice) AS rev FROM data"}
        )
        state.kpis_to_retry = ["Broken KPI"]

        result = run_sql_executor_retry(state)
        assert result.kpis_to_retry == []
        assert {k.name for k in result.kpi_specs} == {"Broken KPI", "Good KPI"}
        repaired_qr = next(qr for qr in result.query_results if qr.kpi_name == "Broken KPI")
        assert repaired_qr.status == "pass"
        assert repaired_qr.result_rows[0]["rev"] == pytest.approx(68.5)

    def test_failing_retry_drops_kpi_and_clears_kpis_to_retry(self, sample_csv, sample_profile):
        kpis = [
            _make_kpi("SELECT SUM(NonExistent) FROM data", "Unfixable KPI"),
            _make_kpi("SELECT SUM(Quantity) AS qty FROM data", "Good KPI"),
        ]
        state = AgentState(input_path=sample_csv, data_profile=sample_profile, kpi_specs=kpis)
        state = run_sql_executor(state)

        # Simulate reflector supplying a fix that still fails at execution time
        state.kpi_specs[0] = state.kpi_specs[0].model_copy(
            update={"sql_query": "SELECT SUM(StillNonExistent) FROM data"}
        )
        state.kpis_to_retry = ["Unfixable KPI"]

        result = run_sql_executor_retry(state)
        assert result.kpis_to_retry == []
        assert [k.name for k in result.kpi_specs] == ["Good KPI"]
        assert [qr.kpi_name for qr in result.query_results] == ["Good KPI"]


# ---------------------------------------------------------------------------
# Full graph orchestration & node timing order (no network)
# ---------------------------------------------------------------------------

class TestGraphExecutionOrder:
    def test_node_invocation_order_without_retry(self, sample_csv, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        domain_response = DomainKPIResponse(
            domain_hypothesis=DomainHypothesis(
                domain="retail", confidence=0.95, reasoning="Invoice columns."
            ),
            kpi_specs=_five_valid_kpis(),
        )
        reflection_response = ReflectionResponse(notes=[])

        graph = build_graph(dataset_name="sample")
        initial_state = AgentState(
            input_path=sample_csv,
            output_path=str(tmp_path / "output_report"),
        )

        with patch("agent.domain_kpi.call_llm", return_value=domain_response) as mock_domain, patch(
            "agent.reflector._call_reflection_llm", return_value=reflection_response
        ) as mock_reflect:
            raw_result = graph.invoke(initial_state)

        final_state = AgentState(**raw_result)
        assert mock_domain.call_count == 1
        assert mock_reflect.call_count == 1
        assert list(final_state.node_timings.keys()) == [
            "profiler",
            "domain_kpi",
            "sql_executor",
            "reflector",
            "pbir_compiler",
        ]
        assert final_state.errors == []
        assert final_state.pbir_project is not None

    def test_node_invocation_order_with_retry_calls_reflector_only_once(
        self, sample_csv, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        kpis = _five_valid_kpis()
        domain_response = DomainKPIResponse(
            domain_hypothesis=DomainHypothesis(
                domain="retail", confidence=0.95, reasoning="Invoice columns."
            ),
            kpi_specs=kpis,
        )
        reflection_response = ReflectionResponse(
            notes=[
                ReflectionNote(
                    kpi_name="Total Units",
                    issue_type="wrong_aggregation",
                    description="Should filter positive quantities.",
                    fix_instruction="Add WHERE Quantity > 0.",
                    fixed_sql_query="SELECT SUM(Quantity) AS total_units FROM data WHERE Quantity > 0",
                )
            ]
        )

        graph = build_graph(dataset_name="sample_retry")
        initial_state = AgentState(
            input_path=sample_csv,
            output_path=str(tmp_path / "output_report_retry"),
        )

        with patch("agent.domain_kpi.call_llm", return_value=domain_response) as mock_domain, patch(
            "agent.reflector._call_reflection_llm", return_value=reflection_response
        ) as mock_reflect:
            raw_result = graph.invoke(initial_state)

        final_state = AgentState(**raw_result)
        assert mock_domain.call_count == 1
        # One-retry-no-loop invariant: reflector is never re-invoked after retry.
        assert mock_reflect.call_count == 1
        assert list(final_state.node_timings.keys()) == [
            "profiler",
            "domain_kpi",
            "sql_executor",
            "reflector",
            "sql_executor_retry",
            "pbir_compiler",
        ]
        assert final_state.kpis_to_retry == []
        assert final_state.errors == []
        assert final_state.pbir_project is not None

    def test_time_node_records_elapsed_seconds(self):
        def dummy_node(state: AgentState) -> AgentState:
            return state

        wrapped = time_node("dummy", dummy_node)
        state = wrapped(AgentState())
        assert "dummy" in state.node_timings
        assert state.node_timings["dummy"] >= 0.0
