"""
Serialiser — writes PBIRProject model to the correct .pbip folder layout
(pbir_reference.md §1):

  <n>.pbip
  <n>.Report/
    .platform
    definition.pbir
    definition/
      report.json
      version.json
      pages/
        pages.json
        <pageId>/
          page.json
          visuals/
            <visualId>/
              visual.json
    StaticResources/SharedResources/BaseThemes/<theme>.json
  <n>.SemanticModel/
    .platform
    definition.pbism
    definition/
      database.tmdl
      model.tmdl
      tables/
        <table>.tmdl

Scope (mentor-confirmed, minimal): CSV source only, single table, no
relationships, no auto-generated date tables, no hierarchies.

Excluded entirely (§2.15): .pbi/localSettings.json, .pbi/cache.abf,
.pbi/editorSettings.json, diagramLayout.json, definition/cultures/en-US.tmdl.

This module is organized into sectioned regions below: fully-fixed
templates, the Power Query M partition-source builder, pages.json/
page.json builders, the <table>.tmdl builder, the visual.json builder, and
finally the top-level write_pbip orchestration. Everything above
write_pbip is a private (underscore-prefixed) module-level helper, except
_build_table_tmdl, which stays directly importable under that name because
it is exercised directly by its own unit test in
tests/test_pbir_compiler.py (TestTMDLFormatting.test_m_query_uses_csv_document_only),
in addition to being used internally by write_pbip below.
"""
from __future__ import annotations

import json
from pathlib import Path

from pbir.models.project import PBIRProject
from pbir.models.page import Page
from pbir.models.table import DataTable
from pbir.models.column import Column
from pbir.models.common import filter_id
from pbir.models.field_ref import (
    column_field,
    measure_field,
    column_projection,
    measure_projection,
    sort_entry,
)
from pbir.models.visual import Visual
from pbir.models.dtypes import dax_type_to_m_type


# =====================================================================
# Fully-fixed templates
#
# Fully fixed, copied near-verbatim per run with only name/GUID
# substitution (pbir_reference.md §2.15, §5 "Fully fixed, copy verbatim"
# row).
#
# NOTE on theme JSONs: pbir_reference.md says to bundle the two
# MS-shipped theme files (StaticResources/SharedResources/BaseThemes/
# CY26SU05.json and BuiltInThemes/AccessibleCityPark.json) verbatim. We
# do not have the actual byte content of those two files -- only their
# names, from report.json's themeCollection block. Rather than
# fabricate JSON that looks plausible but isn't Microsoft's real theme
# schema (which could silently fail to parse or render wrong in
# Desktop), this section ships a minimal, schema-valid theme JSON of
# its own and points both baseTheme/customTheme names at it. This is a
# flagged placeholder, not a verified-accurate MS theme file -- swap in
# the real files (Power BI Desktop ships them under its install
# directory) before relying on exact visual styling matching a real
# export.
# =====================================================================

_REPORT_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.4.0/schema.json"
_VERSION_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"
_PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
_PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
_VISUAL_CONTAINER_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"
_PLATFORM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"

_THEME_NAME = "PBIRCompilerDefault"


def _platform_json(item_type: str, display_name: str, logical_id: str) -> dict:
    """.platform file, identical shape for both .Report and .SemanticModel (§2.2)."""
    return {
        "$schema": _PLATFORM_SCHEMA,
        "metadata": {"type": item_type, "displayName": display_name},
        "config": {"version": "2.0", "logicalId": logical_id},
    }


def _definition_pbir_json(semantic_model_folder_name: str) -> dict:
    """definition.pbir — links Report to SemanticModel (§2.3)."""
    return {
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{semantic_model_folder_name}"}},
    }


def _definition_pbism_json() -> dict:
    """definition.pbism — near-empty, fully fixed (§2.9)."""
    return {"version": "4.2", "settings": {}}


def _version_json() -> dict:
    """version.json — fully fixed (§2.5)."""
    return {"$schema": _VERSION_SCHEMA, "version": "2.0.0"}


def _pbip_root_json(report_folder_name: str) -> dict:
    """<n>.pbip root pointer file (§2.1)."""
    return {
        "version": "1.0",
        "artifacts": [{"report": {"path": report_folder_name}}],
        "settings": {"enableAutoRecovery": True},
    }


