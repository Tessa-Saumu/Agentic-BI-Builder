"""
agent/models.py — Pydantic models for the Agentic BI Builder pipeline.

DataProfile is the output of the Profiler node and the input contract
for all downstream nodes (Planner, SQL Generator, PBIR Compiler).
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


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


class DomainHypothesis(BaseModel):
    """LLM's inference of the dataset's business domain."""

    domain: str = Field(
        description="Short business-domain label, e.g. 'e-commerce retail', 'HR/payroll'."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Model's confidence in the domain label, from 0.0 to 1.0.",
    )
    reasoning: str = Field(
        description="Brief explanation of which profile signals led to this domain label."
    )


class KPISpec(BaseModel):
    """A single proposed KPI: definition, SQL, and chart mapping."""

    name: str = Field(description="Short KPI name, e.g. 'Average Order Value'.")
    description: str = Field(description="One or two sentences on what the KPI measures and why it matters.")
    sql_query: str = Field(
        description="A single valid SQLite SELECT statement computing this KPI. "
                    "Must reference only column names present in the DataProfile."
    )
    chart_type: Literal["card", "barChart", "lineChart", "table"] = Field(
        description="Recommended Power BI visual type for displaying this KPI's result."
    )
    reasoning: str = Field(
        description="Brief explanation of why this KPI and this chart type were chosen."
    )

    @field_validator("sql_query")
    @classmethod
    def _must_look_like_select(cls, v: str) -> str:
        stripped = v.strip().rstrip(";").strip()
        if not stripped.lower().startswith("select"):
            raise ValueError("sql_query must be a SELECT statement")
        return stripped


class DomainKPIResponse(BaseModel):
    """Full structured response expected from the Domain/KPI LLM call."""

    domain_hypothesis: DomainHypothesis
    kpi_specs: list[KPISpec] = Field(description="Exactly five proposed KPIs.")

    @field_validator("kpi_specs")
    @classmethod
    def _exactly_five(cls, v: list[KPISpec]) -> list[KPISpec]:
        if len(v) != 5:
            raise ValueError(f"Expected exactly 5 KPISpec objects, got {len(v)}")
        return v