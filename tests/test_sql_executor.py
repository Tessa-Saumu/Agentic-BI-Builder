"""
Tests for agent/sql_executor.py.

Covers the acceptance criterion "SQL Executor correctly captures errors
without crashing the pipeline" plus the specific cases called out in the
issue: a valid query, a syntax-error query, and a query on an empty result
set. Also covers the SQLite source_table routing that mattered for chinook
in the prior Domain/KPI issue.
"""
import os
import sqlite3
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.models import ColumnProfile, DataProfile, KPISpec  # noqa: E402
from agent.state import AgentState  # noqa: E402
from agent.sql_executor import (  # noqa: E402
    run_sql_executor,
    rerun_single_kpi,
    _execute_single_kpi,
    _build_in_memory_db,
)


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
def chinook_sqlite(tmp_path):
    path = tmp_path / "chinook.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE Invoice (InvoiceId INTEGER, CustomerId INTEGER, Total REAL, BillingCountry TEXT)")
    conn.execute("INSERT INTO Invoice VALUES (1, 10, 15.5, 'USA'), (2, 11, 9.99, 'Canada')")
    conn.execute("CREATE TABLE Track (TrackId INTEGER, Name TEXT)")
    conn.execute("INSERT INTO Track VALUES (1, 'Some Song')")
    conn.commit()
    conn.close()
    return str(path)


@pytest.fixture
def chinook_profile() -> DataProfile:
    return DataProfile(
        source_path="chinook.sqlite",
        source_table="Invoice",
        row_count=2,
        column_count=4,
        columns={
            "InvoiceId": ColumnProfile(inferred_dtype="integer", null_count=0, null_rate=0.0, distinct_count=2),
            "CustomerId": ColumnProfile(inferred_dtype="integer", null_count=0, null_rate=0.0, distinct_count=2),
            "Total": ColumnProfile(inferred_dtype="float", null_count=0, null_rate=0.0, distinct_count=2),
            "BillingCountry": ColumnProfile(inferred_dtype="string", null_count=0, null_rate=0.0, distinct_count=2),
        },
    )


# ---------------------------------------------------------------------------
# Required cases from the issue: valid query, syntax error, empty result set
# ---------------------------------------------------------------------------

class TestRunSqlExecutor:
    def test_valid_query_passes(self, retail_csv, retail_profile):
        kpi = _make_kpi("SELECT SUM(Quantity * UnitPrice) AS revenue FROM data", "Total Revenue")
        state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=[kpi])
        result = run_sql_executor(state)

        assert len(result.query_results) == 1
        qr = result.query_results[0]
        assert qr.status == "pass"
        assert qr.row_count == 1
        assert qr.columns == ["revenue"]
        assert qr.error_message is None
        assert result.errors == []

    def test_syntax_error_query_fails_without_crashing(self, retail_csv, retail_profile):
        kpi = _make_kpi("SELECT SUM(NotAColumn) FROM data", "Broken KPI")
        state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=[kpi])
        result = run_sql_executor(state)  # must not raise

        assert len(result.query_results) == 1
        qr = result.query_results[0]
        assert qr.status == "fail"
        assert qr.error_message is not None
        assert "NotAColumn" in qr.error_message
        # Pipeline-level errors are separate from per-KPI failures.
        assert result.errors == []

    def test_query_on_empty_result_set_is_a_pass_not_a_fail(self, retail_csv, retail_profile):
        # A WHERE clause that matches nothing is a valid outcome, not an error.
        kpi = _make_kpi("SELECT Country FROM data WHERE Country = 'Atlantis'", "No Match")
        state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=[kpi])
        result = run_sql_executor(state)

        qr = result.query_results[0]
        assert qr.status == "pass"
        assert qr.row_count == 0
        assert qr.result_rows == []

    def test_multiple_kpis_each_get_independent_results(self, retail_csv, retail_profile):
        kpis = [
            _make_kpi("SELECT SUM(Quantity * UnitPrice) AS revenue FROM data", "Good 1"),
            _make_kpi("SELECT SUM(FakeCol) FROM data", "Bad"),
            _make_kpi("SELECT Country, SUM(Quantity) AS qty FROM data GROUP BY Country", "Good 2"),
        ]
        state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=kpis)
        result = run_sql_executor(state)

        assert len(result.query_results) == 3
        statuses = {qr.kpi_name: qr.status for qr in result.query_results}
        assert statuses == {"Good 1": "pass", "Bad": "fail", "Good 2": "pass"}

    def test_result_rows_capped_at_max(self, retail_csv, retail_profile):
        from agent.models import MAX_RESULT_ROWS_STORED

        kpi = _make_kpi("SELECT * FROM data", "All Rows")
        state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=[kpi])
        result = run_sql_executor(state)

        qr = result.query_results[0]
        assert qr.row_count == 5  # true row count is preserved...
        assert len(qr.result_rows) <= MAX_RESULT_ROWS_STORED  # ...even though storage is capped

    def test_null_heavy_aggregation_result_is_visible_in_result_rows(self, retail_csv, retail_profile):
        # France's only Quantity value is null, so SUM(Quantity) for that
        # group should come back as None — this is exactly the kind of
        # signal the Reflector needs to see to flag "null_heavy".
        kpi = _make_kpi(
            "SELECT Country, SUM(Quantity) AS total_qty FROM data GROUP BY Country", "By Country"
        )
        state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=[kpi])
        result = run_sql_executor(state)

        qr = result.query_results[0]
        france_row = next(r for r in qr.result_rows if r["Country"] == "France")
        assert france_row["total_qty"] is None


