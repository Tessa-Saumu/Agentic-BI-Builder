"""
scripts/run_reflector_stress_test.py

Deliberately injects realistic SQL errors into a copy of an already-validated
dataset's *_kpis.json, then runs the real SQL Executor + Reflector nodes
against the injected copy and reports whether the Reflector caught and fixed
each planted issue.

WHY THIS SCRIPT EXISTS (read before running):
The Phase 4 validation issue's acceptance criteria require "at least two
datasets show the Reflector catching and correcting at least one issue."
Across every real run of this pipeline during development, the Domain/KPI
node's generated SQL has been valid and sound -- the Reflector has had
nothing organic to flag. That's a real, positive finding about the
Domain/KPI node's output quality, not a problem to hide. This script exists
to prove the Reflector's correction *capability* separately, by giving it
something to correct on purpose, rather than by misrepresenting the three
real end-to-end validation runs as having contained organic bugs they did
not have.

This script is NEVER wired into run_agent.py, graph.py, or any of the
run_*_all.py scripts. It reads a dataset's real, already-produced
*_profile.json and *_kpis.json from data/profiles/, writes its injected
copy to a clearly separate *_kpis_sabotaged.json file, and its results to
data/profiles/<dataset>_stress_test_reflection.json -- never overwriting
the dataset's real *_kpis.json or *_reflection.json. The real validation
runs (via run_agent.py) never read this script's output.

INJECTION STRATEGY:
Selects up to 3 KPIs from the dataset's real kpi_specs and rewrites each
one's sql_query with a distinct, realistic error type -- the kind an
analyst might actually make, not an obviously malformed string:
  - sql_error:    reference a column name that doesn't exist (e.g. a typo
                  or an old column name), so the query fails to execute.
  - wrong_aggregation: swap the aggregation function in a way that still
                  runs but computes something different from what the
                  KPI's name/description claims (e.g. COUNT where SUM was
                  correct).
  - null_heavy:   change the query to aggregate over a column already
                  known (from the DataProfile) to have a high null rate,
                  producing a technically-valid but mostly-NULL result.
Exactly which of these 3 gets applied to which KPI depends on what the
DataProfile actually contains for that dataset (e.g. null_heavy needs a
column with a real null rate to target) -- see _select_injections() below.

Usage:
    python -m scripts.run_reflector_stress_test --dataset chinook
    python -m scripts.run_reflector_stress_test --dataset online_retail
    python -m scripts.run_reflector_stress_test --dataset chinook --n-inject 2

Expects data/profiles/<dataset>_profile.json and
data/profiles/<dataset>_kpis.json to already exist (i.e. the dataset has
already been through the real Profiler and Domain/KPI nodes). Also expects
GEMINI_API_KEY or MISTRAL_API_KEY (matching LLM_PROVIDER) to be set, since
this calls the real Reflector LLM call.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agent.models import DataProfile, KPISpec  # noqa: E402
from agent.reflector import run_reflector  # noqa: E402
from agent.sql_executor import run_sql_executor  # noqa: E402
from agent.state import AgentState  # noqa: E402

PROFILES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "profiles"))
RAW_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "raw"))


def _find_null_heavy_column(profile: DataProfile, min_null_rate: float = 0.05) -> str | None:
    """
    Returns a column name with a real, documented null rate above
    min_null_rate, for the null_heavy injection to target -- so that
    injection is grounded in the dataset's actual profile rather than an
    arbitrary column that happens to have no nulls at all (which would make
    the "null_heavy" injection not actually null-heavy, and therefore not a
    realistic test of that issue_type).

    Returns None if no column in the profile clears the threshold -- the
    caller falls back to a different injection type in that case (see
    _select_injections below), rather than injecting a null_heavy case that
    wouldn't actually be null-heavy.
    """
    candidates = [
        (name, col.null_rate)
        for name, col in profile.columns.items()
        if col.null_rate >= min_null_rate and not col.is_all_null
    ]
    if not candidates:
        return None
    # Prefer the column with the highest null rate -- the clearest, most
    # unambiguous case for the Reflector to catch.
    candidates.sort(key=lambda c: c[1], reverse=True)
    return candidates[0][0]


def _inject_sql_error(kpi: KPISpec) -> tuple[KPISpec, str]:
    """
    Injects a sql_error: renames one column reference in the query to a
    plausible-but-wrong variant (trailing 's', or 'Id' -> 'ID'), simulating
    a realistic typo rather than an obviously broken string like 'xyz123'.
    Returns (mutated_kpi, description_of_what_was_broken).
    """
    original = kpi.sql_query
    # Try a couple of plausible typo patterns; use whichever actually
    # changes the string, so this doesn't silently no-op on a query whose
    # structure doesn't match the first pattern tried.
    mutated = original.replace("Total", "Totals", 1)
    if mutated == original:
        mutated = original.replace("Id", "ID", 1)
    if mutated == original:
        # Last resort: corrupt the FROM clause's table reference itself.
        mutated = original.replace("FROM data", "FROM dataset", 1)

    description = f"Column/table reference corrupted: '{original}' -> '{mutated}'"
    return kpi.model_copy(update={"sql_query": mutated}), description


def _inject_wrong_aggregation(kpi: KPISpec) -> tuple[KPISpec, str]:
    """
    Injects a wrong_aggregation: swaps SUM(...) for COUNT(...) or vice
    versa, which still executes without error but computes a different
    quantity than the KPI's name/description claims -- exactly the class
    of bug a purely mechanical "did it run" check cannot catch, which is
    the Reflector's actual reason for existing.
    """
    original = kpi.sql_query
    if "SUM(" in original:
        mutated = original.replace("SUM(", "COUNT(", 1)
        description = f"SUM replaced with COUNT (same query still executes, wrong quantity): '{original}' -> '{mutated}'"
    elif "AVG(" in original:
        mutated = original.replace("AVG(", "SUM(", 1)
        description = f"AVG replaced with SUM (same query still executes, wrong quantity): '{original}' -> '{mutated}'"
    elif "COUNT(" in original:
        mutated = original.replace("COUNT(", "SUM(", 1)
        description = f"COUNT replaced with SUM (may fail or silently change meaning): '{original}' -> '{mutated}'"
    else:
        # No aggregation function found to swap -- caller should treat
        # this as a failed injection attempt and pick a different KPI.
        return kpi, ""
    return kpi.model_copy(update={"sql_query": mutated}), description


def _inject_null_heavy(kpi: KPISpec, target_column: str) -> tuple[KPISpec, str]:
    """
    Injects a null_heavy case: rewrites the query to a simple aggregation
    grouped by a column already known (from the DataProfile) to have a
    real, meaningful null rate, so the result is technically valid SQL but
    dominated by NULL groupings -- the "real, meaningful" qualifier from
    reflector.py's own SYSTEM_PROMPT is what this is designed to trigger.
    """
    original = kpi.sql_query
    mutated = f"SELECT {target_column}, COUNT(*) AS row_count FROM data GROUP BY {target_column}"
    description = (
        f"Query replaced with a GROUP BY on '{target_column}', a column with a "
        f"real documented null rate in this dataset's profile: '{original}' -> '{mutated}'"
    )
    return kpi.model_copy(update={"sql_query": mutated}), description


def _select_injections(
    profile: DataProfile, kpi_specs: list[KPISpec], n_inject: int
) -> list[tuple[int, KPISpec, str, str]]:
    """
    Selects up to n_inject KPIs from kpi_specs and returns
    (index, mutated_kpi, issue_type_attempted, description) for each.

    Injection type per slot is chosen in a fixed order (sql_error,
    wrong_aggregation, null_heavy) so repeated runs are deterministic, and
    each type is only attempted on a KPI where it can actually apply (e.g.
    null_heavy is skipped entirely if the profile has no column with a
    real null rate -- see _find_null_heavy_column). If fewer than
    n_inject KPIs successfully accept an injection, fewer than n_inject
    are returned rather than forcing a bad injection.
    """
    if not kpi_specs:
        return []

    null_heavy_column = _find_null_heavy_column(profile)
    injection_plan = ["sql_error", "wrong_aggregation", "null_heavy"][:n_inject]

    results: list[tuple[int, KPISpec, str, str]] = []
    used_indices: set[int] = set()

    for issue_type in injection_plan:
        # Pick the first not-yet-used KPI for this injection type.
        idx = next((i for i in range(len(kpi_specs)) if i not in used_indices), None)
        if idx is None:
            break
        kpi = kpi_specs[idx]

        if issue_type == "sql_error":
            mutated, description = _inject_sql_error(kpi)
        elif issue_type == "wrong_aggregation":
            mutated, description = _inject_wrong_aggregation(kpi)
            if not description:
                continue  # this KPI had no aggregation function to swap; leave it, try next slot on next call
        elif issue_type == "null_heavy":
            if null_heavy_column is None:
                print(
                    f"  [skip] null_heavy injection skipped: no column in this dataset's "
                    f"profile has a real null rate to target."
                )
                continue
            mutated, description = _inject_null_heavy(kpi, null_heavy_column)
        else:
            continue

        used_indices.add(idx)
        results.append((idx, mutated, issue_type, description))

    return results


def run_stress_test(dataset_name: str, n_inject: int = 3) -> None:
    profile_path = os.path.join(PROFILES_DIR, f"{dataset_name}_profile.json")
    kpis_path = os.path.join(PROFILES_DIR, f"{dataset_name}_kpis.json")

    if not os.path.exists(profile_path) or not os.path.exists(kpis_path):
        print(f"SKIPPED '{dataset_name}': missing {profile_path} or {kpis_path}.")
        print("  Run scripts/run_domain_kpi_all.py first to produce these.")
        return

    with open(profile_path) as f:
        profile = DataProfile(**json.load(f))
    with open(kpis_path) as f:
        real_kpi_data = json.load(f)
    real_kpi_specs = [KPISpec(**k) for k in real_kpi_data["kpi_specs"]]

    print(f"\n=== Reflector stress test: {dataset_name} ===")
    print(f"Loaded {len(real_kpi_specs)} real, validated KPIs from {kpis_path}")

    injections = _select_injections(profile, real_kpi_specs, n_inject)
    if not injections:
        print(f"SKIPPED '{dataset_name}': could not construct any injections "
              f"(no KPIs with a usable aggregation pattern, or no null-heavy column).")
        return

    sabotaged_kpi_specs = list(real_kpi_specs)
    planted_issues: dict[str, dict] = {}  # kpi_name -> {issue_type, description}
    for idx, mutated_kpi, issue_type, description in injections:
        sabotaged_kpi_specs[idx] = mutated_kpi
        planted_issues[mutated_kpi.name] = {"issue_type": issue_type, "description": description}
        print(f"  [inject] {mutated_kpi.name} ({issue_type}): {description}")

    sabotaged_path = os.path.join(PROFILES_DIR, f"{dataset_name}_kpis_sabotaged.json")
    with open(sabotaged_path, "w", encoding="utf-8") as f:
        json.dump({"kpi_specs": [k.model_dump() for k in sabotaged_kpi_specs]}, f, indent=2)
    print(f"Sabotaged KPI file written to {sabotaged_path} (for audit — never read by run_agent.py)")

    # Resolve the real CSV the same way run_sql_reflector_all.py does, so
    # execution runs against real data, not a stub.
    csv_candidates = [profile.source_path, os.path.join(RAW_DATA_DIR, f"{dataset_name}.csv")]
    data_path = next((p for p in csv_candidates if os.path.exists(p)), None)
    if data_path is None:
        print(f"SKIPPED '{dataset_name}': could not locate raw data file for execution.")
        return

    state = AgentState(input_path=data_path, data_profile=profile, kpi_specs=sabotaged_kpi_specs)

    print("Running real SQL Executor against sabotaged KPIs...")
    state = run_sql_executor(state)
    if state.errors:
        print(f"SQL EXECUTOR FAILED: {state.errors}")
        return

    print("Running real Reflector against sabotaged KPIs + their execution results...")
    state = run_reflector(state, dataset_name=f"{dataset_name}_stress_test")
    if state.errors:
        print(f"REFLECTOR FAILED: {state.errors}")
        return

    # Score: for each planted issue, was it caught (present in
    # state.reflection_notes) and was a fix offered?
    notes_by_kpi = {n.kpi_name: n for n in state.reflection_notes}
    n_caught = 0
    n_fixed = 0
    report_lines = [f"\n--- Stress test results: {dataset_name} ---"]
    for kpi_name, planted in planted_issues.items():
        note = notes_by_kpi.get(kpi_name)
        if note is None:
            report_lines.append(f"  ❌ MISSED: '{kpi_name}' (planted {planted['issue_type']}) — Reflector did not flag it.")
            continue
        n_caught += 1
        category_match = "exact match" if note.issue_type == planted["issue_type"] else f"categorized as '{note.issue_type}' (planted as '{planted['issue_type']}')"
        fix_status = "fix offered" if note.fixed_sql_query is not None else "NO FIX offered"
        if note.fixed_sql_query is not None:
            n_fixed += 1
        report_lines.append(f"  ✅ CAUGHT: '{kpi_name}' — {category_match}, {fix_status}")

    report_lines.append(f"\n{n_caught}/{len(planted_issues)} planted issues caught, {n_fixed}/{len(planted_issues)} had a fix offered.")
    report_lines.append(f"KPIs flagged for retry (state.kpis_to_retry): {state.kpis_to_retry}")
    print("\n".join(report_lines))

    # Persist full results for the README / PR evidence, clearly separated
    # from the dataset's real *_reflection.json.
    output_path = os.path.join(PROFILES_DIR, f"{dataset_name}_stress_test_reflection.json")
    payload = {
        "dataset": dataset_name,
        "planted_issues": planted_issues,
        "reflection_notes": [n.model_dump() for n in state.reflection_notes],
        "n_planted": len(planted_issues),
        "n_caught": n_caught,
        "n_fixed": n_fixed,
        "kpis_to_retry": state.kpis_to_retry,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Full stress test results written to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, help="Dataset name, e.g. chinook, online_retail, hr")
    parser.add_argument("--n-inject", type=int, default=3, help="Number of KPIs to sabotage (max 3, default 3)")
    args = parser.parse_args()

    provider = os.environ.get("LLM_PROVIDER", "gemini")
    print(f"Using LLM_PROVIDER={provider}")

    run_stress_test(args.dataset, n_inject=min(args.n_inject, 3))


if __name__ == "__main__":
    main()