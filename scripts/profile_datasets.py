"""
scripts/profile_datasets.py — Run the profiler on all three reference datasets
and write JSON outputs to data/profiles/.

Usage (from project root, with venv activated):
    python scripts/profile_datasets.py

Expects these files to already exist:
    data/raw/chinook.sqlite       ← Chinook sample DB
    data/raw/online_retail.csv    ← UCI Online Retail dataset
    data/raw/hr.csv               ← IBM HR Analytics dataset

Creates:
    data/profiles/chinook_profile.json
    data/profiles/online_retail_profile.json
    data/profiles/hr_profile.json
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.profiler import run_profiler

try:
    from agent.state import AgentState
except ImportError:
    from dataclasses import dataclass, field
    from typing import Any

    @dataclass
    class AgentState:  # type: ignore[no-redef]
        input_path: str = ""
        output_path: str = ""
        data_profile: Any = None
        errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dataset config
# ---------------------------------------------------------------------------

DATASETS = [
    {
        "input": "data/raw/chinook.sqlite",
        "output": "data/profiles/chinook_profile.json",
        "label": "Chinook",
    },
    {
        "input": "data/raw/online_retail.csv",
        "output": "data/profiles/online_retail_profile.json",
        "label": "Online Retail",
    },
    {
        "input": "data/raw/hr.csv",
        "output": "data/profiles/hr_profile.json",
        "label": "HR Analytics",
    },
]


def run_all() -> None:
    output_dir = Path("data/profiles")
    output_dir.mkdir(parents=True, exist_ok=True)

    for dataset in DATASETS:
        label = dataset["label"]
        input_path = dataset["input"]
        output_path = dataset["output"]

        print(f"\n{'='*60}")
        print(f"Profiling: {label}")
        print(f"  Input : {input_path}")

        if not Path(input_path).exists():
            print(f"  ⚠️  SKIPPED — file not found: {input_path}")
            print(f"  Download instructions below.")
            continue

        state = AgentState(input_path=input_path, output_path="output/placeholder")
        result = run_profiler(state)

        if result.errors:
            print(f"  ❌ Errors: {result.errors}")
            continue

        if result.data_profile is None:
            print("  ❌ No profile produced.")
            continue

        # Serialize to JSON
        profile_dict = result.data_profile.model_dump()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(profile_dict, f, indent=2, default=str)

        profile = result.data_profile
        null_cols = [
            col for col, p in profile.columns.items() if p.null_rate > 0
        ]

        print(f"  ✅ Profile written to: {output_path}")
        print(f"  Rows: {profile.row_count:,}  |  Columns: {profile.column_count}")
        if profile.source_table:
            print(f"  Table: {profile.source_table}")
        print(f"  Columns with nulls ({len(null_cols)}): {null_cols[:5]}"
              + (" ..." if len(null_cols) > 5 else ""))


if __name__ == "__main__":
    run_all()

    print(f"\n{'='*60}")
    print("DOWNLOAD INSTRUCTIONS (if any files were skipped)")
    print("="*60)
    print("""
Chinook SQLite:
  https://github.com/lerocha/chinook-database/releases
  → Download Chinook_Sqlite.sqlite → rename to chinook.sqlite
  → Place in data/raw/

Online Retail CSV:
  https://archive.ics.uci.edu/dataset/352/online+retail
  → Download the Excel file → open in Excel or pandas
  → Save as online_retail.csv → place in data/raw/
  Pandas conversion:
    import pandas as pd
    df = pd.read_excel('Online Retail.xlsx')
    df.to_csv('data/raw/online_retail.csv', index=False)

HR Analytics CSV:
  https://www.kaggle.com/datasets/pavansubhasht/ibm-hr-analytics-attrition-dataset
  → Download WA_Fn-UseC_-HR-Employee-Attrition.csv
  → Rename to hr.csv → place in data/raw/
  (Requires free Kaggle account)
""")