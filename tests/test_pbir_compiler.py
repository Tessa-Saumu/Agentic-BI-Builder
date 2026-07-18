"""
tests/test_pbir_compiler.py -- the project's single unit/integration test
suite for the PBIR Compiler (agent/models.py, agent/state.py,
pbir/models/*, pbir/compiler/builder.py, pbir/compiler/serialiser.py).

FIXTURE STRATEGY: unit tests must primarily verify
this application's OWN behavior and stay independent of any particular
external package/data implementation. Concretely here that means: no
fixture in this file is built from a real dataset's KPI/profile JSON
(chinook, HR, online_retail, or any future one). Every fixture below is a
small, self-contained, INVENTED dataset -- synthetic column names, synthetic
KPI SQL -- chosen only to exercise a specific shape or code path in this
compiler. This keeps the suite from silently rotting every time an upstream
KPI-generation run changes its SQL style or a dataset's KPI file gets
regenerated (which has already happened once for real: see the SQL
normalization bug fixes below), and it means every test failure here points
at this application's own logic, never at "the fixture data changed."

Everything lives in this one file by design -- the project convention is a
single `test_pbir_compiler` suite, and there is no technical reason (pytest
fixtures, classes, and plain data can all coexist in one module) that would
force a split into separate fixture modules.

Structural checks only: folder tree shape, JSON validity, TMDL
tab-indentation, cross-file ID consistency, and the acceptance criteria's
countable properties (>=2 pages, >=4 visuals, measures present). "Opens in
Power BI Desktop without errors" is NOT something pytest can assert -- that
remains a manual verification step outside this suite.
"""
from __future__ import annotations

import json
import os
import re
import uuid

import pytest

from agent.models import ColumnProfile, DataProfile, KPISpec, QueryResult
from agent.state import AgentState
from pbir.compiler.builder import (
    SQLToDaxError,
    extract_group_by_column,
    group_into_pages,
    layout_page,
    run_pbir_compiler,
    translate,
    translate_multi,
)
from pbir.compiler.serialiser import (
    _build_m_partition_source,
    _build_table_tmdl,
    _local_filter_id,
    write_pbip,
)
from pbir.models.column import Column
from pbir.models.common import filter_id
from pbir.models.dtypes import dax_type_to_m_type, map_dtype
from pbir.models.visual import Visual


# =====================================================================
# Synthetic, dataset-agnostic fixture for the full-pipeline / serialiser
# tests below. Invented business domain ("regional activity tracking"),
# invented column names -- deliberately not sourced from, or matching,
# any real project dataset. Chosen to cover, in one small profile:
#   - a currency-shaped numeric column (Amount)          -> is_currency
#   - a row-unique Id-suffixed column (RecordId)          -> summarizeBy=none
#   - a low-cardinality integer "rating" column (PriorityLevel, 5 values)
#                                                          -> summarizeBy=none
#   - a plain low-cardinality string category (Region)
#   - a string-typed date-like column (SignupDate)        -> the real
#     "profiled as string, not datetime" edge case, generically
#   - a two-valued flag column (StatusFlag)                -> CASE WHEN
# and, across its 6 KPIs, all four chart types plus both SQL->DAX bug
# patterns fixed in this session (quoted identifiers; a ratio/percentage
# wrapped in redundant outer parens alongside co-selected raw counts).
# =====================================================================

SYNTHETIC_PROFILE = DataProfile(
    source_path="data/raw/synthetic_activity.csv",
    source_table=None,
    row_count=500,
    column_count=6,
    is_single_row=False,
    columns={
        "RecordId": ColumnProfile(inferred_dtype="integer", null_count=0, null_rate=0.0, distinct_count=500),
        "Region": ColumnProfile(inferred_dtype="string", null_count=0, null_rate=0.0, distinct_count=4),
        "PriorityLevel": ColumnProfile(inferred_dtype="integer", null_count=0, null_rate=0.0, distinct_count=5),
        "Amount": ColumnProfile(inferred_dtype="float", null_count=0, null_rate=0.0, distinct_count=480),
        "SignupDate": ColumnProfile(inferred_dtype="string", null_count=0, null_rate=0.0, distinct_count=310),
        "StatusFlag": ColumnProfile(inferred_dtype="string", null_count=0, null_rate=0.0, distinct_count=2),
    },
)

SYNTHETIC_KPI_SPECS = [
    KPISpec(
        name="Total Amount",
        description="Sum of Amount across all records.",
        sql_query="SELECT SUM(Amount) AS total FROM data",
        chart_type="card",
        reasoning="Single summary metric.",
    ),
    KPISpec(
        name="Amount by Region",
        description="Sum of Amount grouped by Region, using double-quoted identifiers.",
        sql_query='SELECT "Region", SUM("Amount") AS total FROM data GROUP BY "Region" ORDER BY total DESC',
        chart_type="barChart",
        # REGRESSION COVERAGE (bug 7.1a): ANSI double-quoted identifiers,
        # matching the quoting style a KPI-generation run has actually
        # produced for a real dataset -- exercised here through the full
        # pipeline (builder AND category_ref extraction), not just the
        # isolated translate() unit tests further down.
        reasoning="Regional comparison; deliberately double-quoted SQL identifiers.",
    ),
    KPISpec(
        name="Active Rate by Region",
        description="Percentage of Active records per Region, alongside supporting counts.",
        sql_query=(
            "SELECT Region, COUNT(*) AS total_records, "
            "SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) AS active_count, "
            "(SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) AS active_rate "
            "FROM data GROUP BY Region ORDER BY active_rate DESC"
        ),
        chart_type="barChart",
        # REGRESSION COVERAGE (bug 7.1b, GROUP BY variant): a percentage
        # expression wrapped in redundant outer parens, co-selected
        # alongside TWO other non-ratio aggregates (COUNT(*) and a bare
        # SUM(CASE...)) in the same GROUP BY query -- the exact shape that
        # silently dropped the rate expression before the fix.
        reasoning="Rate is the intended chart metric; counts are supporting context.",
    ),
    KPISpec(
        name="Overall Active Rate",
        description="Percentage of Active records overall.",
        sql_query=(
            "SELECT (SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) "
            "AS overall_rate FROM data"
        ),
        chart_type="card",
        # REGRESSION COVERAGE (bug 7.1b, no-GROUP-BY variant): the same
        # wrapped-ratio shape reaching _translate_core directly.
        reasoning="Single summary percentage metric.",
    ),
    KPISpec(
        name="Signup Trend",
        description="Record count by signup month.",
        sql_query="SELECT strftime('%Y-%m', SignupDate) AS month, COUNT(*) AS n FROM data GROUP BY month ORDER BY month",
        chart_type="lineChart",
        reasoning="Time trend; GROUP BY uses the SELECT alias, not the real column.",
    ),
    KPISpec(
        name="Priority Breakdown",
        description="Record count and average Amount per PriorityLevel.",
        sql_query="SELECT PriorityLevel, COUNT(*) AS n, AVG(Amount) AS avg_amount FROM data GROUP BY PriorityLevel",
        chart_type="table",
        reasoning="Two independent aggregates -- a genuine multi-measure table KPI.",
    ),
]

SYNTHETIC_QUERY_RESULTS = [
    QueryResult(kpi_name=k.name, sql_query=k.sql_query, status="pass", row_count=1, columns=[], result_rows=[])
    for k in SYNTHETIC_KPI_SPECS
]


