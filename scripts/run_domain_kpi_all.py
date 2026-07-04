"""
Runs the Domain/KPI node against every `*_profile.json` file in
`data/profiles/` and writes `<dataset>_kpis.json` alongside them.

Usage:
    LLM_PROVIDER=gemini python scripts/run_domain_kpi_all.py
    LLM_PROVIDER=mistral python scripts/run_domain_kpi_all.py

Expects GEMINI_API_KEY or MISTRAL_API_KEY (matching LLM_PROVIDER) to be set.
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.domain_kpi import run_domain_kpi, save_kpi_output  # noqa: E402
from agent.models import DataProfile  # noqa: E402
from agent.state import AgentState  # noqa: E402

PROFILES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "profiles"))


def main() -> None:
    provider = os.environ.get("LLM_PROVIDER", "gemini")
    print(f"Using LLM_PROVIDER={provider}")

    profile_paths = sorted(glob.glob(os.path.join(PROFILES_DIR, "*_profile.json")))
    if not profile_paths:
        print(f"No *_profile.json files found in {PROFILES_DIR}")
        return

    for path in profile_paths:
        dataset_name = os.path.basename(path).removesuffix("_profile.json")
        print(f"\n--- {dataset_name} ---")

        with open(path) as f:
            raw = json.load(f)
        profile = DataProfile(**raw)

        state = AgentState(data_profile=profile)
        state = run_domain_kpi(state)

        if state.errors:
            print(f"FAILED for '{dataset_name}':")
            for err in state.errors:
                print(f"  - {err}")
            continue

        out_path = save_kpi_output(state, dataset_name, output_dir=PROFILES_DIR)
        print(f"Domain: {state.domain_hypothesis.domain} (confidence={state.domain_hypothesis.confidence:.2f})")
        print(f"Wrote {len(state.kpi_specs)} KPIs to {out_path}")


if __name__ == "__main__":
    main()