"""
SQL Executor node — deterministic, zero LLM calls.

Loads the input dataset (CSV or the correct SQLite table, matching how the
Profiler loaded it) into an in-memory SQLite database as table "data" —
matching the contract the Domain/KPI node's prompt already assumes — then
executes every KPISpec.sql_query against it, capturing a QueryResult per KPI.

Never raises for an individual query failure: a syntax error, a reference to
a column that doesn't exist at runtime, or any other sqlite3.Error is
captured as a QueryResult with status="fail" and the query moves on. This
mirrors run_domain_kpi's error-containment pattern so a single bad KPI never
crashes the pipeline.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from agent.models import DataProfile, KPISpec, QueryResult, MAX_RESULT_ROWS_STORED
from agent.profiler import _load_file
from agent.state import AgentState


def _load_dataframe_for_execution(profile: DataProfile, input_path: str) -> pd.DataFrame:
    """
    Load the same data the Profiler profiled, using the same loading logic.

    For SQLite inputs, profile.source_table records which table was actually
    profiled (e.g. "Invoice" for chinook) — that's the table that must be
    loaded here too, not just "the sqlite file" generically, or the executed
    queries would run against different data than the KPIs were designed for.
    For CSV inputs, source_table is None and _load_file loads the CSV as-is.
    """
    df, _ = _load_file(input_path, table_name=profile.source_table)
    return df


def _build_in_memory_db(df: pd.DataFrame) -> sqlite3.Connection:
    """
    Load a DataFrame into a fresh in-memory SQLite database as table "data".

    Table name "data" matches the contract assumed throughout domain_kpi.py's
    system prompt (SQLITE_CONSTRAINTS: "always write FROM data").
    """
    conn = sqlite3.connect(":memory:")
    df.to_sql("data", conn, index=False, if_exists="replace")
    return conn


def _execute_single_kpi(conn: sqlite3.Connection, kpi_name: str, sql_query: str) -> QueryResult:
    """
    Execute one SQL query and capture the outcome as a QueryResult.

    An empty result set (zero rows) is a "pass" — zero rows is a valid
    outcome, not an error. Only an actual execution failure (sqlite3.Error)
    is a "fail".
    """
    try:
        cursor = conn.execute(sql_query)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []

        result_rows = [dict(zip(columns, row)) for row in rows[:MAX_RESULT_ROWS_STORED]]

        return QueryResult(
            kpi_name=kpi_name,
            sql_query=sql_query,
            status="pass",
            row_count=len(rows),
            columns=columns,
            result_rows=result_rows,
            error_message=None,
        )
    except sqlite3.Error as exc:
        return QueryResult(
            kpi_name=kpi_name,
            sql_query=sql_query,
            status="fail",
            row_count=0,
            columns=[],
            result_rows=[],
            error_message=str(exc),
        )


def run_sql_executor(state: AgentState) -> AgentState:
    """
    LangGraph node: execute every KPISpec.sql_query against real data.

    Populates state.query_results with one QueryResult per KPI in
    state.kpi_specs, in the same order. Appends to state.errors only for
    pipeline-level failures (e.g. the data can't be loaded at all) — an
    individual KPI's SQL failure is captured in its QueryResult, not raised.
    """
    if state.data_profile is None:
        state.errors.append("run_sql_executor: state.data_profile is None; run the Profiler node first.")
        return state

    if not state.kpi_specs:
        state.errors.append("run_sql_executor: state.kpi_specs is empty; run the Domain/KPI node first.")
        return state

    try:
        df = _load_dataframe_for_execution(state.data_profile, state.input_path)
    except Exception as exc:
        state.errors.append(f"run_sql_executor: failed to load data for execution: {exc}")
        return state

    try:
        conn = _build_in_memory_db(df)
    except Exception as exc:
        state.errors.append(f"run_sql_executor: failed to build in-memory SQLite DB: {exc}")
        return state

    try:
        results = [
            _execute_single_kpi(conn, kpi.name, kpi.sql_query)
            for kpi in state.kpi_specs
        ]
    finally:
        conn.close()

    state.query_results = results
    return state


def rerun_single_kpi(state: AgentState, kpi_name: str, new_sql_query: str) -> QueryResult:
    """
    Re-execute one KPI's (possibly Reflector-fixed) SQL and return its new
    QueryResult, without re-running the other KPIs. Used by the Reflector's
    one-retry-per-flagged-KPI cycle — this is the deterministic execution
    half of that retry; it does not update state.query_results itself,
    leaving that to the caller so the caller can decide whether to keep or
    drop the KPI based on the retry's outcome.

    Raises the same exceptions as run_sql_executor's setup steps if the
    underlying data can't be (re)loaded — this is expected to be called only
    after run_sql_executor has already succeeded once in this state's
    lifecycle, so a failure here indicates a real environment problem, not a
    per-KPI SQL issue (which is still captured in the returned QueryResult).
    """
    df = _load_dataframe_for_execution(state.data_profile, state.input_path)
    conn = _build_in_memory_db(df)
    try:
        return _execute_single_kpi(conn, kpi_name, new_sql_query)
    finally:
        conn.close()