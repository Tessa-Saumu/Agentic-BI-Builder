"""
PBIR Compiler node -- takes validated KPI results from AgentState,
maps them to PBIRProject Pydantic models, and (via the serialiser,
called separately) writes the full .pbip folder structure to disk.

Scope (mentor-confirmed, minimal): single data table per dataset, CSV
source only. No relationships, no auto-generated date tables, no
hierarchies, no full TMDL generality, no deep visual configurability --
one fixed template per chart type with bindings substituted in.

REFACTORED: this module previously contained three
sections inline (SQL -> DAX translation; page-grouping/canvas layout;
builder orchestration) totaling ~1300 LOC. The first two sections have
been extracted verbatim into their own modules --
pbir/compiler/sql_to_dax.py and pbir/compiler/layout.py -- leaving this
file as the orchestration layer only: run_pbir_compiler() and its
direct helpers (_build_columns, _build_measures_and_group_cols,
_build_visuals, _dedupe_trailing_by_phrase, _derive_report_name).

No logic changed as part of this split -- every function body moved
unmodified; only its containing file changed. All names that were
previously importable from this module (translate, translate_multi,
extract_group_by_column, SQLToDaxError, group_into_pages, layout_page)
remain importable from here via the re-export below, so
`from pbir.compiler.builder import translate` (etc.) continues to work
exactly as before for any existing caller or test -- see
tests/test_pbir_compiler.py, which imports all of these names directly
from this module.
"""
from __future__ import annotations

import re

from agent.state import AgentState
from agent.models import DataProfile, KPISpec, QueryResult

from pbir.models.column import Column
from pbir.models.measure import Measure
from pbir.models.table import DataTable
from pbir.models.visual import Visual
from pbir.models.page import Page
from pbir.models.project import PBIRProject
from pbir.models.common import page_slug, visual_slug

from pbir.models.dtypes import map_dtype

from pbir.compiler.sql_to_dax import (
    SQLToDaxError,
    DaxTranslation,
    translate,
    translate_multi,
    extract_group_by_column,
)
from pbir.compiler.layout import group_into_pages, layout_page

__all__ = [
    "SQLToDaxError",
    "DaxTranslation",
    "translate",
    "translate_multi",
    "extract_group_by_column",
    "group_into_pages",
    "layout_page",
    "run_pbir_compiler",
]


def _build_columns(profile: DataProfile) -> list[Column]:
    """One Column per DataProfile column, per §2.12's dtype mapping."""
    columns: list[Column] = []
    for name, col_profile in profile.columns.items():
        mapping = map_dtype(
            col_profile.inferred_dtype,
            column_name=name,
            distinct_count=col_profile.distinct_count,
        )
        columns.append(
            Column(
                name=name,
                data_type=mapping.dax_type,
                source_column=name,
                summarize_by=mapping.default_summarize_by,
            )
        )
    return columns


def _build_measures_and_group_cols(
    kpi_specs: list[KPISpec],
    query_results: list[QueryResult],
    table_name: str,
    errors: list[str],
) -> tuple[dict[str, list[Measure]], dict[str, str | None]]:
    """
    For each passing QueryResult (cross-referenced with its KPISpec by
    kpi_name), translate its SQL into one or more Measure objects.

    Returns:
      - measures_by_kpi: kpi_name -> list[Measure] (usually length 1; length
        >1 only for table-type KPIs with multiple aggregate output columns)
      - group_col_by_kpi: kpi_name -> the GROUP BY column name for charts/
        tables, or None for card-type single-value KPIs

    KPIs whose SQL can't be translated are recorded in `errors` and excluded
    from the return dicts entirely -- they simply don't get a Visual built
    for them downstream.
    """
    kpi_by_name = {k.name: k for k in kpi_specs}
    measures_by_kpi: dict[str, list[Measure]] = {}
    group_col_by_kpi: dict[str, str | None] = {}

    for result in query_results:
        if result.status != "pass":
            continue
        kpi = kpi_by_name.get(result.kpi_name)
        if kpi is None:
            errors.append(
                f"QueryResult {result.kpi_name!r} has no matching KPISpec; skipping."
            )
            continue

        group_col = extract_group_by_column(result.sql_query)

        try:
            if kpi.chart_type == "table":
                # Table visuals may legitimately carry multiple measures.
                translations = translate_multi(result.sql_query, table_name)
            else:
                translations = [translate(result.sql_query, table_name)]
        except SQLToDaxError as e:
            errors.append(f"KPI {result.kpi_name!r}: {e}")
            continue

        measures = []
        for i, t in enumerate(translations):
            # Disambiguate multi-measure names for table KPIs; single-measure
            # KPIs just use the KPI's own name.
            measure_name = kpi.name if len(translations) == 1 else f"{kpi.name} ({t.source_column})"
            if t.is_percentage:
                fmt = "0.00\\%"
            elif t.is_currency:
                fmt = "\\$#,0.00"
            elif t.aggregation in ("COUNT", "COUNTROWS"):
                fmt = "0"
            else:
                fmt = "0.00"
            measures.append(
                Measure(
                    name=measure_name,
                    expression=t.expression,
                    format_string=fmt,
                    is_currency=t.is_currency,
                )
            )

        measures_by_kpi[result.kpi_name] = measures
        group_col_by_kpi[result.kpi_name] = group_col

    return measures_by_kpi, group_col_by_kpi


