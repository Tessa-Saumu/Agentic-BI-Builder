"""
Runs the SQL Executor and Reflector nodes against every dataset that has
both a `*_profile.json` and a `*_kpis.json` in `data/profiles/` (i.e. every
dataset that's already been through the Profiler and Domain/KPI nodes).

The raw data file location is read from DataProfile.source_path — the same
path the Profiler recorded when it originally loaded the file — rather than
guessed from the dataset name, since that's the only value that's actually
correct for every input type (a CSV named after the dataset, or a shared
.sqlite file with a specific source_table, as with chinook).

Usage:
    Set .env LLM_PROVIDER = "gemini" then run python -m scripts.run_sql_reflector_all
    Set .env LLM_PROVIDER = "mistral" then run python -m scripts.run_sql_reflector_all

Expects GEMINI_API_KEY or MISTRAL_API_KEY (matching LLM_PROVIDER) to be set.
Requires the raw data files (CSV / .sqlite) to exist at the paths recorded
in each *_profile.json's source_path — these are not stored in data/profiles/
and must be present on disk separately (e.g. under data/raw/).
"""
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

from agent.models import DataProfile, KPISpec  # noqa: E402
from agent.reflector import run_reflector  # noqa: E402
from agent.sql_executor import run_sql_executor  # noqa: E402
from agent.state import AgentState  # noqa: E402

PROFILES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "profiles"))
# Fallback directory to check if source_path (as recorded at profiling time,
# possibly on a different machine/OS) doesn't resolve directly.
RAW_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "raw"))


def _resolve_data_path(profile: DataProfile, dataset_name: str) -> str | None:
    """
    Find the real raw data file for this dataset.

    Tries, in order:
    1. profile.source_path exactly as recorded (works if running on the same
       machine/OS that produced the profile).
    2. profile.source_path with backslashes normalized to the current OS's
       separator (handles a profile recorded on Windows being used elsewhere).
    3. data/raw/<dataset_name>.<ext> for each common extension, as a last
       resort if source_path doesn't resolve at all (e.g. the repo was moved).

    Returns None if nothing resolves.
    """
    candidates = [profile.source_path, profile.source_path.replace("\\", os.sep).replace("/", os.sep)]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
        # Also try relative to the project root, in case source_path was
        # recorded as an absolute path or a different relative root.
        project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        alt = os.path.normpath(os.path.join(project_root, candidate))
        if os.path.exists(alt):
            return alt

    for ext in (".csv", ".sqlite", ".db", ".sqlite3"):
        alt = os.path.join(RAW_DATA_DIR, f"{dataset_name}{ext}")
        if os.path.exists(alt):
            return alt

    return None


def _process_dataset(dataset_name: str, profile_path: str, kpis_path: str) -> None:
    print(f"\n--- {dataset_name} ---")

    with open(profile_path) as f:
        profile = DataProfile(**json.load(f))

    with open(kpis_path) as f:
        kpi_data = json.load(f)
    kpi_specs = [KPISpec(**k) for k in kpi_data["kpi_specs"]]

    data_path = _resolve_data_path(profile, dataset_name)
    if data_path is None:
        print(f"SKIPPED '{dataset_name}': could not locate raw data file.")
        print(f"  Expected at recorded source_path: {profile.source_path}")
        print(f"  Or under: {RAW_DATA_DIR}/{dataset_name}.<csv|sqlite|db|sqlite3>")
        return

    state = AgentState(input_path=data_path, data_profile=profile, kpi_specs=kpi_specs)

    state = run_sql_executor(state)
    if state.errors:
        print(f"SQL EXECUTOR FAILED for '{dataset_name}':")
        for err in state.errors:
            print(f"  - {err}")
        return

    n_failed = sum(1 for qr in state.query_results if qr.status == "fail")
    print(f"SQL Executor: {len(state.query_results)} KPIs run, {n_failed} failed at execution.")

    state = run_reflector(state, dataset_name=dataset_name)
    if state.errors:
        print(f"REFLECTOR FAILED for '{dataset_name}':")
        for err in state.errors:
            print(f"  - {err}")
        return

    print(f"Reflector: {len(state.reflection_notes)} issue(s) flagged.")
    print(f"KPIs remaining after reflection: {[k.name for k in state.kpi_specs]}")
    all_pass = all(qr.status == "pass" for qr in state.query_results)
    print(f"{'ALL REMAINING KPIs PASS' if all_pass else 'SOME REMAINING KPIs STILL FAILING'}")


def main() -> None:
    provider = os.environ.get("LLM_PROVIDER", "gemini")
    print(f"Using LLM_PROVIDER={provider}")

    kpis_paths = sorted(glob.glob(os.path.join(PROFILES_DIR, "*_kpis.json")))
    if not kpis_paths:
        print(f"No *_kpis.json files found in {PROFILES_DIR}. Run scripts/run_domain_kpi_all.py first.")
        return

    for kpis_path in kpis_paths:
        dataset_name = os.path.basename(kpis_path).removesuffix("_kpis.json")
        profile_path = os.path.join(PROFILES_DIR, f"{dataset_name}_profile.json")

        if not os.path.exists(profile_path):
            print(f"\n--- {dataset_name} ---")
            print(f"SKIPPED: no matching {dataset_name}_profile.json found in {PROFILES_DIR}")
            continue

        _process_dataset(dataset_name, profile_path, kpis_path)


if __name__ == "__main__":
    main()