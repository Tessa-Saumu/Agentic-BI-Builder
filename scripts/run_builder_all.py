"""
Runs the PBIR Compiler (builder + serialiser) against datasets that have
already been through the Profiler, Domain/KPI, SQL Executor, and Reflector
nodes -- i.e. every dataset with a `*_profile.json` and a `*_kpis.json` in
`data/profiles/` -- and writes a full .pbip project for each to
`output/<dataset>/`.

hr and online_retail are compiled by default. chinook is skipped by default
(its dataset is bundled mainly for reflector-testing, per the
"[SABOTAGED for reflector testing: ...]" markers baked into its KPI
descriptions) and is only compiled when --include-chinook is passed.

SQL source of truth per KPI:
    Each KPISpec's own `sql_query` is the Domain/KPI node's original SQL.
    If `data/profiles/<dataset>_reflection.json` exists AND contains a note
    for that KPI's name, the note's `fixed_sql_query` is used instead --
    that's the corrected SQL the Reflector settled on. Datasets with no
    reflection file at all (e.g. hr, which had no issues to fix) simply use
    every KPI's original sql_query unchanged. Every KPI that reaches the
    builder is treated as a passing QueryResult: by this stage in the
    pipeline (post-reflection) each KPI's SQL is the pipeline's final,
    vetted query, whether or not it happened to need a fix along the way.

Usage:
    python -m scripts.run_builder_all
    python -m scripts.run_builder_all --include-chinook
    python -m scripts.run_builder_all --datasets hr online_retail
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; fall back to whatever's already in the environment

from agent.models import DataProfile, KPISpec, QueryResult  # noqa: E402
from agent.state import AgentState  # noqa: E402
from pbir.compiler.builder import run_pbir_compiler  # noqa: E402
from pbir.compiler.serialiser import write_pbip  # noqa: E402

PROFILES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "profiles"))
OUTPUT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "output"))

# Datasets compiled unless --datasets overrides this list. chinook is
# intentionally absent here -- it's added only via --include-chinook.
DEFAULT_DATASETS = ["hr", "online_retail"]
CHINOOK_DATASET = "chinook"


def _load_kpi_specs(kpis_path: str) -> tuple[list[KPISpec], dict]:
    with open(kpis_path) as f:
        kpi_data = json.load(f)
    kpi_specs = [KPISpec(**k) for k in kpi_data["kpi_specs"]]
    return kpi_specs, kpi_data.get("domain_hypothesis", {})


def _load_reflection_fixes(reflection_path: str) -> dict[str, str]:
    """
    Returns {kpi_name: fixed_sql_query} for every note in the reflection
    file, or {} if the file doesn't exist (a dataset with no flagged
    issues, e.g. hr, has no *_reflection.json at all).
    """
    if not os.path.exists(reflection_path):
        return {}
    with open(reflection_path) as f:
        reflection_data = json.load(f)
    return {note["kpi_name"]: note["fixed_sql_query"] for note in reflection_data.get("notes", [])}


def _build_query_results(kpi_specs: list[KPISpec], fixes_by_kpi_name: dict[str, str]) -> list[QueryResult]:
    """
    One QueryResult per KPISpec, using the Reflector's fixed_sql_query in
    place of the original sql_query wherever a fix was recorded for that
    KPI's name, and the KPISpec's own sql_query otherwise. Every result is
    marked "pass" -- this is the pipeline's final SQL for each KPI by the
    time it reaches the builder, whether it needed a fix or not.
    """
    query_results = []
    for kpi in kpi_specs:
        sql_query = fixes_by_kpi_name.get(kpi.name, kpi.sql_query)
        query_results.append(QueryResult(kpi_name=kpi.name, sql_query=sql_query, status="pass"))
    return query_results


def _process_dataset(dataset_name: str, profile_path: str, kpis_path: str, reflection_path: str) -> None:
    print(f"\n--- {dataset_name} ---")

    with open(profile_path) as f:
        profile = DataProfile(**json.load(f))

    kpi_specs, _domain_hypothesis = _load_kpi_specs(kpis_path)
    fixes_by_kpi_name = _load_reflection_fixes(reflection_path)
    n_fixed = sum(1 for kpi in kpi_specs if kpi.name in fixes_by_kpi_name)
    if os.path.exists(reflection_path):
        print(f"Reflection: {n_fixed}/{len(kpi_specs)} KPI(s) using a reflector-fixed query.")
    else:
        print(f"Reflection: no {os.path.basename(reflection_path)} found; using original SQL for all KPIs.")

    query_results = _build_query_results(kpi_specs, fixes_by_kpi_name)

    state = AgentState(data_profile=profile, kpi_specs=kpi_specs, query_results=query_results)
    state = run_pbir_compiler(state)

    if state.errors:
        print(f"BUILDER FAILED for '{dataset_name}':")
        for err in state.errors:
            print(f"  - {err}")
        return

    project = state.pbir_project
    print(f"Built {len(project.pages)} page(s), {len(project.data_table.measures)} measure(s).")

    dataset_output_dir = os.path.join(OUTPUT_DIR, dataset_name)
    write_pbip(project, dataset_output_dir)
    print(f"Wrote .pbip project to {dataset_output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=None,
        help=f"Dataset names to compile (default: {DEFAULT_DATASETS}). Overrides --include-chinook.",
    )
    parser.add_argument(
        "--include-chinook",
        action="store_true",
        help=f"Also compile the '{CHINOOK_DATASET}' dataset (skipped by default; "
        f"its KPIs are deliberately sabotaged for reflector testing).",
    )
    args = parser.parse_args()

    if args.datasets is not None:
        datasets = list(args.datasets)
    else:
        datasets = list(DEFAULT_DATASETS)
        if args.include_chinook:
            datasets.append(CHINOOK_DATASET)

    print(f"Datasets to compile: {datasets}")

    for dataset_name in datasets:
        profile_path = os.path.join(PROFILES_DIR, f"{dataset_name}_profile.json")
        kpis_path = os.path.join(PROFILES_DIR, f"{dataset_name}_kpis.json")
        reflection_path = os.path.join(PROFILES_DIR, f"{dataset_name}_reflection.json")

        if not os.path.exists(profile_path):
            print(f"\n--- {dataset_name} ---")
            print(f"SKIPPED: no {dataset_name}_profile.json found in {PROFILES_DIR}")
            continue
        if not os.path.exists(kpis_path):
            print(f"\n--- {dataset_name} ---")
            print(f"SKIPPED: no {dataset_name}_kpis.json found in {PROFILES_DIR}. "
                  f"Run scripts/run_domain_kpi_all.py first.")
            continue

        _process_dataset(dataset_name, profile_path, kpis_path, reflection_path)


if __name__ == "__main__":
    main()
