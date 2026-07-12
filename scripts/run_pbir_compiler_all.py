"""
Runs the PBIR Compiler node against every dataset that has a `*_kpis.json`
in `data/profiles/` (i.e. every dataset that's already been through the
Profiler and Domain/KPI nodes), and writes a `.pbip` folder for each one
under `output/<dataset>_report/`.

query_results reconstruction:
    This script does not re-run the SQL Executor. There is currently no
    persisted `*_query_results.json` on disk.
    Instead, for each KPI in `<dataset>_kpis.json`:
      - if `<dataset>_reflection.json` exists and has a note for that KPI,
        use the note's `fixed_sql_query` as the KPI's SQL (the Reflector
        only writes a note when it found and fixed an issue, so a fixed
        note is exactly a corrected, re-verified query);
      - otherwise, use the KPI's original sql_query from *_kpis.json
        unchanged (no issue was ever flagged for it).
    Every resulting QueryResult is built with status="pass" -- this mirrors
    exactly what the two uploaded reflection files show (every flagged KPI
    in both chinook_reflection.json and online_retail_reflection.json has a
    non-null fixed_sql_query; none were left un-fixable/dropped). If a
    dataset's reflection file has a note with fixed_sql_query=null (a KPI
    the Reflector could not fix), that KPI is skipped rather than passed
    through -- see _kpi_specs_with_reflector_fixes() below.

    This is reconstruction from already-produced pipeline artifacts, not a
    live re-execution -- it does not verify the fixed SQL actually runs
    against the raw data again. If you need that guarantee, re-run
    scripts/run_sql_reflector_all.py first and extend it to persist
    query_results.json, then point this script at that file instead.

Scope note (confirmed, minimal): CSV source only -- there is no
SQLite support in this issue's PBIR compiler. chinook_profile.json's
recorded source_path is a .sqlite file (data\\raw\\chinook.sqlite), which
this compiler cannot read. Chinook is therefore opt-in and, when run,
looks for data/raw/chinook.csv specifically (a CSV export of the same
table), NOT the .sqlite file recorded in the profile.

Usage:
    python -m scripts.run_pbir_compiler_all
    python -m scripts.run_pbir_compiler_all --chinook
    python -m scripts.run_pbir_compiler_all --only hr,online_retail
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.models import DataProfile, KPISpec, QueryResult  # noqa: E402
from agent.state import AgentState  # noqa: E402
from pbir.compiler.builder import run_pbir_compiler  # noqa: E402
from pbir.compiler.serialiser import write_pbip  # noqa: E402

PROFILES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "profiles"))
OUTPUT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "output"))
RAW_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "raw"))

# chinook is opt-in: its profile's recorded source_path is a .sqlite file,
# which this CSV-only compiler cannot read (mentor-confirmed scope: no
# SQLite support in this issue). Running it requires a chinook.csv export
# to already exist in data/raw/ -- see _resolve_csv_path().
DEFAULT_EXCLUDED_DATASETS = {"chinook"}


def _kpi_specs_with_reflector_fixes(dataset_name: str, kpi_data: dict) -> tuple[list[KPISpec], list[QueryResult]]:
    """
    Builds (kpi_specs, query_results) for one dataset from its *_kpis.json
    plus its *_reflection.json (if one exists), per the reconstruction
    rules in this module's docstring.

    Returns the kpi_specs list filtered down to only the KPIs that end up
    with a usable SQL query (i.e. drops any KPI whose reflection note has
    fixed_sql_query=None -- an issue the Reflector flagged but could not
    fix), paired 1:1 with their QueryResult (all status="pass").
    """
    reflection_path = os.path.join(PROFILES_DIR, f"{dataset_name}_reflection.json")
    fixes_by_kpi_name: dict[str, str | None] = {}
    if os.path.exists(reflection_path):
        with open(reflection_path) as f:
            reflection = json.load(f)
        for note in reflection.get("notes", []):
            fixes_by_kpi_name[note["kpi_name"]] = note.get("fixed_sql_query")

    kpi_specs: list[KPISpec] = []
    query_results: list[QueryResult] = []

    for raw_kpi in kpi_data["kpi_specs"]:
        kpi_name = raw_kpi["name"]
        final_sql = raw_kpi["sql_query"]

        if kpi_name in fixes_by_kpi_name:
            fixed_sql = fixes_by_kpi_name[kpi_name]
            if fixed_sql is None:
                # Reflector flagged this KPI but could not fix it (per
                # agent/models.py's own ReflectionNote docstring: "such KPIs
                # are dropped without a retry") -- skip it entirely rather
                # than pass through SQL known to be broken.
                continue
            final_sql = fixed_sql

        kpi_spec = KPISpec(**{**raw_kpi, "sql_query": final_sql})
        kpi_specs.append(kpi_spec)
        query_results.append(
            QueryResult(
                kpi_name=kpi_name,
                sql_query=final_sql,
                status="pass",
                row_count=0,
                columns=[],
                result_rows=[],
            )
        )

    return kpi_specs, query_results


def _resolve_csv_path(profile: DataProfile, dataset_name: str) -> str | None:
    """
    Finds this dataset's CSV file and returns an ABSOLUTE path, always.

    This matters: Power Query's File.Contents(...) has no concept of "relative
    to the .pbip file" or "relative to a project root" -- a bare relative
    string like "data/raw/hr.csv" gets evaluated (if at all) relative to
    whatever working directory Power BI Desktop happens to be using, which
    is not predictable and is NOT the same thing Python's os.path.exists()
    just resolved it against. A path that "exists" from this script's point
    of view because it's relative to the terminal's CWD can still fail
    silently inside Power BI Desktop (symptom: "some tables have incomplete
    or no data" / "failed to load the report"). So every candidate below is
    converted to an absolute path with os.path.abspath() before being
    returned or checked -- never a raw relative string.

    Tries profile.source_path first (only if it's actually a .csv path --
    this compiler is CSV-only, so a .sqlite/.db source_path is never used
    even if it resolves on disk), then falls back to data/raw/<dataset_name>.csv.
    """
    project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

    candidates = []
    if profile.source_path.lower().endswith(".csv"):
        raw = profile.source_path.replace("\\", os.sep).replace("/", os.sep)
        candidates.append(raw)
        candidates.append(os.path.join(project_root, raw))

    candidates.append(os.path.join(RAW_DATA_DIR, f"{dataset_name}.csv"))

    for candidate in candidates:
        abs_candidate = os.path.abspath(candidate)
        if os.path.exists(abs_candidate):
            return abs_candidate

    return None


def _process_dataset(dataset_name: str, profile_path: str, kpis_path: str) -> None:
    print(f"\n--- {dataset_name} ---")

    with open(profile_path) as f:
        profile = DataProfile(**json.load(f))

    with open(kpis_path) as f:
        kpi_data = json.load(f)

    csv_path = _resolve_csv_path(profile, dataset_name)
    if csv_path is None:
        print(f"SKIPPED '{dataset_name}': no CSV file found.")
        print(f"  This compiler is CSV-only (no SQLite support in this issue's scope).")
        print(f"  Expected a .csv source_path in the profile, or {RAW_DATA_DIR}/{dataset_name}.csv")
        return

    # Point the profile at the resolved CSV path (and clear source_table,
    # which only applies to a SQLite table reference) so the compiler's M
    # query points at a real, readable file rather than whatever path was
    # originally recorded (e.g. chinook_profile.json's .sqlite path).
    profile = profile.model_copy(update={"source_path": csv_path, "source_table": None})

    kpi_specs, query_results = _kpi_specs_with_reflector_fixes(dataset_name, kpi_data)
    n_dropped = len(kpi_data["kpi_specs"]) - len(kpi_specs)
    if n_dropped:
        print(f"  {n_dropped} KPI(s) dropped: Reflector flagged an issue with no fix available.")

    state = AgentState(
        input_path=csv_path,
        output_path=os.path.join(OUTPUT_DIR, f"{dataset_name}_report"),
        data_profile=profile,
        kpi_specs=kpi_specs,
        query_results=query_results,
    )

    result_state = run_pbir_compiler(state)
    if result_state.errors:
        print(f"PBIR COMPILER FAILED for '{dataset_name}':")
        for err in result_state.errors:
            print(f"  - {err}")
        return

    project = result_state.pbir_project
    n_pages = len(project.pages)
    n_visuals = sum(len(p.visuals) for p in project.pages)
    print(f"Built: {n_pages} page(s), {n_visuals} visual(s), {len(project.data_table.measures)} measure(s).")

    out_dir = Path(state.output_path)
    write_pbip(project, out_dir)
    print(f"Wrote {out_dir / (project.report_name + '.pbip')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chinook",
        action="store_true",
        help="Include chinook (excluded by default -- requires data/raw/chinook.csv; "
             "this compiler cannot read chinook_profile.json's recorded .sqlite path).",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Comma-separated dataset names to run, overriding the default set entirely "
             "(e.g. --only hr,online_retail). Overrides --chinook too if chinook is in the list.",
    )
    args = parser.parse_args()

    kpis_paths = sorted(glob.glob(os.path.join(PROFILES_DIR, "*_kpis.json")))
    if not kpis_paths:
        print(f"No *_kpis.json files found in {PROFILES_DIR}. Run scripts/run_domain_kpi_all.py first.")
        return

    if args.only:
        allowed = {name.strip() for name in args.only.split(",") if name.strip()}
    else:
        allowed = None  # means "all datasets found, minus DEFAULT_EXCLUDED_DATASETS unless --chinook"

    for kpis_path in kpis_paths:
        dataset_name = os.path.basename(kpis_path).removesuffix("_kpis.json")
        profile_path = os.path.join(PROFILES_DIR, f"{dataset_name}_profile.json")

        if allowed is not None:
            if dataset_name not in allowed:
                continue
        else:
            if dataset_name in DEFAULT_EXCLUDED_DATASETS and not args.chinook:
                print(f"\n--- {dataset_name} ---")
                print(f"SKIPPED: {dataset_name} is excluded by default (pass --chinook to include it).")
                continue

        if not os.path.exists(profile_path):
            print(f"\n--- {dataset_name} ---")
            print(f"SKIPPED: no matching {dataset_name}_profile.json found in {PROFILES_DIR}")
            continue

        _process_dataset(dataset_name, profile_path, kpis_path)


if __name__ == "__main__":
    main()