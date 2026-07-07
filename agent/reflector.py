"""
Reflector node — LLM-powered (Gemini or Mistral, switchable via LLM_PROVIDER,
matching the Domain/KPI node's provider convention).

Reviews the full pipeline state so far (DataProfile + all KPISpecs + all
QueryResults) and produces a list of ReflectionNote objects flagging issues
that a purely mechanical SQL-execution check can't catch on its own:
  - null_heavy:        aggregation dominated by nulls, result not meaningful
  - wrong_aggregation:  the SQL technically runs but computes the wrong thing
  - implausible_result: a value that doesn't make sense for what it claims to measure
  - sql_error:          the query failed to execute (QueryResult.status == "fail")
  - other:              a genuine issue that doesn't fit the four categories above
                        (e.g. a duplicate KPI, a misleading chart_type choice) —
                        still reported and retried if fixable, rather than being
                        silently dropped by a closed taxonomy

The Reflector runs on every KPI, not just failed ones, because a KPI can
execute successfully and still be semantically wrong.

For each flagged KPI with a fixed_sql_query, the fix is re-executed exactly
once via sql_executor.rerun_single_kpi. If the retry still fails or is
re-flagged, the KPI is dropped from state.kpi_specs / state.query_results —
no second reflection pass, no further retries, to bound cost and latency.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from agent.domain_kpi import _profile_to_prompt_context
from agent.llm_client import call_llm
from agent.models import DataProfile, KPISpec, QueryResult, ReflectionNote, ReflectionResponse
from agent.sql_executor import rerun_single_kpi
from agent.state import AgentState

# Cap on how many result rows from each QueryResult are included in the
# reflection prompt. QueryResult already caps storage at MAX_RESULT_ROWS_STORED;
# this is a further cap specifically for prompt size, kept separate in case the
# two ever need to diverge.
MAX_ROWS_IN_PROMPT = 10

SYSTEM_PROMPT = """You are a senior BI analyst performing quality review on a \
set of proposed KPIs and their executed SQL results. You will be given:
1. The dataset's schema profile (metadata only).
2. The list of proposed KPIs, each with its SQL query and reasoning.
3. The actual result of running each KPI's SQL against the real data — \
status (pass/fail), row count, columns, and a sample of result rows (or an \
error message if the query failed).

For each KPI, decide whether there is a real issue. A KPI has an issue if \
any of the following apply:
- sql_error: the query failed to execute (status is "fail").
- null_heavy: the result is dominated by NULL values in a way that makes \
the KPI not meaningful (e.g. a SUM/AVG that came back NULL because the \
underlying column was mostly or entirely null for that group).
- wrong_aggregation: the query runs and returns rows, but the aggregation \
logic doesn't actually compute what the KPI's name/description claims (e.g. \
COUNT instead of SUM, or grouping by the wrong column).
- implausible_result: the query runs and returns a value that doesn't make \
sense for what it claims to measure (e.g. a negative total revenue with no \
explanation, an average that is wildly outside the plausible range implied \
by the row count).
- other: a genuine, real issue that doesn't fit any of the four categories \
above (e.g. two KPIs that measure essentially the same thing, or a \
chart_type that is a poor fit for what the query returns). Only use "other" \
for issues you are confident are real problems — it is not a catch-all for \
minor stylistic preferences.

Do NOT flag a KPI just because you would have written the SQL differently \
if it's already correct and meaningful. Do NOT flag a KPI solely because a \
result value looks large — only flag it if it's actually implausible given \
the data described in the profile.

For every flagged KPI, you must provide fixed_sql_query: a complete, valid, \
standalone SQLite SELECT statement that corrects the issue. Only propose a \
fix if you are confident it addresses the specific issue you identified. If \
the issue is something a query rewrite genuinely cannot fix (e.g. the \
underlying data is genuinely, unavoidably null-heavy for that dimension), \
leave fixed_sql_query as null — such KPIs will be dropped rather than \
retried, since retrying with no fix would just fail again.

If a KPI has no issue, do not include it in your response at all — it is \
correct as-is. An empty notes list is a valid, good outcome and means every \
KPI passed review.