@pytest.fixture
def synthetic_state() -> AgentState:
    return AgentState(
        input_path=SYNTHETIC_PROFILE.source_path,
        output_path="output/synthetic_report",
        data_profile=SYNTHETIC_PROFILE,
        kpi_specs=SYNTHETIC_KPI_SPECS,
        query_results=SYNTHETIC_QUERY_RESULTS,
    )


@pytest.fixture
def compiled_synthetic_project(synthetic_state):
    result_state = run_pbir_compiler(synthetic_state)
    assert result_state.errors == [], f"Builder produced errors: {result_state.errors}"
    assert result_state.pbir_project is not None
    return result_state.pbir_project


@pytest.fixture
def patched_theme_assets(tmp_path, monkeypatch):
    """
    write_pbip() copies 2 real Microsoft-shipped theme JSON files from
    serialiser._THEME_ASSETS_DIR (pbir_reference.md SS2.15: vendor them as
    static assets, never regenerate). This suite does not vendor the actual
    byte-verbatim Microsoft files -- that's an external asset to bundle at
    deploy time, not application logic to unit-test -- so tests substitute
    minimal placeholder JSON files in a temp dir for the duration of the
    test, only so write_pbip's file-copy step has something real to copy.
    This does not test theme file CONTENT, only that write_pbip performs
    the copy to the right destination path.
    """
    from pbir.compiler import serialiser

    assets_dir = tmp_path / "theme_assets"
    (assets_dir / "BaseThemes").mkdir(parents=True)
    (assets_dir / "BuiltInThemes").mkdir(parents=True)
    (assets_dir / "BaseThemes" / f"{serialiser._BASE_THEME_NAME}.json").write_text("{}")
    (assets_dir / "BuiltInThemes" / f"{serialiser._CUSTOM_THEME_NAME}.json").write_text("{}")
    # _theme_assets() reads _THEME_ASSETS_DIR as a module global at call
    # time (not a frozen default), so patching it here is picked up by
    # write_pbip's internal call without needing to touch write_pbip itself.
    monkeypatch.setattr(serialiser, "_THEME_ASSETS_DIR", assets_dir)
    return assets_dir


@pytest.fixture
def synthetic_output_dir(compiled_synthetic_project, patched_theme_assets, tmp_path):
    out = tmp_path / "synthetic_report_out"
    write_pbip(compiled_synthetic_project, out)
    return out


# =====================================================================
# Unit tests: SQL -> DAX translator (translate / translate_multi /
# extract_group_by_column / SQLToDaxError, in pbir/compiler/builder.py).
# Every SQL string below is hand-written for the shape it targets, using
# invented column names -- these do not exercise any dataset fixture.
# =====================================================================


class TestSQLToDaxSingleAggregate:
    def test_sum_card(self):
        t = translate("SELECT SUM(Amount) AS total FROM data", "data")
        assert t.expression == "SUM('data'[Amount])"
        assert t.aggregation == "SUM"
        assert t.source_column == "Amount"

    def test_avg(self):
        t = translate("SELECT AVG(UnitCost) AS avg_cost FROM data", "data")
        assert t.expression == "AVERAGE('data'[UnitCost])"
        assert t.aggregation == "AVERAGE"

    def test_count(self):
        t = translate("SELECT COUNT(RecordId) AS n FROM data", "data")
        assert t.expression == "COUNT('data'[RecordId])"
        assert t.aggregation == "COUNT"

    def test_currency_hint_detected(self):
        t = translate("SELECT SUM(Amount) AS total FROM data", "data")
        assert t.is_currency is True

    def test_non_currency_column(self):
        t = translate("SELECT COUNT(RecordId) AS n FROM data", "data")
        assert t.is_currency is False

    def test_grouped_chart_query(self):
        t = translate("SELECT Region, SUM(Amount) AS total FROM data GROUP BY Region ORDER BY total DESC", "data")
        assert t.expression == "SUM('data'[Amount])"

    def test_strftime_grouped_query(self):
        t = translate(
            "SELECT strftime('%Y-%m', SignupDate) AS month, SUM(Amount) AS total "
            "FROM data GROUP BY month ORDER BY month",
            "data",
        )
        assert t.expression == "SUM('data'[Amount])"


class TestSQLToDaxRatio:
    def test_divide_ratio(self):
        t = translate("SELECT SUM(Amount) / COUNT(RecordId) AS ratio FROM data", "data")
        assert t.expression == "DIVIDE(SUM('data'[Amount]), COUNT('data'[RecordId]))"
        assert t.aggregation == "DIVIDE"


class TestSQLToDaxRoundAndCountStar:
    def test_round_wraps_single_aggregate(self):
        t = translate("SELECT ROUND(AVG(UnitCost), 2) AS avg_cost FROM data", "data")
        assert t.expression == "ROUND(AVERAGE('data'[UnitCost]), 2)"
        assert t.aggregation == "ROUND"

    def test_round_wraps_grouped_aggregate(self):
        t = translate(
            "SELECT Region, ROUND(AVG(UnitCost), 2) AS avg_cost FROM data GROUP BY Region ORDER BY avg_cost DESC",
            "data",
        )
        assert t.expression == "ROUND(AVERAGE('data'[UnitCost]), 2)"

    def test_count_star_card(self):
        t = translate("SELECT COUNT(*) AS n FROM data", "data")
        assert t.expression == "COUNTROWS('data')"
        assert t.aggregation == "COUNTROWS"

    def test_round_wrapped_conditional_percentage_card(self):
        """
        Pre-existing shape (unaffected by the 7.1b fix below, which only
        adds handling for a BARE-paren wrap with no ROUND(...) call at
        all): a percentage explicitly wrapped in ROUND(...) already worked
        before this session's fixes, since _ROUND_WRAPPER_RE's own inner
        capture already unwraps it regardless of what's inside. Kept as a
        regression guard that the new _strip_enclosing_parens step
        (unconditionally run at the top of _translate_core) does not
        change this pre-existing, already-correct behavior.
        """
        t = translate(
            "SELECT ROUND(SUM(CASE WHEN StatusFlag = 'Active' THEN 1.0 ELSE 0.0 END) "
            "* 100.0 / COUNT(*), 2) AS rate FROM data",
            "data",
        )
        assert t.expression == (
            "ROUND(DIVIDE(COUNTROWS(FILTER('data', 'data'[StatusFlag] = \"Active\")), "
            "COUNTROWS('data')) * 100, 2)"
        )
        assert t.is_percentage is True

    def test_round_wrapped_conditional_percentage_alongside_count_star_in_group_by(self):
        """Same pre-existing ROUND-wrapped shape, in a GROUP BY query
        alongside a co-selected COUNT(*) -- also unaffected by 7.1b."""
        t = translate(
            "SELECT Region, COUNT(*) AS total_records, "
            "ROUND(SUM(CASE WHEN StatusFlag = 'Active' THEN 1.0 ELSE 0.0 END) * 100.0 "
            "/ COUNT(*), 2) AS rate FROM data GROUP BY Region ORDER BY rate DESC",
            "data",
        )
        assert "DIVIDE" in t.expression
        assert t.is_percentage is True


