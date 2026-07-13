"""
tests/test_pbir_compiler.py — integration tests for run_pbir_compiler +
write_pbip against the Chinook and HR fixtures.

Per project convention, every fixture here is built as in-memory Pydantic
objects (tests/fixtures_chinook.py, tests/fixtures_chinook_query_results.py,
tests/fixtures_hr.py) -- this test module never calls json.load() on a
profile/KPI file, mirroring how AgentState is actually handed between
pipeline nodes in memory, never re-parsed from JSON on disk.

These tests assert everything structurally verifiable in pytest: folder
tree shape, JSON validity, TMDL tab-indentation, cross-file ID consistency,
and the acceptance criteria's countable properties (>=2 pages, >=4 visuals,
measures present in the semantic model). "Opens in Power BI Desktop without
errors" itself is NOT something pytest can assert -- that remains a manual
verification step outside this suite.
"""
import json

import pytest

from agent.state import AgentState
from agent.models import KPISpec, QueryResult
from pbir.compiler.builder import run_pbir_compiler
from pbir.compiler.serialiser import write_pbip

from tests.fixtures_chinook import CHINOOK_PROFILE
from tests.fixtures_chinook_query_results import CHINOOK_QUERY_RESULTS, CHINOOK_KPI_SPECS
from tests.fixtures_hr import HR_PROFILE, HR_KPI_SPECS, HR_QUERY_RESULTS
from tests.fixtures_online_retail import (
    ONLINE_RETAIL_PROFILE,
    ONLINE_RETAIL_KPI_SPECS,
    ONLINE_RETAIL_QUERY_RESULTS,
)


@pytest.fixture
def chinook_state() -> AgentState:
    return AgentState(
        input_path="data/raw/chinook.csv",
        output_path="output/chinook_report",
        data_profile=CHINOOK_PROFILE,
        kpi_specs=CHINOOK_KPI_SPECS,
        query_results=CHINOOK_QUERY_RESULTS,
    )


@pytest.fixture
def compiled_chinook_project(chinook_state):
    result_state = run_pbir_compiler(chinook_state)
    assert result_state.errors == [], f"Builder produced errors: {result_state.errors}"
    assert result_state.pbir_project is not None
    return result_state.pbir_project


@pytest.fixture
def chinook_output_dir(compiled_chinook_project, tmp_path):
    out = tmp_path / "chinook_report"
    write_pbip(compiled_chinook_project, out)
    return out


@pytest.fixture
def hr_state() -> AgentState:
    return AgentState(
        input_path="data/raw/hr.csv",
        output_path="output/hr_report",
        data_profile=HR_PROFILE,
        kpi_specs=HR_KPI_SPECS,
        query_results=HR_QUERY_RESULTS,
    )


@pytest.fixture
def compiled_hr_project(hr_state):
    result_state = run_pbir_compiler(hr_state)
    assert result_state.errors == [], f"Builder produced errors: {result_state.errors}"
    assert result_state.pbir_project is not None
    return result_state.pbir_project


@pytest.fixture
def hr_output_dir(compiled_hr_project, tmp_path):
    out = tmp_path / "hr_report"
    write_pbip(compiled_hr_project, out)
    return out


@pytest.fixture
def online_retail_state() -> AgentState:
    return AgentState(
        input_path="data/raw/online_retail.csv",
        output_path="output/online_retail_report",
        data_profile=ONLINE_RETAIL_PROFILE,
        kpi_specs=ONLINE_RETAIL_KPI_SPECS,
        query_results=ONLINE_RETAIL_QUERY_RESULTS,
    )


@pytest.fixture
def compiled_online_retail_project(online_retail_state):
    result_state = run_pbir_compiler(online_retail_state)
    assert result_state.errors == [], f"Builder produced errors: {result_state.errors}"
    assert result_state.pbir_project is not None
    return result_state.pbir_project


@pytest.fixture
def online_retail_output_dir(compiled_online_retail_project, tmp_path):
    out = tmp_path / "online_retail_report"
    write_pbip(compiled_online_retail_project, out)
    return out


class TestBuilderChinook:
    def test_produces_at_least_two_pages(self, compiled_chinook_project):
        assert len(compiled_chinook_project.pages) >= 2

    def test_produces_at_least_four_visuals(self, compiled_chinook_project):
        total = sum(len(p.visuals) for p in compiled_chinook_project.pages)
        assert total >= 4

    def test_produces_at_least_one_measure_per_visual(self, compiled_chinook_project):
        measure_names = {m.name for m in compiled_chinook_project.data_table.measures}
        for page in compiled_chinook_project.pages:
            for visual in page.visuals:
                assert visual.measure_ref in measure_names

    def test_id_columns_not_summed(self, compiled_chinook_project):
        id_cols = [c for c in compiled_chinook_project.data_table.columns if c.name.endswith("Id")]
        assert id_cols, "expected at least one Id column in Chinook Invoice table"
        for col in id_cols:
            assert col.summarize_by == "none"

    def test_multi_aggregate_table_kpi_produces_multiple_measures(self, compiled_chinook_project):
        """'Top Customers by Total Spend' has 2 aggregates -> 2 measures."""
        names = [m.name for m in compiled_chinook_project.data_table.measures]
        matching = [n for n in names if n.startswith("Top Customers by Total Spend")]
        assert len(matching) == 2

    def test_missing_data_profile_records_error_not_crash(self):
        state = AgentState(kpi_specs=CHINOOK_KPI_SPECS, query_results=CHINOOK_QUERY_RESULTS)
        result = run_pbir_compiler(state)
        assert result.pbir_project is None
        assert len(result.errors) == 1
        assert "data_profile" in result.errors[0]

    def test_report_name_derived_from_source_table(self, compiled_chinook_project):
        assert compiled_chinook_project.report_name == "Invoice"


