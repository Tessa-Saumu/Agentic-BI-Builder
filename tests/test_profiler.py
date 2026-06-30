"""
tests/test_profiler.py — Unit tests for agent/profiler.py

Run with:
    pytest tests/test_profiler.py -v

Test suite covers:
    1. Normal CSV                   — happy path, basic stats correct
    2. All-null column              — flagged correctly, not dropped
    3. Single-row file              — is_single_row=True, stats still valid
    4. SQLite input                 — loads first table, profiles correctly
    5. Spaces in column names       — names stripped, profile keys are clean
    6. Mixed-type column            — labelled 'string', no crash
    7. File not found               — error appended to state, no crash
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Minimal AgentState stub so tests are independent of the full graph.
# Replace this import with your real AgentState once you confirm
# the field names match (input_path, output_path, data_profile, errors).
# ---------------------------------------------------------------------------
try:
    from agent.state import AgentState
except ImportError:
    # Fallback stub — remove once agent/state.py is confirmed
    from dataclasses import dataclass, field
    from typing import Any

    @dataclass
    class AgentState:  # type: ignore[no-redef]
        input_path: str = ""
        output_path: str = ""
        data_profile: Any = None
        errors: list[str] = field(default_factory=list)


from agent.profiler import run_profiler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(input_path: str) -> AgentState:
    return AgentState(input_path=input_path, output_path="output/test")


def _write_csv(df: pd.DataFrame, directory: Path) -> str:
    path = directory / "test.csv"
    df.to_csv(path, index=False)
    return str(path)


def _write_sqlite(df: pd.DataFrame, table: str, directory: Path) -> str:
    path = directory / "test.sqlite"
    conn = sqlite3.connect(path)
    df.to_sql(table, conn, if_exists="replace", index=False)
    conn.close()
    return str(path)


# ---------------------------------------------------------------------------
# Test 1 — Normal CSV
# ---------------------------------------------------------------------------

def test_normal_csv():
    """Happy path: a standard CSV with mixed dtypes profiles correctly."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "name": ["Alice", "Bob", "Carol", "Dave", "Eve"],
            "score": [88.5, 92.0, 75.3, None, 60.0],
            "active": [True, False, True, True, False],
        }
    )

    with tempfile.TemporaryDirectory() as tmp:
        state = _make_state(_write_csv(df, Path(tmp)))
        result = run_profiler(state)

    assert result.data_profile is not None, "data_profile should be set"
    assert result.errors == [], f"Unexpected errors: {result.errors}"

    profile = result.data_profile
    assert profile.row_count == 5
    assert profile.column_count == 4
    assert not profile.is_single_row

    # id column
    assert profile.columns["id"].inferred_dtype == "integer"
    assert profile.columns["id"].null_count == 0
    assert profile.columns["id"].null_rate == 0.0

    # score column has one null
    assert profile.columns["score"].null_count == 1
    assert profile.columns["score"].null_rate == pytest.approx(0.2, abs=1e-6)
    assert profile.columns["score"].inferred_dtype == "float"

    # name column
    assert profile.columns["name"].inferred_dtype == "string"
    assert len(profile.columns["name"].sample_values) == 5


# ---------------------------------------------------------------------------
# Test 2 — All-null column
# ---------------------------------------------------------------------------

def test_all_null_column():
    """All-null column must be profiled (not dropped) and flagged."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "empty": [None, None, None],
            "value": [10, 20, 30],
        }
    )

    with tempfile.TemporaryDirectory() as tmp:
        state = _make_state(_write_csv(df, Path(tmp)))
        result = run_profiler(state)

    profile = result.data_profile
    assert "empty" in profile.columns, "All-null column must still appear in profile"

    empty_col = profile.columns["empty"]
    assert empty_col.is_all_null is True
    assert empty_col.null_count == 3
    assert empty_col.null_rate == pytest.approx(1.0)
    assert empty_col.min_value is None
    assert empty_col.max_value is None
    assert empty_col.sample_values == []

    # Other columns unaffected
    assert profile.columns["id"].null_count == 0
    assert profile.column_count == 3


# ---------------------------------------------------------------------------
# Test 3 — Single-row file
# ---------------------------------------------------------------------------

def test_single_row_file():
    """A file with exactly one data row sets is_single_row=True."""
    df = pd.DataFrame({"a": [42], "b": ["hello"]})

    with tempfile.TemporaryDirectory() as tmp:
        state = _make_state(_write_csv(df, Path(tmp)))
        result = run_profiler(state)

    profile = result.data_profile
    assert profile.row_count == 1
    assert profile.is_single_row is True
    assert result.errors == []

    # Stats should still be valid
    assert profile.columns["a"].null_count == 0
    assert profile.columns["a"].distinct_count == 1
    assert profile.columns["a"].sample_values == [42]


# ---------------------------------------------------------------------------
# Test 4 — SQLite input
# ---------------------------------------------------------------------------

def test_sqlite_input():
    """SQLite database: first table is loaded and profiled correctly."""
    df = pd.DataFrame(
        {
            "customer_id": [101, 102, 103],
            "country": ["Kenya", "Nigeria", "Ghana"],
            "total_spent": [250.0, 480.5, None],
        }
    )

    with tempfile.TemporaryDirectory() as tmp:
        state = _make_state(_write_sqlite(df, "customers", Path(tmp)))
        result = run_profiler(state)

    assert result.errors == []
    profile = result.data_profile
    assert profile.source_table == "customers"
    assert profile.row_count == 3
    assert profile.column_count == 3

    # One null in total_spent
    assert profile.columns["total_spent"].null_count == 1
    assert profile.columns["total_spent"].null_rate == pytest.approx(1 / 3, abs=1e-4)


# ---------------------------------------------------------------------------
# Test 5 — Spaces in column names
# ---------------------------------------------------------------------------

def test_column_names_with_spaces():
    """Column names with leading/trailing spaces are stripped in the profile."""
    df = pd.DataFrame(
        {
            "  product name  ": ["Widget", "Gadget"],
            "price ": [9.99, 14.99],
        }
    )

    with tempfile.TemporaryDirectory() as tmp:
        state = _make_state(_write_csv(df, Path(tmp)))
        result = run_profiler(state)

    profile = result.data_profile
    # Keys must be the stripped versions
    assert "product name" in profile.columns, (
        f"Expected 'product name', got keys: {list(profile.columns.keys())}"
    )
    assert "price" in profile.columns
    assert result.errors == []


# ---------------------------------------------------------------------------
# Test 6 — Mixed-type column
# ---------------------------------------------------------------------------

def test_mixed_type_column():
    """A column with mixed types (pandas object dtype) is labelled 'string'."""
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            # Mixed: integers stored as strings alongside actual strings
            "mixed": ["100", "hello", "200"],
        }
    )

    with tempfile.TemporaryDirectory() as tmp:
        state = _make_state(_write_csv(df, Path(tmp)))
        result = run_profiler(state)

    assert result.errors == []
    assert result.data_profile.columns["mixed"].inferred_dtype == "string"


# ---------------------------------------------------------------------------
# Test 7 — File not found
# ---------------------------------------------------------------------------

def test_file_not_found():
    """Missing input file appends an error to state; data_profile stays None."""
    state = _make_state("/nonexistent/path/data.csv")
    result = run_profiler(state)

    assert result.data_profile is None
    assert len(result.errors) == 1
    assert "not found" in result.errors[0].lower()