class TestSQLToDaxQuotedIdentifiers:
    """
    BUG FIX 7.1a regression coverage: a KPI-generation run used ANSI
    double-quoted identifiers (SUM("Total"), GROUP BY "BillingCountry")
    instead of bare ones. Every shape-matching regex in the translator
    expects a bare identifier; _normalize_identifiers strips the quotes
    once, up front, in translate/translate_multi/extract_group_by_column,
    so nothing downstream needs to change. Single-quoted string literals
    (real SQL string values) must never be touched by this.
    """

    def test_quoted_single_aggregate(self):
        t = translate('SELECT SUM("Amount") AS total FROM data', "data")
        assert t.expression == "SUM('data'[Amount])"

    def test_quoted_aggregate_currency_still_detected(self):
        """Confirms normalization happens before the (lowercased) currency
        hint check -- a quoted column name must still be recognized."""
        t = translate('SELECT SUM("Amount") AS total FROM data', "data")
        assert t.is_currency is True

    def test_quoted_grouped_aggregate(self):
        t = translate(
            'SELECT "Region", SUM("Amount") AS total FROM data GROUP BY "Region" ORDER BY total DESC',
            "data",
        )
        assert t.expression == "SUM('data'[Amount])"

    def test_quoted_group_by_column_extracted_bare(self):
        col = extract_group_by_column(
            'SELECT "Region", SUM("Amount") AS total FROM data GROUP BY "Region" ORDER BY total DESC'
        )
        assert col == "Region"

    def test_quoted_and_bare_identifiers_translate_identically(self):
        """Same query, two quoting styles -> identical DAX output."""
        quoted = translate('SELECT AVG("UnitCost") AS avg_cost FROM data', "data")
        bare = translate("SELECT AVG(UnitCost) AS avg_cost FROM data", "data")
        assert quoted.expression == bare.expression

    def test_single_quoted_string_literal_not_touched_by_normalization(self):
        """
        Double-quote normalization must never touch a single-quoted SQL
        string literal (a real comparison value, not an identifier) --
        confirmed via a WHERE-filtered, quoted-identifier query that still
        resolves the single-quoted comparison value correctly.
        """
        t = translate(
            'SELECT SUM("Amount") AS total FROM data WHERE StatusFlag = \'Active\'',
            "data",
        )
        assert "CALCULATE" in t.expression
        assert "\"Active\"" in t.expression or "'Active'" in t.expression


class TestSQLToDaxWrappedRatioExpressions:
    """
    BUG FIX 7.1b regression coverage: a ratio/percentage expression
    defensively wrapped in its own outer parens -- e.g.
    "(SUM(CASE WHEN col = 'val' THEN 1 ELSE 0 END) * 100.0 / COUNT(*))" --
    silently defeated every shape matcher (they expect the expression to
    start directly with SUM/AVG/COUNT, and the ratio's "/" ends up at
    paren-depth 1, not 0). _strip_enclosing_parens (used inside
    _translate_core) and _unwrap_item_parens (used when classifying a
    GROUP BY SELECT-list item) fix this centrally.
    """

    def test_wrapped_ratio_card_no_group_by(self):
        t = translate(
            "SELECT (SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) "
            "AS rate FROM data",
            "data",
        )
        assert t.aggregation == "DIVIDE"
        assert t.is_percentage is True
        assert "COUNTROWS(FILTER(" in t.expression

    def test_wrapped_ratio_matches_unwrapped_form_exactly(self):
        wrapped = translate(
            "SELECT (SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) "
            "AS rate FROM data",
            "data",
        )
        unwrapped = translate(
            "SELECT SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) "
            "AS rate FROM data",
            "data",
        )
        assert wrapped.expression == unwrapped.expression

    def test_double_wrapped_parens_still_unwrapped(self):
        """Recursion: more than one redundant layer must still be peeled."""
        t = translate(
            "SELECT ((SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) * 100.0 / COUNT(*))) "
            "AS rate FROM data",
            "data",
        )
        assert t.is_percentage is True

    def test_wrapped_ratio_alongside_two_supporting_counts_in_group_by(self):
        """
        The exact real-world shape that was broken: a GROUP BY query
        selecting a raw COUNT(*), a standalone SUM(CASE WHEN...), AND the
        wrapped percentage built from that same SUM -- three agg_items
        once unwrapped, only one of which is a ratio. Must resolve to the
        rate, not reject as "not exactly one aggregate expression".
        """
        t = translate(
            "SELECT Region, COUNT(*) AS total_records, "
            "SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) AS active_count, "
            "(SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) AS active_rate "
            "FROM data GROUP BY Region ORDER BY active_rate DESC",
            "data",
        )
        assert t.aggregation == "DIVIDE"
        assert t.is_percentage is True

    def test_non_redundant_arithmetic_still_rejected(self):
        """
        _strip_enclosing_parens only strips a wrap that spans the WHOLE
        expression; it must not make an unsupported shape (arithmetic
        other than a recognized ratio) suddenly "work" just because it
        happens to be paren-wrapped.
        """
        with pytest.raises(SQLToDaxError):
            translate("SELECT (SUM(Amount) + 1) AS total FROM data", "data")

    def test_partial_wrap_left_alone(self):
        """
        A "(" that closes in the MIDDLE of the expression (not at the very
        end) is not a redundant outer wrap and must not be stripped --
        e.g. "(SUM(Amount)) + (COUNT(RecordId))" is still two separately-
        wrapped terms added together, which remains unsupported.
        """
        with pytest.raises(SQLToDaxError):
            translate("SELECT (SUM(Amount)) + (COUNT(RecordId)) AS total FROM data", "data")

    def test_two_distinct_ratios_still_ambiguous_and_rejected(self):
        """
        The generalized "exactly one ratio among N agg_items" rule must
        still reject the genuinely ambiguous case of two DIFFERENT ratio
        expressions co-selected in one query -- there's no principled way
        to pick one over the other.
        """
        with pytest.raises(SQLToDaxError):
            translate(
                "SELECT Region, SUM(Amount) / COUNT(RecordId) AS avg1, "
                "SUM(UnitCost) / COUNT(RecordId) AS avg2 FROM data GROUP BY Region",
                "data",
            )


