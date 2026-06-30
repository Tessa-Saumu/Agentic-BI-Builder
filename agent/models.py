"""
agent/models.py — Pydantic models for the Agentic BI Builder pipeline.

DataProfile is the output of the Profiler node and the input contract
for all downstream nodes (Planner, SQL Generator, PBIR Compiler).
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    """Profile for a single column in the dataset."""

    inferred_dtype: str = Field(
        description="Human-readable dtype label: 'integer', 'float', 'string', "
                    "'boolean', 'datetime', or 'unknown'."
    )
    null_count: int = Field(description="Number of null / NaN values.")
    null_rate: float = Field(description="Fraction of rows that are null (0.0 – 1.0).")
    distinct_count: int = Field(description="Number of unique non-null values.")
    min_value: Any = Field(default=None, description="Minimum value, or None if all-null.")
    max_value: Any = Field(default=None, description="Maximum value, or None if all-null.")
    sample_values: list[Any] = Field(
        default_factory=list,
        description="Up to 5 non-null sample values for downstream LLM context.",
    )
    is_all_null: bool = Field(
        default=False,
        description="True when every value in this column is null.",
    )


class DataProfile(BaseModel):
    """Full schema profile of the loaded dataset."""

    source_path: str = Field(description="Path to the input file, relative to the project root.")
    source_table: str | None = Field(
        default=None,
        description="Table name (SQLite only). None for CSV inputs.",
    )
    row_count: int = Field(description="Total number of rows in the dataset.")
    column_count: int = Field(description="Total number of columns.")
    is_single_row: bool = Field(
        default=False,
        description="True when the dataset has exactly one data row.",
    )
    columns: dict[str, ColumnProfile] = Field(
        description="Mapping of column name → ColumnProfile."
    )