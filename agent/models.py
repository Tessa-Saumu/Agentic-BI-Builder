"""
agent/models.py — Pydantic models for the Agentic BI Builder pipeline.

DataProfile is the output of the Profiler node and the input contract
for all downstream nodes (Planner, SQL Generator, PBIR Compiler).
"""

from __future__ import annotations

from typing import Any, Literal, Optional
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


# Cap on how many result rows are retained per QueryResult. Full result sets
# can be large (e.g. revenue-by-customer across thousands of customers) and
# don't need to be fully materialized for the Reflector's prompt or a log
# file — a representative sample is enough to judge null-heaviness or
# implausible values.
MAX_RESULT_ROWS_STORED = 20


class QueryResult(BaseModel):
    """Outcome of executing a single KPISpec's sql_query against real data."""

    kpi_name: str = Field(description="Matches the KPISpec.name this result belongs to.")
    sql_query: str = Field(
        description="The exact SQL that was executed to produce this result "
                    "(post-fix, if this is a retry)."
    )
    status: Literal["pass", "fail"] = Field(
        description="'pass' if the query executed without error, 'fail' otherwise. "
                    "An empty result set is still a 'pass' — zero rows is not an error."
    )
    row_count: int = Field(default=0, description="Total rows returned by the query.")
    columns: list[str] = Field(
        default_factory=list, description="Column names in the result set, in order."
    )
    result_rows: list[dict] = Field(
        default_factory=list,
        description=f"Up to {MAX_RESULT_ROWS_STORED} result rows as records "
                    "(column name → value), for downstream inspection by the Reflector.",
    )
    error_message: Optional[str] = Field(
        default=None, description="SQL error text if status is 'fail'; None otherwise."
    )


class ReflectionNote(BaseModel):
    """A single issue the Reflector identified in one KPI's query or results."""

    kpi_name: str = Field(description="Matches the KPISpec.name / QueryResult.kpi_name being flagged.")
    issue_type: Literal["null_heavy", "wrong_aggregation", "implausible_result", "sql_error", "other"] = Field(
        description="Category of the identified issue. Use 'other' for a genuine issue that "
                    "doesn't fit the four specific categories (e.g. a duplicate KPI, a "
                    "misleading chart_type choice) — 'other' still gets reported and, if "
                    "fixable, retried, rather than being silently dropped."
    )
    description: str = Field(description="What is wrong and why, in plain terms.")
    fix_instruction: str = Field(
        description="Human-readable explanation of the fix, for logging/audit purposes."
    )
    fixed_sql_query: Optional[str] = Field(
        default=None,
        description="The corrected SQL query to retry with. None if the issue cannot "
                    "be fixed by changing the SQL (e.g. the underlying data is genuinely "
                    "null-heavy and no query rewrite would help) — such KPIs are dropped "
                    "without a retry.",
    )

    @field_validator("fixed_sql_query")
    @classmethod
    def _fixed_sql_must_be_select(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = v.strip().rstrip(";").strip()
        if not stripped.lower().startswith("select"):
            raise ValueError("fixed_sql_query must be a SELECT statement")
        return stripped


class ReflectionResponse(BaseModel):
    """Full structured response expected from the Reflector LLM call."""

    notes: list[ReflectionNote] = Field(
        default_factory=list,
        description="One entry per KPI with an identified issue. Empty list means "
                    "no issues were found across any KPI — a valid, good outcome.",
    )