class TestSQLToDaxCaseWhenToIf:
    """
    GENERAL CASE WHEN -> DAX IF translation (2026-07-13): SQL's CASE WHEN is
    functionally SQL's IF -- IF has been on the approved basic-DAX list
    (SUM, AVERAGE, COUNT, DIVIDE, IF) since the start of the project, but
    until now the only recognized CASE WHEN shape was the narrow 0/1
    count-percentage idiom (see TestSQLToDaxRoundAndCountStar /
    TestSQLToDaxWrappedRatioExpressions above). This adds a general path
    for a single-condition CASE WHEN <cond> THEN <a> ELSE <b> END, whether
    bare, wrapped in SUM/AVG (a conditional aggregate, not a percentage),
    or wrapped in ROUND(...) -- via DAX's row-context iterator
    SUMX/AVERAGEX around a per-row IF(...), or a direct IF(...) with no
    iterator when there's no surrounding aggregation at all.

    Every SQL string below is hand-written for the shape it targets, using
    invented column names -- these do not exercise any dataset fixture.
    """

    def test_sum_wrapped_case_when_column_branches(self):
        """The canonical motivating example: a conditional SUM (not a
        percentage) where both THEN and ELSE are literal/column values."""
        t = translate(
            "SELECT SUM(CASE WHEN Amount > 50 THEN Amount ELSE 0 END) AS conditional_total FROM data",
            "data",
        )
        assert t.expression == "SUMX('data', IF('data'[Amount] > 50, 'data'[Amount], 0))"
        assert t.aggregation == "SUMX"

    def test_avg_wrapped_case_when(self):
        """AVERAGEX for consistency with SUMX, same as the pre-existing
        row-wise product support (SUM(a*b)/AVG(a*b))."""
        t = translate(
            "SELECT AVG(CASE WHEN Amount > 50 THEN Amount ELSE 0 END) AS avg_conditional FROM data",
            "data",
        )
        assert t.expression == "AVERAGEX('data', IF('data'[Amount] > 50, 'data'[Amount], 0))"
        assert t.aggregation == "AVERAGEX"

    def test_bare_case_when_no_surrounding_aggregate(self):
        """No SUM/AVG at all -- translates directly to IF(...), no
        row-context iterator needed."""
        t = translate(
            "SELECT CASE WHEN Region = 'North' THEN 1 ELSE 0 END AS is_north FROM data",
            "data",
        )
        assert t.expression == 'IF(\'data\'[Region] = "North", 1, 0)'
        assert t.aggregation == "IF"

    def test_numeric_comparison_operator(self):
        """A non-equality comparison operator (>=) against a numeric value,
        confirming _SQL_TO_DAX_OP's operator mapping is reused correctly."""
        t = translate(
            "SELECT SUM(CASE WHEN PriorityLevel >= 3 THEN Amount ELSE 0 END) AS high_priority_total FROM data",
            "data",
        )
        assert t.expression == (
            "SUMX('data', IF('data'[PriorityLevel] >= 3, 'data'[Amount], 0))"
        )

    def test_round_wrapped_case_when(self):
        """ROUND(...) wrapping a CASE-WHEN-based SUM -- composes with the
        pre-existing ROUND-unwrapping path exactly like every other
        _translate_core shape."""
        t = translate(
            "SELECT ROUND(SUM(CASE WHEN Amount > 50 THEN Amount ELSE 0 END), 2) AS rounded_total FROM data",
            "data",
        )
        assert t.expression == (
            "ROUND(SUMX('data', IF('data'[Amount] > 50, 'data'[Amount], 0)), 2)"
        )
        assert t.aggregation == "ROUND"

    def test_case_when_inside_group_by(self):
        """A CASE-WHEN-based conditional SUM as a chart's single grouped
        aggregate -- exercises _extract_single_grouped_aggregate_expr's
        single-agg-item path, not just the no-GROUP-BY Case 3 path."""
        t = translate(
            "SELECT Region, SUM(CASE WHEN Amount > 50 THEN Amount ELSE 0 END) AS conditional_total "
            "FROM data GROUP BY Region ORDER BY conditional_total DESC",
            "data",
        )
        assert t.expression == "SUMX('data', IF('data'[Amount] > 50, 'data'[Amount], 0))"

    def test_where_clause_combined_with_case_when(self):
        """A WHERE clause alongside a CASE-WHEN-based measure -- confirms
        _apply_where_filter's CALCULATE(...) wrapper composes correctly
        with the new SUMX/IF expression, same as every other shape."""
        t = translate(
            "SELECT SUM(CASE WHEN Amount > 50 THEN Amount ELSE 0 END) AS total "
            "FROM data WHERE Region = 'North'",
            "data",
        )
        assert t.expression == (
            "CALCULATE(SUMX('data', IF('data'[Amount] > 50, 'data'[Amount], 0)), "
            '\'data\'[Region] = "North")'
        )

    def test_quoted_identifiers_in_case_when(self):
        """BUG FIX 7.1a orthogonality: double-quoted identifiers inside a
        CASE WHEN must be normalized the same as everywhere else in the
        translator, since _normalize_identifiers runs before any
        shape-matcher (including the new CASE WHEN ones) ever sees the SQL."""
        t = translate(
            'SELECT SUM(CASE WHEN "Amount" > 50 THEN "Amount" ELSE 0 END) AS total FROM data',
            "data",
        )
        assert t.expression == "SUMX('data', IF('data'[Amount] > 50, 'data'[Amount], 0))"

    def test_existing_percentage_idiom_still_takes_priority(self):
        """REGRESSION GUARD: the specific 0/1-count-percentage idiom (see
        _CONDITIONAL_PCT_RE) must still be tried BEFORE the new general
        CASE WHEN path, and must still win -- the general path must never
        shadow it and produce a plain SUMX(IF(...)) instead of the
        idiomatic FILTER/COUNTROWS percentage form."""
        t = translate(
            "SELECT SUM(CASE WHEN StatusFlag = 'Active' THEN 1.0 ELSE 0.0 END) * 100.0 "
            "/ COUNT(*) AS rate FROM data",
            "data",
        )
        assert t.aggregation == "DIVIDE"
        assert t.is_percentage is True
        assert "COUNTROWS(FILTER(" in t.expression

    def test_multi_when_case_not_recognized(self):
        """Only a single-condition CASE WHEN...THEN...ELSE...END is
        recognized -- a multi-WHEN CASE (a second WHEN branch) falls
        through to the standard unsupported-shape error, same as any
        other not-yet-seen shape in this translator."""
        with pytest.raises(SQLToDaxError):
            translate(
                "SELECT SUM(CASE WHEN Amount > 100 THEN 2 WHEN Amount > 50 THEN 1 ELSE 0 END) "
                "AS tiered FROM data",
                "data",
            )

    def test_arithmetic_in_then_branch_not_recognized(self):
        """then_val/else_val must be a bare number or bare column reference
        only -- an arithmetic expression in a branch (Amount * 2) is not a
        recognized shape and must fall through to the standard
        unsupported-shape error rather than being silently mistranslated."""
        with pytest.raises(SQLToDaxError):
            translate(
                "SELECT SUM(CASE WHEN Amount > 50 THEN Amount * 2 ELSE 0 END) AS total FROM data",
                "data",
            )

    def test_case_when_item_alongside_plain_aggregate_in_table_kpi(self):
        """translate_multi() keeps a CASE-WHEN-based measure as its own
        sibling alongside an independent plain aggregate in a table KPI --
        confirms the new shape composes through translate_multi's existing
        item-classification regex without any change needed there."""
        translations = translate_multi(
            "SELECT Region, COUNT(*) AS n, "
            "SUM(CASE WHEN Amount > 50 THEN Amount ELSE 0 END) AS conditional_total "
            "FROM data GROUP BY Region",
            "data",
        )
        assert len(translations) == 2
        aggregations = {t.aggregation for t in translations}
        assert aggregations == {"COUNTROWS", "SUMX"}


class TestSQLToDaxUnsupportedShapes:
    def test_row_wise_product_supported(self):
        t = translate("SELECT SUM(UnitsSold * UnitCost) AS revenue FROM data", "data")
        assert t.expression == "SUMX('data', 'data'[UnitsSold] * 'data'[UnitCost])"

    def test_addition_inside_aggregate_rejected(self):
        with pytest.raises(SQLToDaxError):
            translate("SELECT SUM(Amount + 1) AS total FROM data", "data")

    def test_multi_aggregate_rejected_by_translate(self):
        with pytest.raises(SQLToDaxError):
            translate(
                "SELECT Region, COUNT(RecordId) AS n, SUM(Amount) AS total "
                "FROM data GROUP BY Region ORDER BY total DESC",
                "data",
            )

    def test_two_independent_non_ratio_aggregates_rejected_even_with_bare_count(self):
        with pytest.raises(SQLToDaxError):
            translate(
                "SELECT Region, COUNT(EntryId) AS n, SUM(Amount) AS total FROM data GROUP BY Region",
                "data",
            )

    def test_completely_unrecognized_shape(self):
        with pytest.raises(SQLToDaxError):
            translate("SELECT * FROM data", "data")


