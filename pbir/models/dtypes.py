"""
pbir/models/dtypes.py — single source of truth for dtype translation.

The Profiler's `inferred_dtype` string (agent/models.py ColumnProfile) needs
to become THREE different things in the compiled output, and per
pbir_reference.md §2.12 these must all be driven by the same mapping table
rather than re-derived ad hoc in three places:

  1. TMDL `column.dataType`      (dateTime | string | int64 | decimal)
  2. Power Query M `Table.TransformColumnTypes` type literal
  3. TMDL `column.summarizeBy`   (none | sum)

Only 'integer', 'float', 'string', 'datetime' are handled richly per the
reference doc's observed enum. 'boolean' and 'unknown' from
agent/models.py's ColumnProfile are mapped to safe string-like fallbacks
since they weren't reverse-engineered in the reference doc.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DTypeMapping:
    dax_type: str          # TMDL column dataType
    m_type_literal: str     # Power Query M type literal for TransformColumnTypes
    default_summarize_by: str  # TMDL column summarizeBy


_DTYPE_TABLE: dict[str, DTypeMapping] = {
    "integer": DTypeMapping("int64", "Int64.Type", "sum"),
    "float": DTypeMapping("decimal", "type number", "sum"),
    "string": DTypeMapping("string", "type text", "none"),
    "datetime": DTypeMapping("dateTime", "type datetime", "none"),
    # Not covered by the reference doc's observed samples; safe fallbacks.
    "boolean": DTypeMapping("string", "type text", "none"),
    "unknown": DTypeMapping("string", "type text", "none"),
}

# Column-name suffixes that indicate a surrogate/foreign key rather than a
# genuinely additive quantity. Not part of the reference doc -- a practical
# correctness fix, since defaulting an *Id column's summarizeBy to "sum"
# produces a nonsensical "Sum of CustomerId" in Power BI's field list.
_ID_LIKE_SUFFIXES = ("id", "key", "code")

# Below this many distinct values, an integer column is treated as
# categorical/ordinal (ratings, levels, flags -- e.g. a 1-4 satisfaction
# score, JobLevel 1-5, StockOptionLevel 0-3) rather than a genuinely
# additive quantity, and summarizeBy defaults to "none" instead of "sum".
# Not part of the reference doc -- name-suffix matching alone (Id/Key/Code)
# misses this whole category, since these columns don't share a naming
# convention; distinct_count from DataProfile is a more principled signal
# than guessing from the name.
_LOW_CARDINALITY_THRESHOLD = 10


def _looks_like_id_column(column_name: str) -> bool:
    lowered = column_name.lower()
    return any(lowered.endswith(suffix) for suffix in _ID_LIKE_SUFFIXES)


def map_dtype(
    inferred_dtype: str,
    column_name: str | None = None,
    distinct_count: int | None = None,
) -> DTypeMapping:
    """
    Map a Profiler ColumnProfile.inferred_dtype string to its DAX/M/summarizeBy
    triple. Falls back to 'string' treatment for anything unrecognized rather
    than raising, since an unexpected dtype label shouldn't hard-fail the
    whole compiler -- it'll just be treated conservatively as text.

    summarizeBy is forced to "none" (regardless of dtype) when either:
      - column_name looks like an ID/key column (ends in Id/Key/Code), or
      - distinct_count is given and below _LOW_CARDINALITY_THRESHOLD, which
        catches ordinal/rating/level columns (JobSatisfaction 1-4, JobLevel
        1-5, etc.) that don't share an ID-like name but are equally wrong
        to auto-sum.
    """
    mapping = _DTYPE_TABLE.get(inferred_dtype, _DTYPE_TABLE["unknown"])
    if mapping.default_summarize_by != "sum":
        return mapping

    is_id_like = bool(column_name) and _looks_like_id_column(column_name)
    is_low_cardinality = distinct_count is not None and distinct_count < _LOW_CARDINALITY_THRESHOLD

    if is_id_like or is_low_cardinality:
        return DTypeMapping(mapping.dax_type, mapping.m_type_literal, "none")
    return mapping


def dax_type_to_m_type(dax_type: str) -> str:
    """Public accessor: DAX column dataType -> M TransformColumnTypes literal."""
    for mapping in _DTYPE_TABLE.values():
        if mapping.dax_type == dax_type:
            return mapping.m_type_literal
    return "type text"


def is_date_column(inferred_dtype: str) -> bool:
    return inferred_dtype == "datetime"