def _report_json() -> dict:
    """
    report.json — theme + report-level settings (§2.4). Treated as a static
    template per the reference doc; theme names point at the bundled
    placeholder theme (see section docstring above).
    """
    return {
        "$schema": _REPORT_SCHEMA,
        "themeCollection": {
            "baseTheme": {
                "name": _THEME_NAME,
                "reportVersionAtImport": "5.55",
                "type": "SharedResources",
            },
            "customTheme": {
                "name": _THEME_NAME,
                "reportVersionAtImport": "5.55",
                "type": "SharedResources",
            },
        },
        "objects": {
            "section": [
                {
                    "properties": {
                        "verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}
                    },
                    "selector": {"id": "default"},
                }
            ]
        },
        "resourcePackages": [
            {
                "resourcePackage": {
                    "name": "SharedResources",
                    "type": "SharedResources",
                    "items": [
                        {
                            "type": "BaseTheme",
                            "name": _THEME_NAME,
                            "path": f"BaseThemes/{_THEME_NAME}.json",
                        }
                    ],
                }
            }
        ],
        "settings": {
            "useNewFilterPaneExperience": True,
            "allowChangeFilterTypes": True,
            "useStylableVisualContainerHeader": True,
            "exportDataMode": "Underlying",
        },
    }


def _theme_json() -> dict:
    """
    Minimal, schema-valid Power BI theme. See section docstring above: this
    is a flagged placeholder, not the verified real MS theme file content.
    """
    return {
        "name": _THEME_NAME,
        "dataColors": [
            "#1A6B6B", "#C97B4A", "#3E5C76", "#8A9B6E",
            "#B85C5C", "#6C5B7B", "#D4A24C", "#4C7A8C",
        ],
        "background": "#FFFFFF",
        "foreground": "#252423",
        "tableAccent": "#1A6B6B",
    }


# --- TMDL fixed templates (§2.10, §2.9-equivalent for TMDL side) ---

_DATABASE_TMDL = "database\n\tcompatibilityLevel: 1600\n"


def _model_tmdl(table_name: str) -> str:
    """
    model.tmdl (§2.11). `ref table` line is dynamic (must match the single
    tables/*.tmdl file that exists) but the header block and annotations
    are fixed boilerplate. Single-table scope only (mentor sign-off: no
    relationships, no auto-generated date tables).
    """
    lines = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        f"annotation PBI_QueryOrder = {_m_string_array([table_name])}",
        'annotation PBI_ProTooling = ["DevMode"]',
        "",
        f"ref table {table_name}",
        "",
        "ref cultureInfo en-US",
        "",
    ]
    return "\n".join(lines)


def _m_string_array(values: list[str]) -> str:
    quoted = ", ".join(f'"{v}"' for v in values)
    return f"[{quoted}]"


# --- Excluded files: intentionally never written (§2.15) ---
# .pbi/localSettings.json (x2), .pbi/cache.abf, .pbi/editorSettings.json,
# diagramLayout.json, definition/cultures/en-US.tmdl
_EXCLUDED_FILES_NOTE = (
    "The following are never written by this compiler; Power BI Desktop "
    "regenerates them on open: .pbi/localSettings.json (both copies), "
    ".pbi/cache.abf, .pbi/editorSettings.json, diagramLayout.json, "
    "definition/cultures/en-US.tmdl."
)


# =====================================================================
# Power Query M partition-source builder
#
# Builds the Power Query M script for a table's `partition` block
# (pbir_reference.md §2.12).
#
# CSV only, matching what pbir_reference.md documents and confirms
# against a real reverse-engineered export: Csv.Document(...) ->
# Table.PromoteHeaders -> Table.TransformColumnTypes. Cleaning steps
# (Table.ReplaceValue etc.) are explicitly out of scope per the
# reference doc -- only promote-headers + type-casting.
# =====================================================================


def _m_escape_text_literal(value: str) -> str:
    r"""
    Escapes a string for embedding inside an M double-quoted text literal.

    BUG FIX (was the cause of "some tables have incomplete or no data"):
    M's *only* string-escape mechanism is doubling the quote character
    ("" -> a literal "). Unlike Python/C/JSON, backslash has NO special
    meaning inside an M text literal -- it is always a literal character.
    Confirmed directly against pbir_reference.md's own reverse-engineered
    File.Contents(...) call, which embeds a raw Windows path with single,
    un-doubled backslashes (e.g. "C:\Users\ingex\...\Health_Dirty.xlsx").

    The previous version of this function did
    `csv_path.replace("\\", "\\\\")`, which doubled every backslash in
    the absolute CSV path before it was embedded in the M script. M does not
    collapse "\\\\" back down to a single backslash the way Python/JSON
    do, so Csv.Document(File.Contents(...)) ended up trying to open a path
    that literally contained doubled separators and therefore didn't match
    any file on disk -- Power BI Desktop then opens the report with that
    table's partition failing to resolve, which is exactly the "some tables
    have incomplete or no data" dialog. The fix is to leave backslashes
    alone and only double literal quote characters.
    """
    return value.replace('"', '""')


