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

Two node entry points:
  - run_sql_executor: the first pass, executes every KPI in state.kpi_specs.
  - run_sql_executor_retry: the retry pass, reached only via agent/graph.py's
    conditional edge out of "reflector" when state.kpis_to_retry is
    non-empty. Executes only the KPIs named there.
Both share the same private helpers (_load_dataframe_for_execution,
_build_in_memory_db, _execute_single_kpi) and the same rerun_single_kpi
primitive for single-KPI execution — neither entry point duplicates the
other's logic.
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

    print(f"[SQL Executor] Loading data from '{state.input_path}'" + (
        f" (table: {state.data_profile.source_table})" if state.data_profile.source_table else ""
    ) + "...")
    try:
        df = _load_dataframe_for_execution(state.data_profile, state.input_path)
    except Exception as exc:
        state.errors.append(f"run_sql_executor: failed to load data for execution: {exc}")
        return state

    print(f"[SQL Executor] Loaded {len(df)} rows. Building in-memory SQLite table...")
    try:
        conn = _build_in_memory_db(df)
    except Exception as exc:
        state.errors.append(f"run_sql_executor: failed to build in-memory SQLite DB: {exc}")
        return state

    print(f"[SQL Executor] Executing {len(state.kpi_specs)} KPI queries...")
    try:
        results = []
        for kpi in state.kpi_specs:
            qr = _execute_single_kpi(conn, kpi.name, kpi.sql_query)
            status_label = "PASS" if qr.status == "pass" else f"FAIL ({qr.error_message})"
            print(f"[SQL Executor]   {kpi.name}: {status_label}")
            results.append(qr)
    finally:
        conn.close()

    n_passed = sum(1 for r in results if r.status == "pass")
    print(f"[SQL Executor] Done: {n_passed}/{len(results)} queries passed.")

    state.query_results = results
    return state


def rerun_single_kpi(state: AgentState, kpi_name: str, new_sql_query: str) -> QueryResult:
    """
    Re-execute one KPI's (possibly Reflector-fixed) SQL and return its new
    QueryResult, without re-running the other KPIs. This is the
    single-KPI execution primitive used by run_sql_executor_retry below —
    it does not update state.query_results itself, leaving that to the
    caller so the caller can decide whether to keep or drop the KPI based
    on the retry's outcome.

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


def run_sql_executor_retry(state: AgentState) -> AgentState:
    """
    LangGraph node: the retry endpoint reached only via agent/graph.py's
    conditional edge out of "reflector" when state.kpis_to_retry is
    non-empty. Re-executes exactly the KPIs reflector.py flagged and already
    applied a fix to (their KPISpec.sql_query already holds the fixed
    query — this function doesn't take the fix text as an argument, it
    reads it off state.kpi_specs), using the same rerun_single_kpi
    primitive run_sql_executor's original single-KPI retry used.

    This node has no knowledge of reflector.py and does not import from it —
    it only reads state.kpis_to_retry, a plain list of names. That's what
    lets agent/graph.py own the retry-count policy (currently: exactly one
    pass, enforced by there being no edge back to "reflector" or to this
    node from pbir_compiler) instead of this file or reflector.py owning it.

    For each retried KPI:
      - if the retry now passes: state.query_results is updated with the
        new QueryResult, replacing the stale one from the original
        (pre-fix) execution.
      - if the retry still fails: the KPI is dropped from both
        state.kpi_specs and state.query_results — this is where "one
        retry only — then drop the KPI" is actually enforced, since this
        function only ever runs once per KPI name per pipeline invocation
        (kpis_to_retry is cleared at the end, and nothing downstream of
        this node can repopulate it).

    Always clears state.kpis_to_retry before returning, whether or not any
    KPI was actually retried, so the field never carries stale names into
    a later invocation of the graph.

    Appends to state.errors only for pipeline-level failures (the data
    can't be reloaded at all) — an individual KPI's retry failure is
    captured by dropping that KPI, not raised.
    """
    if not state.kpis_to_retry:
        # Nothing to do — agent/graph.py's conditional edge should not have
        # routed here in this case, but returning state unchanged rather
        # than raising keeps this function safe to call defensively.
        return state

    print(f"[SQL Executor Retry] Re-executing {len(state.kpis_to_retry)} flagged KPI(s)...")

    kpis_by_name = {kpi.name: kpi for kpi in state.kpi_specs}
    results_by_name = {qr.kpi_name: qr for qr in state.query_results}
    dropped_kpi_names: set[str] = set()

    for kpi_name in state.kpis_to_retry:
        kpi = kpis_by_name.get(kpi_name)
        if kpi is None:
            # Shouldn't happen — reflector.py only adds names that exist in
            # kpi_specs — but skip defensively rather than crash the run.
            continue

        try:
            retry_result = rerun_single_kpi(state, kpi_name, kpi.sql_query)
        except Exception as exc:
            state.errors.append(
                f"run_sql_executor_retry: retry execution failed for KPI '{kpi_name}': {exc}"
            )
            dropped_kpi_names.add(kpi_name)
            continue

        if retry_result.status == "fail":
            print(
                f"[SQL Executor Retry]   {kpi_name}: still FAIL after fix "
                f"({retry_result.error_message}) — dropping."
            )
            dropped_kpi_names.add(kpi_name)
        else:
            print(f"[SQL Executor Retry]   {kpi_name}: PASS — fix confirmed.")
            results_by_name[kpi_name] = retry_result

    state.kpi_specs = [kpi for name, kpi in kpis_by_name.items() if name not in dropped_kpi_names]
    state.query_results = [
        qr for name, qr in results_by_name.items() if name not in dropped_kpi_names
    ]
    state.kpis_to_retry = []

    print(
        f"[SQL Executor Retry] Done: {len(dropped_kpi_names)} KPI(s) dropped, "
        f"{len(state.kpi_specs)} KPI(s) remaining."
    )
    return state