class TestSQLToDaxMultiMeasure:
    def test_two_aggregates_for_table_kpi(self):
        translations = translate_multi(
            "SELECT Region, COUNT(RecordId) AS n, SUM(Amount) AS total "
            "FROM data GROUP BY Region ORDER BY total DESC LIMIT 10",
            "data",
        )
        assert len(translations) == 2
        exprs = {t.expression for t in translations}
        assert exprs == {"COUNT('data'[RecordId])", "SUM('data'[Amount])"}

    def test_no_aggregates_raises(self):
        with pytest.raises(SQLToDaxError):
            translate_multi("SELECT Region FROM data", "data")

    def test_wrapped_ratio_alongside_plain_aggregate_kept_as_two_measures(self):
        """
        Unlike translate() (which picks ONE metric for a single-measure
        chart), translate_multi() legitimately keeps every recognized
        aggregate as its own sibling measure -- a table visual can show a
        raw count next to a computed rate. Confirms the 7.1b paren-unwrap
        fix also applies here without collapsing the two into one.
        """
        translations = translate_multi(
            "SELECT Region, COUNT(*) AS n, "
            "(SUM(CASE WHEN StatusFlag = 'Active' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)) AS rate "
            "FROM data GROUP BY Region",
            "data",
        )
        assert len(translations) == 2
        aggregations = {t.aggregation for t in translations}
        assert aggregations == {"COUNTROWS", "DIVIDE"}

    def test_quoted_identifiers_in_table_kpi(self):
        translations = translate_multi(
            'SELECT "Region", COUNT("RecordId") AS n, SUM("Amount") AS total FROM data GROUP BY "Region"',
            "data",
        )
        assert len(translations) == 2
        exprs = {t.expression for t in translations}
        assert exprs == {"COUNT('data'[RecordId])", "SUM('data'[Amount])"}


class TestGroupByColumnExtraction:
    def test_plain_group_by(self):
        assert extract_group_by_column(
            "SELECT Region, SUM(Amount) AS total FROM data GROUP BY Region ORDER BY total DESC"
        ) == "Region"

    def test_strftime_group_by_extracts_inner_column(self):
        assert extract_group_by_column(
            "SELECT strftime('%Y-%m', SignupDate) AS month, SUM(Amount) AS total "
            "FROM data GROUP BY month ORDER BY month"
        ) == "SignupDate"

    def test_no_group_by_returns_none(self):
        assert extract_group_by_column("SELECT SUM(Amount) AS total FROM data") is None

    def test_group_by_with_limit_no_order(self):
        assert extract_group_by_column(
            "SELECT Region, COUNT(*) AS n FROM data GROUP BY Region LIMIT 10"
        ) == "Region"


# =====================================================================
# Unit tests: Profiler dtype -> DAX/M/summarizeBy mapping
# (map_dtype / dax_type_to_m_type, in pbir/models/dtypes.py).
# =====================================================================


class TestDtypeMapping:
    def test_integer_maps_to_int64(self):
        m = map_dtype("integer", column_name="UnitsSold")
        assert m.dax_type == "int64"
        assert m.default_summarize_by == "sum"

    def test_float_maps_to_decimal(self):
        m = map_dtype("float", column_name="UnitCost")
        assert m.dax_type == "decimal"
        assert m.default_summarize_by == "sum"

    def test_string_maps_to_string_no_summarize(self):
        m = map_dtype("string", column_name="Category")
        assert m.dax_type == "string"
        assert m.default_summarize_by == "none"

    def test_datetime_maps_to_datetime(self):
        m = map_dtype("datetime", column_name="EventDate")
        assert m.dax_type == "dateTime"
        assert m.default_summarize_by == "none"

    def test_unknown_dtype_falls_back_to_string(self):
        m = map_dtype("some_weird_type", column_name="X")
        assert m.dax_type == "string"

    def test_date_like_column_profiled_as_string_stays_text(self):
        """
        A date-shaped column that the Profiler infers as 'string' rather
        than 'datetime' (a real, observed Profiler outcome) must be
        treated as plain text, not guessed at as a date-hierarchy
        candidate -- generic stand-in for the real 'a date column profiled
        as string' edge case.
        """
        m = map_dtype("string", column_name="SignupDate")
        assert m.dax_type == "string"
        assert m.default_summarize_by == "none"


class TestIdColumnSuppression:
    def test_id_suffix_suppresses_sum(self):
        m = map_dtype("integer", column_name="RecordId")
        assert m.default_summarize_by == "none"

    def test_key_suffix_suppresses_sum(self):
        m = map_dtype("integer", column_name="ForeignKey")
        assert m.default_summarize_by == "none"

    def test_genuine_quantity_column_still_sums(self):
        m = map_dtype("integer", column_name="UnitsSold")
        assert m.default_summarize_by == "sum"

    def test_no_column_name_defaults_to_dtype_table(self):
        m = map_dtype("integer")
        assert m.default_summarize_by == "sum"

    def test_low_cardinality_integer_suppresses_sum(self):
        """Ordinal/rating-shaped integer column (few distinct values, no
        Id/Key/Code suffix) must not default to summing either."""
        m = map_dtype("integer", column_name="PriorityLevel", distinct_count=5)
        assert m.default_summarize_by == "none"

    def test_high_cardinality_integer_without_id_suffix_still_sums(self):
        """Confirms the low-cardinality override doesn't over-trigger for
        a genuinely additive, high-cardinality column."""
        m = map_dtype("integer", column_name="UnitsSold", distinct_count=480)
        assert m.default_summarize_by == "sum"


class TestMTypeLiteralAccessor:
    def test_int64_to_m_type(self):
        assert dax_type_to_m_type("int64") == "Int64.Type"

    def test_decimal_to_m_type(self):
        assert dax_type_to_m_type("decimal") == "type number"

    def test_string_to_m_type(self):
        assert dax_type_to_m_type("string") == "type text"

    def test_datetime_to_m_type(self):
        assert dax_type_to_m_type("dateTime") == "type datetime"

    def test_unrecognized_falls_back(self):
        assert dax_type_to_m_type("nonsense") == "type text"


# =====================================================================
# Unit tests: page-grouping and canvas layout
# (group_into_pages / layout_page, in pbir/compiler/builder.py).
# =====================================================================


def _mk(n: int, chart_type: str) -> Visual:
    return Visual(visual_id=f"v{n}", chart_type=chart_type, title=f"t{n}", measure_ref=f"m{n}")