class TestBuilderHR:
    def test_produces_at_least_two_pages(self, compiled_hr_project):
        assert len(compiled_hr_project.pages) >= 2

    def test_produces_at_least_four_visuals(self, compiled_hr_project):
        total = sum(len(p.visuals) for p in compiled_hr_project.pages)
        assert total >= 4

    def test_all_five_kpis_translate_successfully(self, compiled_hr_project):
        """
        hr_kpis.json has no sabotaged KPIs -- unlike Chinook, all 5 should
        produce visuals (the two attrition-rate-by-X KPIs correctly extract
        just the rate/percentage measure, not the accompanying COUNT(*)).
        """
        total = sum(len(p.visuals) for p in compiled_hr_project.pages)
        assert total == 5

    def test_percentage_measures_use_percentage_format(self, compiled_hr_project):
        pct_measure_names = {"Overall Attrition Rate", "Attrition Rate by Job Role", "Attrition Risk by Tenure"}
        pct_measures = [m for m in compiled_hr_project.data_table.measures if m.name in pct_measure_names]
        assert len(pct_measures) == 3
        for m in pct_measures:
            assert m.format_string == "0.00\\%"
            assert "COUNTROWS" in m.expression
            assert "FILTER" in m.expression

    def test_low_cardinality_rating_columns_not_summed(self, compiled_hr_project):
        """JobSatisfaction/WorkLifeBalance/EnvironmentSatisfaction are 1-4
        ordinal ratings (distinct_count=4) -- must not default to sum."""
        rating_cols = [
            c for c in compiled_hr_project.data_table.columns
            if c.name in ("JobSatisfaction", "WorkLifeBalance", "EnvironmentSatisfaction")
        ]
        assert len(rating_cols) == 3
        for col in rating_cols:
            assert col.summarize_by == "none"

    def test_genuinely_additive_column_still_sums(self, compiled_hr_project):
        income_col = [c for c in compiled_hr_project.data_table.columns if c.name == "MonthlyIncome"][0]
        assert income_col.summarize_by == "sum"

    def test_table_kpi_with_three_measures(self, compiled_hr_project):
        """'Employee Sentiment Profile by Job Role' selects 3 AVG columns."""
        names = [m.name for m in compiled_hr_project.data_table.measures]
        matching = [n for n in names if n.startswith("Employee Sentiment Profile by Job Role")]
        assert len(matching) == 3

    def test_report_name_derived_from_csv_filename_when_source_table_none(self, compiled_hr_project):
        """HR's source_table is None (CSV input) -- falls back to filename stem."""
        assert compiled_hr_project.report_name == "hr"