# DEFENSIVE FIX (2026-07-15): observed once in Desktop as a rendered visual
# title reading "Average Monthly Income by Department by Department" -- an
# LLM-generated KPI name (agent/domain_kpi.py's SYSTEM_PROMPT explicitly
# models "by <dimension>" as good KPI-name phrasing, e.g. its own worked
# example "Total Revenue by Country") appears to have collided with Power
# BI Desktop's own category-axis title convention for grouped visuals,
# producing a doubled "by X" in the rendered title text.
#
# IMPORTANT -- this was NOT reproduced against any of the 3 uploaded KPI
# JSON files (chinook/hr/online_retail): none of their 15 KPI names contain
# this duplication, and the closest name in hr_kpis.json is "Average
# Monthly Income by Job Role" (grouped by Job Role, not Department) -- a
# different KPI than the one in the report. The observed bug therefore
# came from a different LLM generation run than any sample available here.
# Since domain_kpi.py's kpi.name is free-form LLM text with no code-level
# template that appends "by <group>" (confirmed by reading that module end
# to end -- result.kpi_specs passes through run_domain_kpi() unmodified),
# this can't be fixed by removing a concatenation step, because there isn't
# one to remove. What CAN be done here, defensively, without knowing the
# exact triggering name: guard the one place a KPI name becomes a visual's
# DISPLAYED title against this specific shape, in case the LLM (or a future
# run) produces a name that already ends in the same "by <phrase>" twice.
#
# Scope, deliberately narrow:
#   - Touches ONLY the `title` field written to Visual -- never `visual_id`
#     (still built from the untouched kpi.name via visual_slug(), whose
#     internals aren't available here to inspect -- see the fixes-log
#     precedent with filter_id() for why an unfamiliar ID-generation
#     helper's input shouldn't be changed without visibility into it),
#     never `measure_ref`, and never the `measures_by_kpi` /
#     `group_col_by_kpi` dict lookups two lines above and below this
#     change -- all of those still key off kpi.name exactly as before, so
#     no measure/category binding can be affected by this.
#   - Only collapses an EXACT trailing repeat ("...by X by X", case-
#     insensitive) -- verified against a 20-case suite covering every real
#     KPI name across all 3 uploaded JSON files plus synthetic edge cases
#     (triple repeats, trailing whitespace, a "Nearby" word-boundary trap,
#     empty string) before being wired in here. A name with two DIFFERENT
#     trailing "by" phrases (e.g. "Revenue by Country by Region") is
#     provably left untouched -- confirmed in that same test suite -- since
#     that's a legitimate two-level grouping, not a duplication bug.
#   - Applied via a small standalone helper (_dedupe_trailing_by_phrase),
#     not inlined, so it can be unit-tested in isolation the same way this
#     module's other fixes (7.1a/7.1b, the CASE WHEN work) already are.
_TRAILING_BY_DUP_RE = re.compile(
    r"""^(?P<base>.*\bby\s+(?P<phrase>.+?))\s+by\s+(?P=phrase)\s*$""",
    re.IGNORECASE,
)


def _dedupe_trailing_by_phrase(name: str) -> str:
    """
    Collapses an exact trailing "by <phrase> by <phrase>" repeat (case-
    insensitive match; the kept copy's original casing is preserved) down
    to a single "by <phrase>". Applied in a loop so a triple-or-higher
    repeat fully collapses rather than leaving one duplicate behind. Any
    name without this exact trailing-duplicate shape -- including a name
    with two DIFFERENT "by X" / "by Y" phrases -- is returned completely
    unchanged. See the FIX note above this function for the incident that
    prompted it and the test suite it was verified against.
    """
    current = name.strip()
    while True:
        m = _TRAILING_BY_DUP_RE.match(current)
        if not m:
            return current
        current = m.group("base")