class TestPageGrouping:
    def test_five_visual_mixed_shape_meets_acceptance_criteria(self):
        """2 cards + 1 line + 1 bar + 1 table -> must yield >=2 pages, >=4 visuals."""
        visuals = [_mk(1, "card"), _mk(2, "card"), _mk(3, "lineChart"), _mk(4, "barChart"), _mk(5, "table")]
        pages = group_into_pages(visuals)
        assert len(pages) >= 2
        assert sum(len(p) for p in pages) == 5
        assert all(len(p) <= 3 for p in pages)

    def test_two_charts_no_cards_single_page(self):
        visuals = [_mk(1, "lineChart"), _mk(2, "barChart")]
        pages = group_into_pages(visuals)
        assert len(pages) == 1
        assert len(pages[0]) == 2

    def test_three_cards_two_charts(self):
        visuals = [_mk(1, "card"), _mk(2, "card"), _mk(3, "card"), _mk(4, "lineChart"), _mk(5, "barChart")]
        pages = group_into_pages(visuals)
        assert len(pages) == 2
        assert len(pages[0]) == 3
        assert len(pages[1]) == 2

    def test_single_visual(self):
        pages = group_into_pages([_mk(1, "card")])
        assert len(pages) == 1
        assert len(pages[0]) == 1

    def test_no_page_exceeds_type_cap(self):
        visuals = [_mk(i, "card") for i in range(7)]
        pages = group_into_pages(visuals)
        assert all(len(p) <= 3 for p in pages)
        assert sum(len(p) for p in pages) == 7

    def test_all_visuals_preserved_across_pages(self):
        visuals = [_mk(i, "barChart") for i in range(5)]
        pages = group_into_pages(visuals)
        assert sum(len(p) for p in pages) == 5


class TestVisualLayout:
    def test_positions_are_non_overlapping_for_two_cards(self):
        visuals = [_mk(1, "card"), _mk(2, "card")]
        layout_page(visuals)
        assert visuals[0].position.x != visuals[1].position.x

    def test_single_visual_gets_full_width(self):
        visuals = [_mk(1, "lineChart")]
        layout_page(visuals)
        assert visuals[0].position.width > 0
        assert visuals[0].position.height > 0

    def test_three_visual_page_has_two_rows(self):
        visuals = [_mk(1, "lineChart"), _mk(2, "barChart"), _mk(3, "table")]
        layout_page(visuals)
        ys = {v.position.y for v in visuals}
        assert len(ys) == 2

    def test_empty_list_does_not_crash(self):
        layout_page([])


# =====================================================================
# MIN_VISUALS_REQUIRED acceptance gate: individual untranslatable KPIs
# are dropped (not fatal), but the whole build is rejected if too few
# survive translation to meet the project's visual-count criterion.
# =====================================================================