def _build_m_partition_source(csv_path: str, columns: list[Column]) -> str:
    """
    Returns the full M `let...in` script as a string, e.g.:

        let
            Source = Csv.Document(File.Contents("data/raw/hr.csv"), [Delimiter=",", Columns=35, Encoding=65001, QuoteStyle=QuoteStyle.None]),
            #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
            #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{"Age", Int64.Type}, ...})
        in
            #"Changed Type"
    """
    n_cols = len(columns)
    m_path = _m_escape_text_literal(csv_path)

    type_pairs = ", ".join(
        f'{{"{_m_escape_text_literal(col.source_column)}", {dax_type_to_m_type(col.data_type)}}}'
        for col in columns
    )

    lines = [
        "let",
        f'    Source = Csv.Document(File.Contents("{m_path}"), '
        f'[Delimiter=",", Columns={n_cols}, Encoding=65001, QuoteStyle=QuoteStyle.None]),',
        '    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        f'    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{{type_pairs}}})',
        "in",
        '    #"Changed Type"',
    ]
    return "\n".join(lines)


# =====================================================================
# pages.json / page.json builders
# =====================================================================


def _build_pages_json(pages: list) -> dict:
    """
    pages.json -- the ONLY file that knows how many pages exist and in
    what order (§2.6). Regenerated every run.
    """
    return {
        "$schema": _PAGES_SCHEMA,
        "pageOrder": [p.page_id for p in pages],
        "activePageName": pages[0].page_id if pages else "",
    }


def _build_page_json(page: Page) -> dict:
    return {
        "$schema": _PAGE_SCHEMA,
        "name": page.page_id,
        "displayName": page.display_name,
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
    }


# =====================================================================
# <table>.tmdl builder
#
# Writes <table>.tmdl, the core dynamic file (pbir_reference.md §2.12):
# table header, column blocks, measure blocks, partition (M query)
# block, trailing annotations.
#
# TMDL uses tabs for indentation, not spaces (reference doc explicitly
# flags this as lint-worthy) -- every indent in this section is a
# literal \t.
# =====================================================================

_CURRENCY_FORMAT_HINT_ANNOTATION = '\t\tannotation PBI_FormatHint = {"currencyCulture":"en-US"}'


def _measure_block(measure) -> list[str]:
    name = f"'{measure.name}'" if " " in measure.name or "(" in measure.name else measure.name
    lines = [f"\tmeasure {name} = {measure.expression}"]
    if measure.format_string:
        lines.append(f"\t\tformatString: {measure.format_string}")
    lines.append(f"\t\tlineageTag: {measure.lineage_tag}")
    if measure.is_currency:
        lines.append(_CURRENCY_FORMAT_HINT_ANNOTATION)
    lines.append("")
    return lines


def _column_block(column) -> list[str]:
    lines = [f"\tcolumn {column.name}"]
    lines.append(f"\t\tdataType: {column.data_type}")
    if column.format_string:
        lines.append(f"\t\tformatString: {column.format_string}")
    lines.append(f"\t\tlineageTag: {column.lineage_tag}")
    lines.append(f"\t\tsummarizeBy: {column.summarize_by}")
    lines.append(f"\t\tsourceColumn: {column.source_column}")
    lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")
    return lines