def _build_visuals(
    kpi_specs: list[KPISpec],
    measures_by_kpi: dict[str, list[Measure]],
    group_col_by_kpi: dict[str, str | None],
    table_name: str,
) -> list[Visual]:
    """One Visual per KPI that has at least one successfully-built measure."""
    visuals: list[Visual] = []
    for kpi in kpi_specs:
        measures = measures_by_kpi.get(kpi.name)
        if not measures:
            continue

        # For single-measure visuals, measure_ref is that one measure's name.
        # For table KPIs with multiple measures, we still record the first as
        # measure_ref (used e.g. for the field list / primary binding) but
        # the serialiser is responsible for emitting all sibling measures.
        visuals.append(
            Visual(
                visual_id=visual_slug(kpi.name, kpi.chart_type),
                chart_type=kpi.chart_type,
                title=_dedupe_trailing_by_phrase(kpi.name),
                measure_ref=measures[0].name,
                category_ref=group_col_by_kpi.get(kpi.name),
                entity=table_name,
            )
        )
    return visuals


def _derive_report_name(profile: DataProfile) -> str:
    """
    source_table is the natural report name for a SQLite-backed dataset
    (e.g. "Invoice"). For a CSV-backed dataset, source_table is None (per
    agent/models.py's own docstring), so fall back to the CSV's filename
    stem -- e.g. "data\\raw\\hr.csv" -> "hr" -- rather than the generic
    literal "report", so multiple compiled datasets don't collide on the
    same output folder name.
    """
    if profile.source_table:
        return profile.source_table
    stem = profile.source_path.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    return stem or "report"


def run_pbir_compiler(state: AgentState) -> AgentState:
    if state.data_profile is None:
        state.errors.append("PBIR compiler: state.data_profile is required but was None.")
        return state

    profile: DataProfile = state.data_profile
    table_name = profile.source_table or "data"

    columns = _build_columns(profile)

    measures_by_kpi, group_col_by_kpi = _build_measures_and_group_cols(
        state.kpi_specs, state.query_results, table_name, state.errors
    )

    # Flatten all measures (across all KPIs, including multi-measure table
    # KPIs) into the table's measure list.
    all_measures: list[Measure] = []
    for measures in measures_by_kpi.values():
        all_measures.extend(measures)

    visuals = _build_visuals(state.kpi_specs, measures_by_kpi, group_col_by_kpi, table_name)

    # ACCEPTANCE THRESHOLD (2026-07-12): per the project's own acceptance
    # criteria ("at least two pages and at least four visuals"), a build
    # producing fewer than MIN_VISUALS_REQUIRED translatable KPIs does not
    # satisfy the deliverable, even though each individual KPI failure was
    # already handled gracefully above (dropped, not hard-failed). This is
    # a deliberate, mentor-agreed design: untranslatable SQL for ANY
    # individual KPI is fine and expected -- it's dropped, not fatal -- but
    # if too FEW KPIs survive translation overall, the resulting report
    # would not meet the project's own bar for a working dashboard, so the
    # whole build is rejected rather than silently shipping a thin report.
    MIN_VISUALS_REQUIRED = 4

    if len(visuals) < MIN_VISUALS_REQUIRED:
        state.errors.append(
            f"PBIR compiler: only {len(visuals)} KPI(s) produced a translatable "
            f"measure (minimum {MIN_VISUALS_REQUIRED} required to meet the "
            f"project's visual-count acceptance criterion); no .pbip built."
        )
        return state

    data_table = DataTable(
        name=table_name,
        columns=columns,
        measures=all_measures,
        source_csv_path=profile.source_path,
    )

    pages: list[Page] = []
    for i, page_visuals in enumerate(group_into_pages(visuals), start=1):
        layout_page(page_visuals)
        display_name = (
            page_visuals[0].title if len(page_visuals) == 1 else f"Overview {i}"
        )
        pages.append(
            Page(
                page_id=page_slug(display_name, i),
                display_name=display_name,
                visuals=page_visuals,
            )
        )

    project = PBIRProject(
        report_name=_derive_report_name(profile),
        pages=pages,
        data_table=data_table,
        source_path=profile.source_path,
        source_table=table_name,
    )

    state.pbir_project = project
    return state