Respond only via the structured schema provided. Do not include any text \
outside the structured response.
"""


def _query_result_to_prompt_context(qr: QueryResult) -> str:
    sample = qr.result_rows[:MAX_ROWS_IN_PROMPT]
    lines = [
        f"  status: {qr.status}",
        f"  row_count: {qr.row_count}",
        f"  columns: {qr.columns}",
    ]
    if qr.status == "fail":
        lines.append(f"  error_message: {qr.error_message}")
    else:
        lines.append(f"  sample_rows (up to {MAX_ROWS_IN_PROMPT}): {sample}")
    return "\n".join(lines)


def _build_reflection_prompt(
    profile: DataProfile, kpi_specs: list[KPISpec], query_results: list[QueryResult]
) -> str:
    profile_context = _profile_to_prompt_context(profile)

    results_by_name = {qr.kpi_name: qr for qr in query_results}

    kpi_blocks = []
    for kpi in kpi_specs:
        qr = results_by_name.get(kpi.name)
        block = [
            f"KPI: {kpi.name}",
            f"  description: {kpi.description}",
            f"  chart_type: {kpi.chart_type}",
            f"  sql_query: {kpi.sql_query}",
            f"  reasoning: {kpi.reasoning}",
        ]
        if qr is not None:
            block.append("  execution result:")
            block.append(_query_result_to_prompt_context(qr))
        else:
            block.append("  execution result: NOT EXECUTED (no matching QueryResult found)")
        kpi_blocks.append("\n".join(block))

    return (
        f"Dataset profile:\n\n{profile_context}\n\n"
        f"KPIs and their execution results:\n\n" + "\n\n".join(kpi_blocks) +
        "\n\nReview each KPI and return any ReflectionNotes for genuine issues."
    )


def _call_reflection_llm(system_prompt: str, user_content: str, provider: str) -> ReflectionResponse:
    """
    Reuses agent/llm_client.py's provider-dispatch call_llm — the same
    shared Gemini/Mistral calling logic (including model fallback and
    retry-with-backoff) that agent/domain_kpi.py uses, just parsed into
    ReflectionResponse instead of DomainKPIResponse.
    """
    return call_llm(system_prompt, user_content, provider, response_model=ReflectionResponse)


def _log_reflection(dataset_name: str, notes: list[ReflectionNote], output_dir: str = "data/profiles") -> str | None:
    """
    Log reflection activity to console always, and to a JSON file when there
    are any notes to report. Returns the file path written, or None if no
    notes were generated (nothing to log to a file).
    """
    if not notes:
        print(f"[Reflector] {dataset_name}: no issues found across {len(notes)} KPIs — all clear.")
        return None

    print(f"[Reflector] {dataset_name}: {len(notes)} issue(s) found:")
    for note in notes:
        print(f"  - [{note.issue_type}] {note.kpi_name}: {note.description}")
        print(f"    fix: {note.fix_instruction}")

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{dataset_name}_reflection.json")
    payload = {
        "dataset": dataset_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "notes": [n.model_dump() for n in notes],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[Reflector] Reflection log written to {out_path}")
    return out_path


def run_reflector(state: AgentState, dataset_name: str = "dataset") -> AgentState:
    """
    LangGraph node: review all KPIs + their QueryResults, flag issues, and
    run one retry cycle for flagged KPIs with a concrete fix.

    Populates state.reflection_notes with whatever the LLM flagged (after
    retries are resolved, notes reflect the final judgment — a KPI that was
    successfully fixed is not re-flagged; state.reflection_notes documents
    what was found and fixed/dropped, for audit purposes).

    KPIs whose one retry still fails (or has no fixed_sql_query offered) are
    removed from both state.kpi_specs and state.query_results — per the
    issue's "one retry only — then drop the KPI" instruction.

    Never raises: on any node-level failure (missing prerequisites, LLM call
    failure), appends to state.errors and returns state unchanged for the
    parts that couldn't be reflected on.
    """
    if state.data_profile is None:
        state.errors.append("run_reflector: state.data_profile is None; run the Profiler node first.")
        return state
    if not state.kpi_specs:
        state.errors.append("run_reflector: state.kpi_specs is empty; run the Domain/KPI node first.")
        return state
    if not state.query_results:
        state.errors.append("run_reflector: state.query_results is empty; run the SQL Executor node first.")
        return state

    provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()

    print(f"[Reflector] Provider: {provider}. Building reflection prompt for {len(state.kpi_specs)} KPIs...")
    prompt = _build_reflection_prompt(state.data_profile, state.kpi_specs, state.query_results)

    print("[Reflector] Requesting review from LLM...")
    try:
        response = _call_reflection_llm(SYSTEM_PROMPT, prompt, provider)
    except Exception as exc:
        state.errors.append(f"run_reflector: LLM call failed for provider '{provider}': {exc}")
        return state

    notes = response.notes
    _log_reflection(dataset_name, notes)

    if not notes:
        state.reflection_notes = notes
        return state

    print(f"[Reflector] Applying fixes for {len(notes)} flagged KPI(s)...")
    results_by_name = {qr.kpi_name: qr for qr in state.query_results}
    kpis_by_name = {kpi.name: kpi for kpi in state.kpi_specs}
    dropped_kpi_names: set[str] = set()

    for note in notes:
        if note.kpi_name not in kpis_by_name:
            # LLM referenced a KPI name that doesn't exist in this run —
            # nothing to retry, nothing to drop, just keep the note for audit.
            continue

        if note.fixed_sql_query is None:
            # No fix offered — per the issue, drop rather than retry with
            # nothing changed (that would just fail again).
            dropped_kpi_names.add(note.kpi_name)
            print(f"[Reflector] Dropping '{note.kpi_name}': no fix available for {note.issue_type}.")
            continue

        print(f"[Reflector] Re-executing '{note.kpi_name}' with fixed SQL...")
        try:
            retry_result = rerun_single_kpi(state, note.kpi_name, note.fixed_sql_query)
        except Exception as exc:
            state.errors.append(
                f"run_reflector: retry execution failed for KPI '{note.kpi_name}': {exc}"
            )
            dropped_kpi_names.add(note.kpi_name)
            continue

        if retry_result.status == "fail":
            print(
                f"[Reflector] Dropping '{note.kpi_name}': retry with fixed SQL still failed "
                f"({retry_result.error_message})."
            )
            dropped_kpi_names.add(note.kpi_name)
        else:
            print(f"[Reflector] '{note.kpi_name}' fixed successfully on retry.")
            results_by_name[note.kpi_name] = retry_result
            # Keep the KPISpec's sql_query in sync with what actually ran,
            # so downstream nodes (and any re-inspection) see the real query.
            kpis_by_name[note.kpi_name] = kpis_by_name[note.kpi_name].model_copy(
                update={"sql_query": note.fixed_sql_query}
            )

    state.kpi_specs = [kpi for name, kpi in kpis_by_name.items() if name not in dropped_kpi_names]
    state.query_results = [
        qr for name, qr in results_by_name.items() if name not in dropped_kpi_names
    ]
    state.reflection_notes = notes

    print(f"[Reflector] Done: {len(dropped_kpi_names)} KPI(s) dropped, {len(state.kpi_specs)} remaining.")
    return state