class TestMinimumVisualAcceptanceThreshold:
    def _tiny_profile(self) -> DataProfile:
        return DataProfile(
            source_path="data/raw/tiny.csv",
            source_table=None,
            row_count=10,
            column_count=2,
            is_single_row=False,
            columns={
                "Amount": ColumnProfile(inferred_dtype="float", null_count=0, null_rate=0.0, distinct_count=10),
                "Category": ColumnProfile(inferred_dtype="string", null_count=0, null_rate=0.0, distinct_count=3),
            },
        )

    def test_build_rejected_when_fewer_than_four_visuals_survive(self):
        kpi_specs = [
            KPISpec(name="Total", description="d", sql_query="SELECT SUM(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="Average", description="d", sql_query="SELECT AVG(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
        ]
        query_results = [
            QueryResult(kpi_name=k.name, sql_query=k.sql_query, status="pass", row_count=1, columns=[], result_rows=[])
            for k in kpi_specs
        ]
        state = AgentState(data_profile=self._tiny_profile(), kpi_specs=kpi_specs, query_results=query_results)
        result = run_pbir_compiler(state)

        assert result.pbir_project is None
        assert any("only 2 KPI(s)" in e for e in result.errors)

    def test_build_accepted_when_exactly_four_visuals_survive(self):
        kpi_specs = [
            KPISpec(name="Total", description="d", sql_query="SELECT SUM(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="Average", description="d", sql_query="SELECT AVG(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="Count", description="d", sql_query="SELECT COUNT(*) AS n FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="By Category", description="d", sql_query="SELECT Category, SUM(Amount) AS Amount FROM data GROUP BY Category", chart_type="barChart", reasoning="r"),
        ]
        query_results = [
            QueryResult(kpi_name=k.name, sql_query=k.sql_query, status="pass", row_count=1, columns=[], result_rows=[])
            for k in kpi_specs
        ]
        state = AgentState(data_profile=self._tiny_profile(), kpi_specs=kpi_specs, query_results=query_results)
        result = run_pbir_compiler(state)

        assert result.errors == []
        assert result.pbir_project is not None
        assert sum(len(p.visuals) for p in result.pbir_project.pages) == 4

    def test_individual_untranslatable_kpi_is_dropped_not_fatal(self):
        kpi_specs = [
            KPISpec(name="Total", description="d", sql_query="SELECT SUM(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="Average", description="d", sql_query="SELECT AVG(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="Count", description="d", sql_query="SELECT COUNT(*) AS n FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="By Category", description="d", sql_query="SELECT Category, SUM(Amount) AS Amount FROM data GROUP BY Category", chart_type="barChart", reasoning="r"),
            # Genuinely untranslatable (addition, not a recognized shape) --
            # should be dropped, not fatal, since 4 others still survive.
            KPISpec(name="Bad KPI", description="d", sql_query="SELECT SUM(Amount + 1) AS Amount FROM data", chart_type="card", reasoning="r"),
        ]
        query_results = [
            QueryResult(kpi_name=k.name, sql_query=k.sql_query, status="pass", row_count=1, columns=[], result_rows=[])
            for k in kpi_specs
        ]
        state = AgentState(data_profile=self._tiny_profile(), kpi_specs=kpi_specs, query_results=query_results)
        result = run_pbir_compiler(state)

        assert result.pbir_project is not None
        assert sum(len(p.visuals) for p in result.pbir_project.pages) == 4
        assert any("Bad KPI" in e for e in result.errors)


# =====================================================================
# Full-pipeline integration: builder.run_pbir_compiler against the
# synthetic 6-KPI fixture defined at the top of this file (all 4 chart
# types, an Id column, a low-cardinality rating column, a currency
# column, and both SQL->DAX bug patterns fixed this session).
# =====================================================================


class TestFullPipelineIntegration:
    def test_produces_at_least_two_pages(self, compiled_synthetic_project):
        assert len(compiled_synthetic_project.pages) >= 2

    def test_produces_at_least_four_visuals(self, compiled_synthetic_project):
        total = sum(len(p.visuals) for p in compiled_synthetic_project.pages)
        assert total >= 4

    def test_all_six_kpis_translate_successfully(self, compiled_synthetic_project):
        """None of the 6 synthetic KPIs is deliberately broken -- all should
        survive translation, including both quoted-identifier and
        wrapped-ratio shapes."""
        total = sum(len(p.visuals) for p in compiled_synthetic_project.pages)
        assert total == len(SYNTHETIC_KPI_SPECS) == 6

    def test_every_visual_measure_ref_is_a_real_measure(self, compiled_synthetic_project):
        measure_names = {m.name for m in compiled_synthetic_project.data_table.measures}
        for page in compiled_synthetic_project.pages:
            for visual in page.visuals:
                assert visual.measure_ref in measure_names

    def test_id_column_not_summed(self, compiled_synthetic_project):
        record_id = [c for c in compiled_synthetic_project.data_table.columns if c.name == "RecordId"]
        assert len(record_id) == 1
        assert record_id[0].summarize_by == "none"

    def test_low_cardinality_rating_column_not_summed(self, compiled_synthetic_project):
        priority = [c for c in compiled_synthetic_project.data_table.columns if c.name == "PriorityLevel"]
        assert len(priority) == 1
        assert priority[0].summarize_by == "none"

    def test_genuinely_additive_column_still_sums(self, compiled_synthetic_project):
        amount = [c for c in compiled_synthetic_project.data_table.columns if c.name == "Amount"]
        assert len(amount) == 1
        assert amount[0].summarize_by == "sum"

    def test_currency_measure_uses_currency_format(self, compiled_synthetic_project):
        total_amount = [m for m in compiled_synthetic_project.data_table.measures if m.name == "Total Amount"]
        assert len(total_amount) == 1
        assert total_amount[0].is_currency is True
        assert total_amount[0].format_string == "\\$#,0.00"

    def test_percentage_measures_use_percentage_format(self, compiled_synthetic_project):
        pct_names = {"Overall Active Rate", "Active Rate by Region"}
        pct_measures = [m for m in compiled_synthetic_project.data_table.measures if m.name in pct_names]
        assert len(pct_measures) == 2
        for m in pct_measures:
            assert m.format_string == "0.00\\%"
            assert "DIVIDE" in m.expression
            assert "COUNTROWS" in m.expression

    def test_multi_measure_table_kpi_produces_two_measures(self, compiled_synthetic_project):
        names = [m.name for m in compiled_synthetic_project.data_table.measures]
        matching = [n for n in names if n.startswith("Priority Breakdown")]
        assert len(matching) == 2

    def test_quoted_identifier_kpi_resolves_category_ref_bare(self, compiled_synthetic_project):
        """BUG FIX 7.1a at full-pipeline level: 'Amount by Region' uses
        double-quoted SQL throughout -- category_ref must be the bare
        column name, not None and not still-quoted."""
        matches = [
            v for page in compiled_synthetic_project.pages for v in page.visuals
            if v.title == "Amount by Region"
        ]
        assert len(matches) == 1
        assert matches[0].category_ref == "Region"

    def test_wrapped_ratio_kpis_bind_to_percentage_measures(self, compiled_synthetic_project):
        """BUG FIX 7.1b at full-pipeline level: both wrapped-ratio KPIs
        must produce a visual bound to a DIVIDE-based measure."""
        measure_exprs = {m.name: m.expression for m in compiled_synthetic_project.data_table.measures}
        for title in ("Active Rate by Region", "Overall Active Rate"):
            matches = [v for page in compiled_synthetic_project.pages for v in page.visuals if v.title == title]
            assert len(matches) == 1, f"no visual found for {title!r}"
            assert "DIVIDE" in measure_exprs[matches[0].measure_ref]

    def test_report_name_derived_from_csv_filename_stem(self, compiled_synthetic_project):
        """source_table is None (CSV input, the realistic case for this
        pipeline) -- falls back to the source CSV's filename stem."""
        assert compiled_synthetic_project.report_name == "synthetic_activity"

    def test_missing_data_profile_records_error_not_crash(self):
        state = AgentState(kpi_specs=SYNTHETIC_KPI_SPECS, query_results=SYNTHETIC_QUERY_RESULTS)
        result = run_pbir_compiler(state)
        assert result.pbir_project is None
        assert len(result.errors) == 1
        assert "data_profile" in result.errors[0]


# =====================================================================
# Serialiser: folder-tree structure (write_pbip against the compiled
# synthetic project).
# =====================================================================


class TestSerialiserFolderStructure:
    def test_root_pointer_file_exists(self, synthetic_output_dir, compiled_synthetic_project):
        pbip_file = synthetic_output_dir / f"{compiled_synthetic_project.report_name}.pbip"
        assert pbip_file.exists()

    def test_report_and_semantic_model_folders_exist(self, synthetic_output_dir, compiled_synthetic_project):
        name = compiled_synthetic_project.report_name
        assert (synthetic_output_dir / f"{name}.Report").is_dir()
        assert (synthetic_output_dir / f"{name}.SemanticModel").is_dir()

    def test_platform_files_exist_both_sides(self, synthetic_output_dir, compiled_synthetic_project):
        name = compiled_synthetic_project.report_name
        assert (synthetic_output_dir / f"{name}.Report" / ".platform").exists()
        assert (synthetic_output_dir / f"{name}.SemanticModel" / ".platform").exists()

    def test_definition_pbir_links_to_semantic_model(self, synthetic_output_dir, compiled_synthetic_project):
        name = compiled_synthetic_project.report_name
        pbir = json.loads((synthetic_output_dir / f"{name}.Report" / "definition.pbir").read_text())
        assert pbir["datasetReference"]["byPath"]["path"] == f"../{name}.SemanticModel"

    def test_pages_json_lists_every_page_folder(self, synthetic_output_dir, compiled_synthetic_project):
        name = compiled_synthetic_project.report_name
        pages_json = json.loads(
            (synthetic_output_dir / f"{name}.Report" / "definition" / "pages" / "pages.json").read_text()
        )
        assert len(pages_json["pageOrder"]) == len(compiled_synthetic_project.pages)
        for page_id in pages_json["pageOrder"]:
            assert (synthetic_output_dir / f"{name}.Report" / "definition" / "pages" / page_id / "page.json").exists()

    def test_every_visual_json_exists_and_matches_page(self, synthetic_output_dir, compiled_synthetic_project):
        name = compiled_synthetic_project.report_name
        for page in compiled_synthetic_project.pages:
            page_dir = synthetic_output_dir / f"{name}.Report" / "definition" / "pages" / page.page_id
            for visual in page.visuals:
                visual_file = page_dir / "visuals" / visual.visual_id / "visual.json"
                assert visual_file.exists(), f"missing {visual_file}"

    def test_table_tmdl_exists(self, synthetic_output_dir, compiled_synthetic_project):
        name = compiled_synthetic_project.report_name
        table_file = (
            synthetic_output_dir / f"{name}.SemanticModel" / "definition" / "tables"
            / f"{compiled_synthetic_project.data_table.name}.tmdl"
        )
        assert table_file.exists()

    def test_relationships_tmdl_never_written(self, synthetic_output_dir):
        """Relationships are permanently out of scope (mentor sign-off)."""
        assert not list(synthetic_output_dir.rglob("relationships.tmdl"))

    def test_no_sqlite_or_date_table_files_ever_written(self, synthetic_output_dir):
        """SQLite M-source and auto-date-tables are permanently out of
        scope (mentor sign-off: CSV-only, no auto-generated date tables)."""
        assert not list(synthetic_output_dir.rglob("LocalDateTable_*.tmdl"))
        assert not list(synthetic_output_dir.rglob("DateTableTemplate_*.tmdl"))
        for tmdl_file in synthetic_output_dir.rglob("*.tmdl"):
            assert "Sqlite.Database" not in tmdl_file.read_text()

    def test_excluded_files_never_written(self, synthetic_output_dir):
        """SS2.15: these should never appear in compiler output."""
        forbidden = [
            "**/.pbi/localSettings.json",
            "**/.pbi/cache.abf",
            "**/.pbi/editorSettings.json",
            "**/diagramLayout.json",
            "**/cultures/en-US.tmdl",
        ]
        for pattern in forbidden:
            matches = list(synthetic_output_dir.glob(pattern))
            assert matches == [], f"unexpected excluded file(s) written: {matches}"


# =====================================================================
# Serialiser: JSON structural correctness.
# =====================================================================


class TestJSONValidity:
    def test_every_json_file_parses(self, synthetic_output_dir):
        json_files = list(synthetic_output_dir.rglob("*.json"))
        assert len(json_files) > 0
        for f in json_files:
            json.loads(f.read_text())

    def test_tableEx_has_no_rows_role(self, synthetic_output_dir, compiled_synthetic_project):
        """The #1 way to break a tableEx visual: copying pivotTable's Rows role."""
        name = compiled_synthetic_project.report_name
        found = False
        for page in compiled_synthetic_project.pages:
            for visual in page.visuals:
                if visual.chart_type != "table":
                    continue
                found = True
                visual_file = (
                    synthetic_output_dir / f"{name}.Report" / "definition" / "pages"
                    / page.page_id / "visuals" / visual.visual_id / "visual.json"
                )
                data = json.loads(visual_file.read_text())
                query_state = data["visual"]["query"]["queryState"]
                assert "Rows" not in query_state
                assert "Values" in query_state
        assert found, "no table visual found in the synthetic project"

    def test_card_visual_has_data_role(self, synthetic_output_dir, compiled_synthetic_project):
        name = compiled_synthetic_project.report_name
        found = False
        for page in compiled_synthetic_project.pages:
            for visual in page.visuals:
                if visual.chart_type != "card":
                    continue
                found = True
                visual_file = (
                    synthetic_output_dir / f"{name}.Report" / "definition" / "pages"
                    / page.page_id / "visuals" / visual.visual_id / "visual.json"
                )
                data = json.loads(visual_file.read_text())
                assert "Data" in data["visual"]["query"]["queryState"]
                assert data["visual"]["visualType"] == "cardVisual"
        assert found, "no card visual found in the synthetic project"

    def test_table_visual_projection_count_matches_category_plus_measures(
        self, synthetic_output_dir, compiled_synthetic_project
    ):
        """'Priority Breakdown' groups by PriorityLevel and selects 2
        aggregates -> 1 category + 2 measures = 3 sibling Values projections."""
        name = compiled_synthetic_project.report_name
        for page in compiled_synthetic_project.pages:
            for visual in page.visuals:
                if visual.chart_type != "table":
                    continue
                visual_file = (
                    synthetic_output_dir / f"{name}.Report" / "definition" / "pages"
                    / page.page_id / "visuals" / visual.visual_id / "visual.json"
                )
                data = json.loads(visual_file.read_text())
                projections = data["visual"]["query"]["queryState"]["Values"]["projections"]
                assert len(projections) == 3
                return
        pytest.fail("no table visual found in the synthetic project")


# =====================================================================
# TMDL formatting and ID-safety.
# =====================================================================


class TestTMDLFormatting:
    def test_table_tmdl_uses_tabs_not_leading_spaces(self, synthetic_output_dir, compiled_synthetic_project):
        """
        Top-level declarations (table/measure/column/partition) are
        correctly unindented; the M-script body uses spaces internally for
        its own step lines (matches the reference sample's own
        convention), which is expected. This only checks that nothing
        uses a literal leading space where a TAB was expected.
        """
        name = compiled_synthetic_project.report_name
        table_file = (
            synthetic_output_dir / f"{name}.SemanticModel" / "definition" / "tables"
            / f"{compiled_synthetic_project.data_table.name}.tmdl"
        )
        text = table_file.read_text()
        for line in text.split("\n"):
            if line.startswith(" "):
                pytest.fail(f"Line starts with a literal space, not a tab: {line!r}")

    def test_measure_lineage_tags_are_valid_uuids(self, compiled_synthetic_project):
        for m in compiled_synthetic_project.data_table.measures:
            uuid.UUID(m.lineage_tag)  # raises ValueError if not a valid UUID

    def test_m_query_uses_csv_document_only(self, compiled_synthetic_project):
        """CSV-only scope: every generated M query must use Csv.Document."""
        tmdl_text = _build_table_tmdl(compiled_synthetic_project.data_table)
        assert "Csv.Document" in tmdl_text
        assert "Sqlite" not in tmdl_text
        assert "Odbc" not in tmdl_text

    def test_m_query_never_doubles_windows_path_backslashes(self):
        """
        REGRESSION GUARD: M's only string-escape rule is doubling the quote
        character; backslash has no special meaning and must never be
        doubled. Doubling a Windows absolute path's backslashes would
        silently break Csv.Document (it would try to open a path matching
        nothing on disk), with no other error surfaced.
        """
        windows_path = r"C:\Users\example\Documents\data\raw\synthetic.csv"
        cols = [Column(name="Age", data_type="int64", source_column="Age")]
        source = _build_m_partition_source(windows_path, cols)

        assert windows_path in source, "the exact single-backslash path must appear verbatim"
        assert "\\\\" not in source, "no doubled backslashes should ever appear in the M source"

    def test_m_query_resolves_relative_path_to_absolute(self):
        """
        REGRESSION GUARD: profiler.py stores source_path relative to the
        project root. Power Query's File.Contents(...) has no notion of
        "relative to the .pbip file" -- a relative path here fails to load
        in Power BI Desktop with "supplied file path must be a valid
        absolute path". This confirms a relative input is resolved to an
        absolute one, while test_m_query_never_doubles_windows_path_backslashes
        above confirms an already-absolute path is left untouched.
        """
        relative_path = os.path.join("data", "raw", "synthetic.csv")
        cols = [Column(name="Age", data_type="int64", source_column="Age")]
        source = _build_m_partition_source(relative_path, cols)

        match = re.search(r'File\.Contents\("(.+?)"\)', source)
        assert match is not None, "expected a File.Contents(...) call in the generated M source"
        assert os.path.isabs(match.group(1)), "the path inside File.Contents(...) must be absolute"

    def test_filter_names_never_collide_on_long_visual_ids(self):
        """
        REGRESSION GUARD: a prior filter-naming scheme truncated the
        CONCATENATED (visual_id + field_name) string to a fixed cap before
        the differentiating suffix was applied, so once visual_id alone
        approached that cap, multiple filters on the same visual collapsed
        onto an identical name. Desktop's real constraint is 1-50
        characters, not the 40 originally assumed.
        """
        long_visual_id = "viz_some_fairly_long_descriptive_kpi_name_table"
        names = [_local_filter_id(long_visual_id, i) for i in range(4)]

        assert len(set(names)) == 4, f"filter names collided: {names}"
        for name in names:
            assert 1 <= len(name) <= 50, f"filter name outside Desktop's 1-50 char limit: {name!r}"
        assert all(name.endswith(f"_{i}") for i, name in enumerate(names)), (
            "the differentiating _<idx> suffix must never be truncated away"
        )

    def test_common_filter_id_matches_serialiser_fix(self):
        """
        pbir/models/common.py's filter_id() had the identical truncation
        bug as serialiser.py's _local_filter_id() (same root cause, two
        call sites) -- guards common.py's copy specifically, since other
        code may still reach for it directly.
        """
        long_visual_id = "viz_some_fairly_long_descriptive_kpi_name_barchart"
        f0 = filter_id(long_visual_id, "SomeField", 0)
        f1 = filter_id(long_visual_id, "OtherField", 1)

        assert f0 != f1
        assert 1 <= len(f0) <= 50
        assert 1 <= len(f1) <= 50
        assert f0.endswith("_0")
        assert f1.endswith("_1")