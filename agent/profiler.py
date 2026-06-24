"""
agent/profiler.py — Deterministic Pandas-based schema analysis node.

This is the first node in the LangGraph pipeline. It has zero LLM calls.
It loads the input file (CSV or SQLite), computes per-column statistics,
and stores a DataProfile in state.data_profile.

All downstream nodes (Planner, SQL Generator, PBIR Compiler) depend on
this output
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any
import pandas as pd
from agent.models import ColumnProfile, DataProfile
from agent.state import AgentState

# ---------------------------------------------------------------------------
# Dtype label mapping
# ---------------------------------------------------------------------------

_DTYPE_MAP: dict[str, str] = {
    "int8": "integer",
    "int16": "integer",
    "int32": "integer",
    "int64": "integer",
    "uint8": "integer",
    "uint16": "integer",
    "uint32": "integer",
    "uint64": "integer",
    "float16": "float",
    "float32": "float",
    "float64": "float",
    "bool": "boolean",
    "object": "string",       
    "category": "string",
}


def _infer_dtype_label(series: pd.Series) -> str:
    """Map a pandas dtype to a human-readable label.

    Handles datetime detection separately because pandas may not
    auto-parse datetime columns when reading CSV files.
    """
    dtype_str = str(series.dtype)

    # Direct lookup first
    if dtype_str in _DTYPE_MAP:
        return _DTYPE_MAP[dtype_str]

    # Datetime variants (datetime64[ns], datetime64[us], etc.)
    if dtype_str.startswith("datetime"):
        return "datetime"

    # Timedelta, period, etc. — treat as string for BI purposes
    return "unknown"


# ---------------------------------------------------------------------------
# File loader
# ---------------------------------------------------------------------------

def _load_file(input_path: str) -> tuple[pd.DataFrame, str | None]:
    """Load CSV or SQLite file into a DataFrame.

    Returns:
        (df, table_name) — table_name is None for CSV inputs.

    Raises:
        FileNotFoundError: if the path does not exist.
        ValueError: if the file extension is unsupported.
        RuntimeError: wraps unexpected pandas / sqlite3 errors with context.
    """
    path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    suffix = path.suffix.lower()

    # --- CSV ---
    if suffix == ".csv":
        try:
            df = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            raise RuntimeError(f"Failed to read CSV '{input_path}': {exc}") from exc
        return df, None

    # --- SQLite ---
    if suffix in (".sqlite", ".db", ".sqlite3"):
        try:
            conn = sqlite3.connect(path)
            # Discover tables; pick the first user table
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name;"
            )
            tables = [row[0] for row in cursor.fetchall()]

            if not tables:
                conn.close()
                raise ValueError(f"SQLite database '{input_path}' contains no tables.")

            table_name = tables[0]
            df = pd.read_sql(f"SELECT * FROM [{table_name}]", conn)
            conn.close()
        except (sqlite3.Error, ValueError) as exc:
            raise RuntimeError(
                f"Failed to read SQLite '{input_path}': {exc}"
            ) from exc
        return df, table_name

    raise ValueError(
        f"Unsupported file type '{suffix}'. "
        "Expected .csv, .sqlite, .db, or .sqlite3."
    )


# ---------------------------------------------------------------------------
# Per-column stats
# ---------------------------------------------------------------------------

def _safe_scalar(value: Any) -> Any:
    """Convert numpy scalars to native Python types for JSON serialisation."""
    if value is None:
        return None
    # pandas NA / NaT
    if pd.isna(value):
        return None
    # numpy int / float → Python int / float
    if hasattr(value, "item"):
        return value.item()
    return value


def _profile_column(series: pd.Series) -> ColumnProfile:
    """Compute statistics for a single pandas Series (column)."""

    total_rows = len(series)
    null_count = int(series.isnull().sum())
    null_rate = null_count / total_rows if total_rows > 0 else 0.0
    is_all_null = null_count == total_rows

    non_null = series.dropna()
    distinct_count = int(non_null.nunique())

    inferred_dtype = _infer_dtype_label(series)

    # min / max — skip for all-null or string columns (not meaningful for BI)
    min_value: Any = None
    max_value: Any = None

    if not is_all_null and inferred_dtype not in ("string", "unknown"):
        try:
            min_value = _safe_scalar(non_null.min())
            max_value = _safe_scalar(non_null.max())
        except (TypeError, ValueError):
            # Mixed content that pandas didn't catch — leave as None
            pass

    # Up to 5 non-null samples
    sample_raw = non_null.head(5).tolist()
    sample_values = [_safe_scalar(v) for v in sample_raw]

    return ColumnProfile(
        inferred_dtype=inferred_dtype,
        null_count=null_count,
        null_rate=round(null_rate, 6),
        distinct_count=distinct_count,
        min_value=min_value,
        max_value=max_value,
        sample_values=sample_values,
        is_all_null=is_all_null,
    )


# ---------------------------------------------------------------------------
# Column name sanitisation (spaces in names)
# ---------------------------------------------------------------------------

def _sanitise_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace from column names.

    We do not rename or split columns — we preserve the original names
    in the profile so downstream SQL generators can quote them properly.
    Stripping whitespace only prevents invisible key mismatches.
    """
    df.columns = [str(col).strip() for col in df.columns]
    return df


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------

def run_profiler(state: AgentState) -> AgentState:
    """LangGraph node: load input file and compute DataProfile.

    Mutates state.data_profile and appends to state.errors on failure.
    Always returns state so the graph can continue or branch on errors.
    """
    input_path = state.input_path

    # --- Load ---
    try:
        df, table_name = _load_file(input_path)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        state.errors.append(f"Profiler load error: {exc}")
        return state

    # --- Sanitise column names ---
    df = _sanitise_column_names(df)

    # --- Build per-column profiles ---
    column_profiles: dict[str, ColumnProfile] = {}
    for col in df.columns:
        try:
            column_profiles[col] = _profile_column(df[col])
        except Exception as exc:          # noqa: BLE001 — safety net per column
            state.errors.append(f"Profiler column error [{col}]: {exc}")
            # Insert a placeholder so downstream nodes still see the column
            column_profiles[col] = ColumnProfile(
                inferred_dtype="unknown",
                null_count=0,
                null_rate=0.0,
                distinct_count=0,
                is_all_null=False,
            )

    row_count = len(df)

    profile = DataProfile(
        source_path=str(Path(input_path).resolve()),
        source_table=table_name,
        row_count=row_count,
        column_count=len(df.columns),
        is_single_row=(row_count == 1),
        columns=column_profiles,
    )

    state.data_profile = profile
    return state