def _build_table_tmdl(table: DataTable) -> str:
    lines: list[str] = [f"table {table.name}", f"\tlineageTag: {table.lineage_tag}", ""]

    for measure in table.measures:
        lines.extend(_measure_block(measure))

    for column in table.columns:
        lines.extend(_column_block(column))

    m_source = _build_m_partition_source(table.source_csv_path, table.columns)
    # Reference sample (§2.12) indents the M let/in body with 4 tabs --
    # confirmed by inspecting the raw source of pbir_reference.md's own
    # partition example, which shows "\t\t\t\tlet" / "\t\t\t\tin".
    indented_source = "\n".join(f"\t\t\t\t{line}" if line else "" for line in m_source.split("\n"))

    lines.append(f"\tpartition {table.name} = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append(indented_source)
    lines.append("")
    lines.append("\tannotation PBI_NavigationStepName = Navigation")
    lines.append("\tannotation PBI_ResultType = Table")
    lines.append("")

    return "\n".join(lines)


# =====================================================================
# visual.json builder
#
# Builds visual.json (pbir_reference.md §2.8), the deepest and most
# complex file in the format.
#
# Role shape per visual type (§5 summary table), strictly followed:
#
#     cardVisual            Data role, single Measure projection, no
#                            filter-worthy category.
#     clusteredColumnChart  Category role (plain Column) + Y role
#                            (Measure).
#     lineChart              Same shape as clusteredColumnChart's
#                            Category/Y.
#     tableEx                One role, Values, ALL fields (grouping
#                            column + every measure) as flat sibling
#                            projections. No Rows role -- the #1 way to
#                            break this by copying pivotTable's shape
#                            (§2.8.1). This compiler never emits
#                            pivotTable (KPISpec has no chart_type for
#                            it), so Rows is simply never used.
#
# Scope (mentor-confirmed, minimal): no date-hierarchy binding (§2.8.2's
# HierarchyLevel/PropertyVariationSource group) -- every Category-role
# field is a plain Column projection regardless of the column's dtype,
# since auto-generated date tables/hierarchies are explicitly out of
# scope.
#
# filterConfig is always emitted, one filter per bound field, defaulting
# `type` to "Advanced" (§2.8's documented compiler rule, since no causal
# pattern for Categorical vs Advanced was identified in the samples).
# =====================================================================


def _card_query_state(entity: str, measure_name: str) -> dict:
    return {
        "Data": {
            "projections": [measure_projection(entity, measure_name, active=True)]
        }
    }


def _category_y_query_state(entity: str, category_col: str, measure_name: str) -> dict:
    return {
        "Category": {"projections": [column_projection(entity, category_col, active=True)]},
        "Y": {"projections": [measure_projection(entity, measure_name)]},
    }


def _table_values_query_state(entity: str, category_col, measure_names: list) -> dict:
    projections = []
    if category_col:
        projections.append(column_projection(entity, category_col))
    for m in measure_names:
        projections.append(measure_projection(entity, m))
    return {"Values": {"projections": projections}}


def _filters_for_card(entity: str, measure_name: str) -> list:
    return [
        {
            "name": filter_id("card", measure_name, 0),
            "field": measure_field(entity, measure_name),
            "type": "Advanced",
        }
    ]


def _filters_for_category_y(entity: str, category_col: str, measure_name: str, visual_id: str) -> list:
    return [
        {
            "name": filter_id(visual_id, category_col, 0),
            "field": column_field(entity, category_col),
            "type": "Advanced",
        },
        {
            "name": filter_id(visual_id, measure_name, 1),
            "field": measure_field(entity, measure_name),
            "type": "Advanced",
        },
    ]


def _filters_for_table(entity: str, category_col, measure_names: list, visual_id: str) -> list:
    filters = []
    idx = 0
    if category_col:
        filters.append(
            {
                "name": filter_id(visual_id, category_col, idx),
                "field": column_field(entity, category_col),
                "type": "Advanced",
            }
        )
        idx += 1
    for m in measure_names:
        filters.append(
            {
                "name": filter_id(visual_id, m, idx),
                "field": measure_field(entity, m),
                "type": "Advanced",
            }
        )
        idx += 1
    return filters


def _visual_container_objects(title_text: str) -> dict:
    """
    Fixed per-visual-type chrome template (§2.8: "template, not generated").
    Deliberately minimal -- tableEx and lineChart samples confirmed to ship
    with little-to-no objects/visualContainerObjects at all (§5); an
    empty/near-empty template is a valid choice, not a sign anything's
    missing.
    """
    return {
        "title": [
            {
                "properties": {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "text": {"expr": {"Literal": {"Value": f"'{title_text}'"}}},
                },
                "selector": {"id": "default"},
            }
        ]
    }


def _build_visual_json(visual: Visual, measure_names: list, category_is_date: bool = False) -> dict:
    """
    measure_names: all measure names bound to this visual. Length 1 for
    card/barChart/lineChart; length >=1 for table (may be several sibling
    measures per §2.8.1).

    category_is_date: accepted for call-site stability but always treated
    as False -- date-hierarchy binding is out of scope (mentor sign-off).
    Kept as a parameter rather than removed so callers don't need updating
    if this scope decision is revisited later.
    """
    entity = visual.entity
    primary_measure = measure_names[0]

    if visual.chart_type == "card":
        query_state = _card_query_state(entity, primary_measure)
        filters = _filters_for_card(entity, primary_measure)
        sort = [sort_entry(entity, primary_measure, is_measure=True)]
        container_objects = _visual_container_objects(visual.title)
        objects: dict = {}
    elif visual.chart_type in ("barChart", "lineChart"):
        category_col = visual.category_ref or ""
        query_state = _category_y_query_state(entity, category_col, primary_measure)
        filters = _filters_for_category_y(entity, category_col, primary_measure, visual.visual_id)
        sort = [sort_entry(entity, primary_measure, is_measure=True)]
        container_objects = _visual_container_objects(visual.title)
        objects = {}
    elif visual.chart_type == "table":
        category_col = visual.category_ref
        query_state = _table_values_query_state(entity, category_col, measure_names)
        filters = _filters_for_table(entity, category_col, measure_names, visual.visual_id)
        sort = None
        container_objects = _visual_container_objects(visual.title)
        objects = {}
    else:
        raise ValueError(f"Unsupported chart_type for visual.json: {visual.chart_type!r}")

    query: dict = {"queryState": query_state}
    if sort:
        query["sortDefinition"] = {"sort": sort, "isDefaultSort": True}

    visual_dict = {
        "$schema": _VISUAL_CONTAINER_SCHEMA,
        "name": visual.visual_id,
        "position": {
            "x": visual.position.x,
            "y": visual.position.y,
            "z": visual.position.z,
            "height": visual.position.height,
            "width": visual.position.width,
            "tabOrder": visual.position.tab_order,
        },
        "visual": {
            "visualType": visual.visual_type,
            "query": query,
            "objects": objects,
            "visualContainerObjects": container_objects,
            "drillFilterOtherVisuals": True,
        },
    }
    if filters:
        visual_dict["filterConfig"] = {"filters": filters}

    return visual_dict


# =====================================================================
# Serialiser orchestration
# =====================================================================


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _measure_names_for_visual(project: PBIRProject, visual) -> list:
    """
    Recovers all measure names bound to a given visual. For card/bar/line,
    that's just [visual.measure_ref]. For table visuals with multiple
    sibling measures (§2.8.1), the builder encodes each as
    '<KPI Name> (<column>)' -- match every measure on the table whose name
    starts with the visual's title, since that's the KPI-name prefix
    convention used in builder.py's _build_measures_and_group_cols.
    """
    prefix = visual.title
    matches = [m.name for m in project.data_table.measures if m.name == prefix or m.name.startswith(f"{prefix} (")]
    return matches if matches else [visual.measure_ref]


def write_pbip(project: PBIRProject, output_dir: Path) -> None:
    output_dir = Path(output_dir)
    report_folder_name = f"{project.report_name}.Report"
    semantic_folder_name = f"{project.report_name}.SemanticModel"

    report_dir = output_dir / report_folder_name
    semantic_dir = output_dir / semantic_folder_name

    # --- Root .pbip pointer file ---
    _write_json(output_dir / f"{project.report_name}.pbip", _pbip_root_json(report_folder_name))

    # --- .Report side ---
    _write_json(
        report_dir / ".platform",
        _platform_json("Report", project.report_name, project.report_logical_id),
    )
    _write_json(report_dir / "definition.pbir", _definition_pbir_json(semantic_folder_name))
    _write_json(report_dir / "definition" / "report.json", _report_json())
    _write_json(report_dir / "definition" / "version.json", _version_json())

    _write_json(
        report_dir / "StaticResources" / "SharedResources" / "BaseThemes" / f"{_THEME_NAME}.json",
        _theme_json(),
    )

    _write_json(
        report_dir / "definition" / "pages" / "pages.json",
        _build_pages_json(project.pages),
    )

    for page in project.pages:
        page_dir = report_dir / "definition" / "pages" / page.page_id
        _write_json(page_dir / "page.json", _build_page_json(page))

        for visual in page.visuals:
            measure_names = _measure_names_for_visual(project, visual)
            visual_json = _build_visual_json(visual, measure_names, category_is_date=False)
            visual_dir = page_dir / "visuals" / visual.visual_id
            _write_json(visual_dir / "visual.json", visual_json)

    # --- .SemanticModel side ---
    _write_json(
        semantic_dir / ".platform",
        _platform_json("SemanticModel", project.report_name, project.semantic_model_logical_id),
    )
    _write_json(semantic_dir / "definition.pbism", _definition_pbism_json())
    _write_text(semantic_dir / "definition" / "database.tmdl", _DATABASE_TMDL)

    _write_text(
        semantic_dir / "definition" / "model.tmdl",
        _model_tmdl(project.data_table.name),
    )

    _write_text(
        semantic_dir / "definition" / "tables" / f"{project.data_table.name}.tmdl",
        _build_table_tmdl(project.data_table),
    )