# ---------------------------------------------------------------------------
# SQLite source_table routing (the chinook case)
# ---------------------------------------------------------------------------

class TestSourceTableRouting:
    def test_loads_only_the_profiled_table_not_other_tables_in_db(self, chinook_sqlite, chinook_profile):
        kpi = _make_kpi("SELECT SUM(Total) AS total_revenue FROM data", "Total Revenue")
        state = AgentState(input_path=chinook_sqlite, data_profile=chinook_profile, kpi_specs=[kpi])
        result = run_sql_executor(state)

        qr = result.query_results[0]
        assert qr.status == "pass"
        assert qr.result_rows[0]["total_revenue"] == pytest.approx(25.49)

    def test_columns_from_decoy_table_are_not_queryable(self, chinook_sqlite, chinook_profile):
        # Track.Name should not exist in the loaded "data" table — only
        # Invoice's columns should be present.
        kpi = _make_kpi("SELECT Name FROM data", "Should Fail")
        state = AgentState(input_path=chinook_sqlite, data_profile=chinook_profile, kpi_specs=[kpi])
        result = run_sql_executor(state)

        qr = result.query_results[0]
        assert qr.status == "fail"


# ---------------------------------------------------------------------------
# Pipeline-level error containment
# ---------------------------------------------------------------------------

class TestPipelineLevelErrors:
    def test_missing_data_profile_records_error_without_raising(self):
        state = AgentState()
        result = run_sql_executor(state)  # must not raise
        assert result.query_results == []
        assert any("data_profile is None" in e for e in result.errors)

    def test_missing_kpi_specs_records_error_without_raising(self, retail_profile):
        state = AgentState(data_profile=retail_profile)
        result = run_sql_executor(state)
        assert result.query_results == []
        assert any("kpi_specs is empty" in e for e in result.errors)

    def test_nonexistent_file_records_error_without_raising(self, retail_profile):
        kpi = _make_kpi("SELECT 1", "x")
        state = AgentState(
            input_path="/tmp/does_not_exist_xyz.csv", data_profile=retail_profile, kpi_specs=[kpi]
        )
        result = run_sql_executor(state)
        assert result.query_results == []
        assert any("failed to load data" in e for e in result.errors)


# ---------------------------------------------------------------------------
# rerun_single_kpi — used by the Reflector's one-retry cycle
# ---------------------------------------------------------------------------

class TestRerunSingleKpi:
    def test_rerun_executes_only_the_given_kpi(self, retail_csv, retail_profile):
        original_kpis = [
            _make_kpi("SELECT SUM(FakeCol) FROM data", "Broken"),
            _make_kpi("SELECT Country FROM data", "Untouched"),
        ]
        state = AgentState(input_path=retail_csv, data_profile=retail_profile, kpi_specs=original_kpis)
        state = run_sql_executor(state)
        assert state.query_results[0].status == "fail"

        fixed_result = rerun_single_kpi(
            state, kpi_name="Broken", new_sql_query="SELECT SUM(Quantity) AS total_qty FROM data"
        )
        assert fixed_result.status == "pass"
        assert fixed_result.kpi_name == "Broken"