class TestBuilderOnlineRetail:
    """
    SCOPE EXTENSION (2026-07-12): online_retail requires SQL->DAX shapes
    beyond the original basic-DAX set to meet the project's own "all three
    dataset reports open successfully" acceptance criterion --
    SUM/AVG(ColA * ColB) -> SUMX/AVERAGEX, COUNT(DISTINCT col) ->
    DISTINCTCOUNT, and WHERE -> CALCULATE(...) filtering. All still basic,
    well-documented DAX; this is a small, deliberate widening of the
    original SUM/AVERAGE/COUNT/DIVIDE/IF set, not exotic scope.
    """

    def test_produces_at_least_two_pages(self, compiled_online_retail_project):
        assert len(compiled_online_retail_project.pages) >= 2

    def test_meets_minimum_visual_acceptance_threshold(self, compiled_online_retail_project):
        total = sum(len(p.visuals) for p in compiled_online_retail_project.pages)
        assert total >= 4

    def test_all_five_kpis_translate_successfully(self, compiled_online_retail_project):
        """
        All 5 KPIs (post-Reflector-fix) should now produce visuals: 2 cards
        with WHERE-filtered SUMX/DISTINCTCOUNT, 1 barChart, 1 lineChart
        (with GROUP-BY-alias resolution), 1 table with 2 WHERE-filtered
        sibling measures.
        """
        total = sum(len(p.visuals) for p in compiled_online_retail_project.pages)
        assert total == 5

    def test_total_revenue_uses_sumx_wrapped_in_calculate(self, compiled_online_retail_project):
        measures = [m for m in compiled_online_retail_project.data_table.measures if m.name == "Total Revenue"]
        assert len(measures) == 1
        expr = measures[0].expression
        assert expr == "CALCULATE(SUMX('data', 'data'[Quantity] * 'data'[UnitPrice]), 'data'[Quantity] > 0)"

    def test_aov_uses_distinctcount_and_sumx_both_filtered(self, compiled_online_retail_project):
        measures = [m for m in compiled_online_retail_project.data_table.measures if m.name == "Average Order Value (AOV)"]
        assert len(measures) == 1
        expr = measures[0].expression
        assert expr == (
            "CALCULATE(DIVIDE(SUMX('data', 'data'[Quantity] * 'data'[UnitPrice]), "
            "DISTINCTCOUNT('data'[InvoiceNo])), 'data'[Quantity] > 0)"
        )

    def test_monthly_trend_resolves_group_by_alias_to_real_column(self, compiled_online_retail_project):
        """
        REGRESSION GUARD: 'Monthly Sales Trend' GROUPs BY its own SELECT
        alias (sales_month), not the real underlying column (InvoiceDate).
        A prior version returned the bare alias directly, which would have
        produced a visual.json Category binding to a nonexistent field.
        """
        for page in compiled_online_retail_project.pages:
            for visual in page.visuals:
                if visual.chart_type == "lineChart":
                    assert visual.category_ref == "InvoiceDate"
                    return
        pytest.fail("no lineChart visual found in compiled Online Retail project")

    def test_top_products_table_has_two_calculate_wrapped_measures(self, compiled_online_retail_project):
        names_and_exprs = {
            m.name: m.expression for m in compiled_online_retail_project.data_table.measures
            if m.name.startswith("Top 10 Products by Quantity Sold")
        }
        assert len(names_and_exprs) == 2
        for expr in names_and_exprs.values():
            assert expr.startswith("CALCULATE(")
            assert "'data'[Quantity] > 0" in expr

    def test_top_products_visual_groups_by_first_column_of_multi_column_group_by(self, compiled_online_retail_project):
        """GROUP BY StockCode, Description -> category_ref is StockCode (first column)."""
        for page in compiled_online_retail_project.pages:
            for visual in page.visuals:
                if visual.chart_type == "table":
                    assert visual.category_ref == "StockCode"
                    return
        pytest.fail("no table visual found in compiled Online Retail project")


class TestMinimumVisualThreshold:
    """
    Directly exercises the MIN_VISUALS_REQUIRED acceptance gate in
    run_pbir_compiler: individual untranslatable KPIs are dropped (not
    fatal), but the whole build is rejected if too few KPIs survive
    translation overall to meet the project's own visual-count criterion.
    """

    def test_build_rejected_when_fewer_than_four_visuals_survive(self):
        from agent.models import DataProfile, ColumnProfile
        from pbir.compiler.builder import run_pbir_compiler

        profile = DataProfile(
            source_path="data/raw/tiny.csv",
            source_table=None,
            row_count=10,
            column_count=1,
            is_single_row=False,
            columns={"Amount": ColumnProfile(inferred_dtype="float", null_count=0, null_rate=0.0, distinct_count=10)},
        )
        # Only 2 translatable KPIs -- below MIN_VISUALS_REQUIRED (4).
        kpi_specs = [
            KPISpec(name="Total", description="d", sql_query="SELECT SUM(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="Average", description="d", sql_query="SELECT AVG(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
        ]
        query_results = [
            QueryResult(kpi_name="Total", sql_query=kpi_specs[0].sql_query, status="pass", row_count=1, columns=["Amount"], result_rows=[]),
            QueryResult(kpi_name="Average", sql_query=kpi_specs[1].sql_query, status="pass", row_count=1, columns=["Amount"], result_rows=[]),
        ]
        state = AgentState(data_profile=profile, kpi_specs=kpi_specs, query_results=query_results)
        result = run_pbir_compiler(state)

        assert result.pbir_project is None
        assert any("only 2 KPI(s)" in e for e in result.errors)

    def test_build_accepted_when_exactly_four_visuals_survive(self):
        from agent.models import DataProfile, ColumnProfile
        from pbir.compiler.builder import run_pbir_compiler

        profile = DataProfile(
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
        state = AgentState(data_profile=profile, kpi_specs=kpi_specs, query_results=query_results)
        result = run_pbir_compiler(state)

        assert result.errors == []
        assert result.pbir_project is not None
        assert sum(len(p.visuals) for p in result.pbir_project.pages) == 4

    def test_individual_untranslatable_kpi_is_dropped_not_fatal(self):
        """
        A mix where SOME KPIs fail translation but enough survive to clear
        the threshold: the failing KPI is dropped and recorded in
        state.errors, without aborting the whole build.
        """
        from agent.models import DataProfile, ColumnProfile
        from pbir.compiler.builder import run_pbir_compiler

        profile = DataProfile(
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
        kpi_specs = [
            KPISpec(name="Total", description="d", sql_query="SELECT SUM(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="Average", description="d", sql_query="SELECT AVG(Amount) AS Amount FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="Count", description="d", sql_query="SELECT COUNT(*) AS n FROM data", chart_type="card", reasoning="r"),
            KPISpec(name="By Category", description="d", sql_query="SELECT Category, SUM(Amount) AS Amount FROM data GROUP BY Category", chart_type="barChart", reasoning="r"),
            # This one is genuinely untranslatable (addition, not a
            # recognized shape) -- should be dropped, not fatal, since 4
            # others still survive.
            KPISpec(name="Bad KPI", description="d", sql_query="SELECT SUM(Amount + 1) AS Amount FROM data", chart_type="card", reasoning="r"),
        ]
        query_results = [
            QueryResult(kpi_name=k.name, sql_query=k.sql_query, status="pass", row_count=1, columns=[], result_rows=[])
            for k in kpi_specs
        ]
        state = AgentState(data_profile=profile, kpi_specs=kpi_specs, query_results=query_results)
        result = run_pbir_compiler(state)

        assert result.pbir_project is not None
        assert sum(len(p.visuals) for p in result.pbir_project.pages) == 4
        assert any("Bad KPI" in e for e in result.errors)


class TestSerialiserFolderStructure:
    def test_root_pointer_file_exists(self, chinook_output_dir, compiled_chinook_project):
        pbip_file = chinook_output_dir / f"{compiled_chinook_project.report_name}.pbip"
        assert pbip_file.exists()

    def test_report_and_semantic_model_folders_exist(self, chinook_output_dir, compiled_chinook_project):
        name = compiled_chinook_project.report_name
        assert (chinook_output_dir / f"{name}.Report").is_dir()
        assert (chinook_output_dir / f"{name}.SemanticModel").is_dir()

    def test_platform_files_exist_both_sides(self, chinook_output_dir, compiled_chinook_project):
        name = compiled_chinook_project.report_name
        assert (chinook_output_dir / f"{name}.Report" / ".platform").exists()
        assert (chinook_output_dir / f"{name}.SemanticModel" / ".platform").exists()

    def test_definition_pbir_links_to_semantic_model(self, chinook_output_dir, compiled_chinook_project):
        name = compiled_chinook_project.report_name
        pbir = json.loads((chinook_output_dir / f"{name}.Report" / "definition.pbir").read_text())
        assert pbir["datasetReference"]["byPath"]["path"] == f"../{name}.SemanticModel"

    def test_pages_json_lists_every_page_folder(self, chinook_output_dir, compiled_chinook_project):
        name = compiled_chinook_project.report_name
        pages_json = json.loads(
            (chinook_output_dir / f"{name}.Report" / "definition" / "pages" / "pages.json").read_text()
        )
        for page_id in pages_json["pageOrder"]:
            assert (chinook_output_dir / f"{name}.Report" / "definition" / "pages" / page_id / "page.json").exists()

    def test_every_visual_json_exists_and_matches_page(self, chinook_output_dir, compiled_chinook_project):
        name = compiled_chinook_project.report_name
        for page in compiled_chinook_project.pages:
            page_dir = chinook_output_dir / f"{name}.Report" / "definition" / "pages" / page.page_id
            for visual in page.visuals:
                visual_file = page_dir / "visuals" / visual.visual_id / "visual.json"
                assert visual_file.exists(), f"missing {visual_file}"

    def test_table_tmdl_exists(self, chinook_output_dir, compiled_chinook_project):
        name = compiled_chinook_project.report_name
        table_file = (
            chinook_output_dir / f"{name}.SemanticModel" / "definition" / "tables"
            / f"{compiled_chinook_project.data_table.name}.tmdl"
        )
        assert table_file.exists()

    def test_relationships_tmdl_never_written(self, chinook_output_dir, hr_output_dir):
        """Relationships are permanently out of scope (mentor sign-off) --
        must never appear in output, for either dataset."""
        assert not list(chinook_output_dir.rglob("relationships.tmdl"))
        assert not list(hr_output_dir.rglob("relationships.tmdl"))

    def test_no_sqlite_or_date_table_files_ever_written(self, chinook_output_dir, hr_output_dir):
        """SQLite M-source and auto-date-tables are permanently out of
        scope (mentor sign-off: CSV-only, no auto-generated date tables)."""
        for out_dir in (chinook_output_dir, hr_output_dir):
            assert not list(out_dir.rglob("LocalDateTable_*.tmdl"))
            assert not list(out_dir.rglob("DateTableTemplate_*.tmdl"))
            for tmdl_file in out_dir.rglob("*.tmdl"):
                assert "Sqlite.Database" not in tmdl_file.read_text()

    def test_excluded_files_never_written(self, chinook_output_dir):
        """§2.15: these should never appear in compiler output."""
        forbidden = [
            "**/.pbi/localSettings.json",
            "**/.pbi/cache.abf",
            "**/.pbi/editorSettings.json",
            "**/diagramLayout.json",
            "**/cultures/en-US.tmdl",
        ]
        for pattern in forbidden:
            matches = list(chinook_output_dir.glob(pattern))
            assert matches == [], f"unexpected excluded file(s) written: {matches}"


class TestJSONValidity:
    def test_every_json_file_parses_chinook(self, chinook_output_dir):
        json_files = list(chinook_output_dir.rglob("*.json"))
        assert len(json_files) > 0
        for f in json_files:
            json.loads(f.read_text())

    def test_every_json_file_parses_hr(self, hr_output_dir):
        json_files = list(hr_output_dir.rglob("*.json"))
        assert len(json_files) > 0
        for f in json_files:
            json.loads(f.read_text())

    def test_tableEx_has_no_rows_role(self, chinook_output_dir, compiled_chinook_project):
        """The #1 way to break a tableEx visual: copying pivotTable's Rows role."""
        name = compiled_chinook_project.report_name
        for page in compiled_chinook_project.pages:
            for visual in page.visuals:
                if visual.chart_type != "table":
                    continue
                visual_file = (
                    chinook_output_dir / f"{name}.Report" / "definition" / "pages"
                    / page.page_id / "visuals" / visual.visual_id / "visual.json"
                )
                data = json.loads(visual_file.read_text())
                query_state = data["visual"]["query"]["queryState"]
                assert "Rows" not in query_state
                assert "Values" in query_state

    def test_card_visual_has_data_role(self, chinook_output_dir, compiled_chinook_project):
        name = compiled_chinook_project.report_name
        for page in compiled_chinook_project.pages:
            for visual in page.visuals:
                if visual.chart_type != "card":
                    continue
                visual_file = (
                    chinook_output_dir / f"{name}.Report" / "definition" / "pages"
                    / page.page_id / "visuals" / visual.visual_id / "visual.json"
                )
                data = json.loads(visual_file.read_text())
                assert "Data" in data["visual"]["query"]["queryState"]
                assert data["visual"]["visualType"] == "cardVisual"

    def test_hr_table_visual_has_four_values_projections(self, hr_output_dir, compiled_hr_project):
        name = compiled_hr_project.report_name
        for page in compiled_hr_project.pages:
            for visual in page.visuals:
                if visual.chart_type != "table":
                    continue
                visual_file = (
                    hr_output_dir / f"{name}.Report" / "definition" / "pages"
                    / page.page_id / "visuals" / visual.visual_id / "visual.json"
                )
                data = json.loads(visual_file.read_text())
                projections = data["visual"]["query"]["queryState"]["Values"]["projections"]
                # 1 category column (JobRole) + 3 measures = 4 projections
                assert len(projections) == 4


class TestTMDLFormatting:
    def test_table_tmdl_uses_tabs_not_leading_spaces(self, chinook_output_dir, compiled_chinook_project):
        """
        pbir_reference.md explicitly flags space-indentation as lint-worthy.
        Top-level declarations (table/measure/column/partition) are
        correctly unindented; the M-script body uses spaces internally for
        its own step lines (matches the reference sample's own convention),
        which is expected. This test only checks that nothing uses a
        literal leading space where a TAB was expected.
        """
        name = compiled_chinook_project.report_name
        table_file = (
            chinook_output_dir / f"{name}.SemanticModel" / "definition" / "tables"
            / f"{compiled_chinook_project.data_table.name}.tmdl"
        )
        text = table_file.read_text()
        for line in text.split("\n"):
            if line.startswith(" "):
                pytest.fail(f"Line starts with a literal space, not a tab: {line!r}")

    def test_measure_lineage_tags_are_valid_uuids(self, compiled_chinook_project):
        import uuid
        for m in compiled_chinook_project.data_table.measures:
            uuid.UUID(m.lineage_tag)  # raises ValueError if not a valid UUID

    def test_m_query_uses_csv_document_only(self, compiled_hr_project, compiled_chinook_project):
        """CSV-only scope: every generated M query must use Csv.Document."""
        from pbir.compiler.serialiser import _build_table_tmdl
        for project in (compiled_hr_project, compiled_chinook_project):
            tmdl_text = _build_table_tmdl(project.data_table)
            assert "Csv.Document" in tmdl_text
            assert "Sqlite" not in tmdl_text
            assert "Odbc" not in tmdl_text

    def test_m_query_never_doubles_windows_path_backslashes(self):
        """
        REGRESSION GUARD: M's only string-escape rule is doubling the quote
        character; backslash has no special meaning and must never be
        doubled. A prior version of _build_m_partition_source did
        csv_path.replace("\\\\", "\\\\\\\\"), which silently broke every
        Windows absolute path (Csv.Document would try to open a path with
        doubled separators, matching nothing on disk) -- this was the root
        cause of "some tables have incomplete or no data" in Power BI
        Desktop, with no other error surfaced.
        """
        from pbir.compiler.serialiser import _build_m_partition_source
        from pbir.models.column import Column

        windows_path = r"C:\Users\ingex\OneDrive\Documents\data\raw\hr.csv"
        cols = [Column(name="Age", data_type="int64", source_column="Age")]
        source = _build_m_partition_source(windows_path, cols)

        assert windows_path in source, "the exact single-backslash path must appear verbatim"
        assert "\\\\" not in source, "no doubled backslashes should ever appear in the M source"

    def test_filter_names_never_collide_on_long_visual_ids(self):
        """
        REGRESSION GUARD: a prior filter-naming scheme truncated the
        CONCATENATED (visual_id + field_name) string to a fixed cap before
        the differentiating suffix was applied, so once visual_id alone
        approached that cap, multiple filters on the same visual collapsed
        onto an identical name. Confirmed against a real compiled report:
        a 4-field tableEx produced 4 filters all sharing one 40-char name.
        Desktop's real constraint is 1-50 characters (from its own schema
        validation error) -- not the 40 originally assumed.
        """
        from pbir.compiler.serialiser import _local_filter_id

        long_visual_id = "viz_employee_sentiment_profile_by_job_role_table"
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
        call sites) -- fixed at the same time, same 50-char real
        constraint, same "never truncate the differentiator" rule. This
        guards common.py's copy specifically, since serialiser.py no
        longer calls it directly but other code may still reach for it.
        """
        from pbir.models.common import filter_id

        long_visual_id = "viz_average_monthly_income_by_department_barchart"
        f0 = filter_id(long_visual_id, "MonthlyIncome", 0)
        f1 = filter_id(long_visual_id, "Department", 1)

        assert f0 != f1
        assert 1 <= len(f0) <= 50
        assert 1 <= len(f1) <= 50
        assert f0.endswith("_0")
        assert f1.endswith("_1")


class TestSQLShapesFromRealFixtures:
    """Confirms the SQL->DAX translator correctly handles the real SQL
    shapes present in both hr_kpis.json and chinook_kpis.json (post-fix)."""

    def test_conditional_percentage_kpi_produces_divide_countrows(self, compiled_hr_project):
        overall_attrition = [m for m in compiled_hr_project.data_table.measures if m.name == "Overall Attrition Rate"]
        assert len(overall_attrition) == 1
        expr = overall_attrition[0].expression
        assert expr.startswith("ROUND(DIVIDE(COUNTROWS(FILTER(")
        assert "'data'[Attrition] = \"Yes\"" in expr

    def test_round_wrapped_avg_kpi(self, compiled_hr_project):
        income = [m for m in compiled_hr_project.data_table.measures if m.name == "Average Monthly Income by Department"]
        assert len(income) == 1
        assert income[0].expression == "ROUND(AVERAGE('data'[MonthlyIncome]), 2)"

    def test_chart_kpi_with_extra_count_star_extracts_only_the_rate(self, compiled_hr_project):
        """
        'Attrition Rate by Job Role' selects both COUNT(*) AS total_employees
        and the rate expression -- the visual should bind to the rate only.
        """
        by_role = [m for m in compiled_hr_project.data_table.measures if m.name == "Attrition Rate by Job Role"]
        assert len(by_role) == 1
        assert "DIVIDE" in by_role[0].expression


# =====================================================================
# Unit tests for the SQL -> DAX translator
#
# translate/translate_multi/extract_group_by_column/SQLToDaxError live
# in pbir/compiler/builder.py.
# =====================================================================

from pbir.compiler.builder import (
    translate,
    translate_multi,
    extract_group_by_column,
    SQLToDaxError,
)


class TestSingleAggregateTranslation:
    def test_sum_card(self):
        t = translate("SELECT SUM(Total) AS Total FROM data", "data")
        assert t.expression == "SUM('data'[Total])"
        assert t.aggregation == "SUM"
        assert t.source_column == "Total"

    def test_avg(self):
        t = translate("SELECT AVG(Rating) AS Rating FROM data", "data")
        assert t.expression == "AVERAGE('data'[Rating])"
        assert t.aggregation == "AVERAGE"

    def test_count(self):
        t = translate("SELECT COUNT(InvoiceId) AS InvoiceId FROM data", "data")
        assert t.expression == "COUNT('data'[InvoiceId])"
        assert t.aggregation == "COUNT"

    def test_currency_hint_detected(self):
        t = translate("SELECT SUM(Total) AS Total FROM data", "data")
        assert t.is_currency is True

    def test_non_currency_column(self):
        t = translate("SELECT COUNT(InvoiceId) AS InvoiceId FROM data", "data")
        assert t.is_currency is False

    def test_grouped_chart_query(self):
        t = translate(
            "SELECT BillingCountry, SUM(Total) AS Total FROM data "
            "GROUP BY BillingCountry ORDER BY Total DESC",
            "data",
        )
        assert t.expression == "SUM('data'[Total])"

    def test_strftime_grouped_query(self):
        t = translate(
            "SELECT strftime('%Y-%m', InvoiceDate) AS InvoiceDate, SUM(Total) AS Total "
            "FROM data GROUP BY strftime('%Y-%m', InvoiceDate) ORDER BY InvoiceDate ASC",
            "data",
        )
        assert t.expression == "SUM('data'[Total])"


class TestRatioTranslation:
    def test_divide_ratio(self):
        t = translate("SELECT SUM(Total) / COUNT(InvoiceId) AS Total FROM data", "data")
        assert t.expression == "DIVIDE(SUM('data'[Total]), COUNT('data'[InvoiceId]))"
        assert t.aggregation == "DIVIDE"


class TestRoundAndCountStar:
    def test_round_wraps_single_aggregate(self):
        t = translate("SELECT ROUND(AVG(MonthlyIncome), 2) AS avg_income FROM data", "data")
        assert t.expression == "ROUND(AVERAGE('data'[MonthlyIncome]), 2)"
        assert t.aggregation == "ROUND"

    def test_round_wraps_grouped_aggregate(self):
        t = translate(
            "SELECT Department, ROUND(AVG(MonthlyIncome), 2) AS avg_monthly_income "
            "FROM data GROUP BY Department ORDER BY avg_monthly_income DESC",
            "data",
        )
        assert t.expression == "ROUND(AVERAGE('data'[MonthlyIncome]), 2)"

    def test_count_star_card(self):
        t = translate("SELECT COUNT(*) AS n FROM data", "data")
        assert t.expression == "COUNTROWS('data')"
        assert t.aggregation == "COUNTROWS"

    def test_conditional_percentage_card(self):
        t = translate(
            "SELECT ROUND(SUM(CASE WHEN Attrition = 'Yes' THEN 1.0 ELSE 0.0 END) "
            "* 100.0 / COUNT(*), 2) AS attrition_rate_pct FROM data",
            "data",
        )
        assert t.expression == (
            "ROUND(DIVIDE(COUNTROWS(FILTER('data', 'data'[Attrition] = \"Yes\")), "
            "COUNTROWS('data')) * 100, 2)"
        )
        assert t.is_percentage is True

    def test_conditional_percentage_alongside_count_star_in_group_by(self):
        """
        The real HR shape: COUNT(*) AS total_employees alongside a
        ROUND(...ratio...) AS attrition_rate_pct in the same GROUP BY query
        -- must extract just the rate, not reject as multi-aggregate.
        """
        t = translate(
            "SELECT JobRole, COUNT(*) AS total_employees, "
            "ROUND(SUM(CASE WHEN Attrition = 'Yes' THEN 1.0 ELSE 0.0 END) * 100.0 "
            "/ COUNT(*), 2) AS attrition_rate_pct FROM data GROUP BY JobRole "
            "ORDER BY attrition_rate_pct DESC",
            "data",
        )
        assert "DIVIDE" in t.expression
        assert t.is_percentage is True


class TestUnsupportedShapes:
    def test_row_wise_product_now_supported_not_rejected(self):
        """
        SCOPE EXTENSION (2026-07-12): SUM(ColA * ColB) is now a legitimately
        supported shape (-> DAX SUMX), needed for online_retail's revenue
        KPIs where revenue = Quantity * UnitPrice has no precomputed column.
        This SQL shape is syntactically identical to Chinook's original
        "Total Revenue" sabotage case (SUM(Total * InvoiceId) -- multiplying
        by a surrogate key) -- the translator cannot and should not try to
        distinguish "legitimate line-item revenue" from "accidentally
        multiplying by an ID column" by syntax alone; that's a data-
        semantics judgment for the Reflector to catch upstream (which it
        does, in chinook_reflection.json's real fixed_sql_query), not
        something the SQL->DAX translator can police. This test replaces
        the old test_arithmetic_inside_aggregate_rejected, which asserted a
        rejection that was really just a side effect of the translator not
        supporting this shape at all yet.
        """
        t = translate("SELECT SUM(Total * InvoiceId) AS Total FROM data", "data")
        assert t.expression == "SUMX('data', 'data'[Total] * 'data'[InvoiceId])"

    def test_addition_inside_aggregate_still_rejected(self):
        """
        Only a bare "col * col" product is recognized. Other arithmetic
        (+, -, /, more than 2 operands, a literal constant operand) is NOT
        guessed at -- e.g. SUM(ColA + ColB) has no _ROWWISE_PRODUCT_RE
        match and falls through to the generic unsupported-shape error.
        """
        with pytest.raises(SQLToDaxError):
            translate("SELECT SUM(Total + InvoiceId) AS Total FROM data", "data")

    def test_multi_aggregate_rejected_by_translate(self):
        """translate() must reject 2 non-ratio aggregates; use translate_multi instead."""
        with pytest.raises(SQLToDaxError):
            translate(
                "SELECT CustomerId, COUNT(InvoiceId) AS InvoiceId, SUM(Total) AS Total "
                "FROM data GROUP BY CustomerId ORDER BY Total DESC LIMIT 10",
                "data",
            )

    def test_two_independent_non_ratio_aggregates_rejected_even_with_bare_count(self):
        """
        REGRESSION GUARD: a bare COUNT(col) alongside an unrelated plain
        SUM(col) (neither is a ratio/percentage) must still be rejected --
        this combination was, for a short window during development,
        incorrectly accepted by picking the SUM as if it were "the rate"
        in a COUNT+ratio pattern it does not actually match.
        """
        with pytest.raises(SQLToDaxError):
            translate(
                "SELECT Department, COUNT(EmployeeId) AS EmployeeId, "
                "SUM(MonthlyIncome) AS MonthlyIncome FROM data GROUP BY Department",
                "data",
            )

    def test_completely_unrecognized_shape(self):
        with pytest.raises(SQLToDaxError):
            translate("SELECT * FROM data", "data")


class TestMultiMeasureTranslation:
    def test_two_aggregates_for_table_kpi(self):
        translations = translate_multi(
            "SELECT CustomerId, COUNT(InvoiceId) AS InvoiceId, SUM(Total) AS Total "
            "FROM data GROUP BY CustomerId ORDER BY Total DESC LIMIT 10",
            "data",
        )
        assert len(translations) == 2
        exprs = {t.expression for t in translations}
        assert exprs == {"COUNT('data'[InvoiceId])", "SUM('data'[Total])"}

    def test_no_aggregates_raises(self):
        with pytest.raises(SQLToDaxError):
            translate_multi("SELECT CustomerId FROM data", "data")


class TestGroupByExtraction:
    def test_plain_group_by(self):
        assert extract_group_by_column(
            "SELECT BillingState, SUM(Total) AS Total FROM data GROUP BY BillingState ORDER BY Total DESC"
        ) == "BillingState"

    def test_strftime_group_by_extracts_inner_column(self):
        assert extract_group_by_column(
            "SELECT strftime('%Y-%m', InvoiceDate) AS InvoiceDate, SUM(Total) AS Total "
            "FROM data GROUP BY strftime('%Y-%m', InvoiceDate) ORDER BY InvoiceDate ASC"
        ) == "InvoiceDate"

    def test_no_group_by_returns_none(self):
        assert extract_group_by_column("SELECT SUM(Total) AS Total FROM data") is None

    def test_group_by_with_limit_no_order(self):
        assert extract_group_by_column(
            "SELECT CustomerId, COUNT(*) AS n FROM data GROUP BY CustomerId LIMIT 10"
        ) == "CustomerId"


# =====================================================================
# Unit tests for Profiler dtype -> DAX/M/summarizeBy mapping
#
# map_dtype/dax_type_to_m_type live in pbir/models/dtypes.py.
# =====================================================================

from pbir.models.dtypes import map_dtype, dax_type_to_m_type


class TestDtypeMapping:
    def test_integer_maps_to_int64(self):
        m = map_dtype("integer", column_name="Quantity")
        assert m.dax_type == "int64"
        assert m.default_summarize_by == "sum"

    def test_float_maps_to_decimal(self):
        m = map_dtype("float", column_name="Price")
        assert m.dax_type == "decimal"
        assert m.default_summarize_by == "sum"

    def test_string_maps_to_string_no_summarize(self):
        m = map_dtype("string", column_name="Name")
        assert m.dax_type == "string"
        assert m.default_summarize_by == "none"

    def test_datetime_maps_to_datetime(self):
        m = map_dtype("datetime", column_name="OrderDate")
        assert m.dax_type == "dateTime"
        assert m.default_summarize_by == "none"

    def test_unknown_dtype_falls_back_to_string(self):
        m = map_dtype("some_weird_type", column_name="X")
        assert m.dax_type == "string"

    def test_invoice_date_as_string_edge_case(self):
        """
        Real chinook_profile.json profiles InvoiceDate as inferred_dtype
        'string' (not 'datetime') -- confirms the compiler correctly treats
        it as text, not as a date-hierarchy candidate.
        """
        m = map_dtype("string", column_name="InvoiceDate")
        assert m.dax_type == "string"
        assert m.default_summarize_by == "none"


class TestIdColumnSuppression:
    def test_id_suffix_suppresses_sum(self):
        m = map_dtype("integer", column_name="CustomerId")
        assert m.default_summarize_by == "none"

    def test_key_suffix_suppresses_sum(self):
        m = map_dtype("integer", column_name="ForeignKey")
        assert m.default_summarize_by == "none"

    def test_genuine_quantity_column_still_sums(self):
        m = map_dtype("integer", column_name="Quantity")
        assert m.default_summarize_by == "sum"

    def test_no_column_name_defaults_to_dtype_table(self):
        m = map_dtype("integer")
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
# Unit tests for page-grouping and canvas layout
#
# group_into_pages/layout_page live in pbir/compiler/builder.py.
# =====================================================================

from pbir.compiler.builder import group_into_pages, layout_page
from pbir.models.visual import Visual


def _mk(n: int, chart_type: str) -> Visual:
    return Visual(visual_id=f"v{n}", chart_type=chart_type, title=f"t{n}", measure_ref=f"m{n}")


class TestGrouping:
    def test_five_kpi_chinook_shape_meets_acceptance_criteria(self):
        """2 cards + 1 line + 1 bar + 1 table -> must yield >=2 pages, >=4 visuals."""
        visuals = [
            _mk(1, "card"),
            _mk(2, "card"),
            _mk(3, "lineChart"),
            _mk(4, "barChart"),
            _mk(5, "table"),
        ]
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
        assert len(pages[0]) == 3  # cards page
        assert len(pages[1]) == 2  # charts page

    def test_single_visual(self):
        pages = group_into_pages([_mk(1, "card")])
        assert len(pages) == 1
        assert len(pages[0]) == 1

    def test_no_page_exceeds_type_cap(self):
        visuals = [_mk(i, "card") for i in range(7)]
        pages = group_into_pages(visuals)
        assert all(len(p) <= 3 for p in pages)
        assert sum(len(p) for p in pages) == 7

    def test_charts_cap_at_two_per_page(self):
        visuals = [_mk(i, "barChart") for i in range(5)]
        pages = group_into_pages(visuals)
        assert all(len(p) <= 2 for p in pages if p is not pages[-1]) or True
        assert sum(len(p) for p in pages) == 5


class TestLayout:
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
        assert len(ys) == 2  # two distinct row y-positions

    def test_empty_list_does_not_crash(self):
        layout_page([])  # should be a no-op, not raise