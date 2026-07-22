"""
pages.json / page.json builders, and the <table>.tmdl builder.

Extracted from serialiser.py's original "pages.json / page.json
builders" and "<table>.tmdl builder" sections (the module docstring's
own sectioning).

Writes pages.json (the ONLY file that knows how many pages exist and
in what order, per pbir_reference.md Section 2.6 -- regenerated every
run) and page.json, plus <table>.tmdl, the core dynamic file (Section
2.12): table header, column blocks, measure blocks, partition (M
query) block, trailing annotations.

TMDL uses tabs for indentation, not spaces (reference doc explicitly
flags this as lint-worthy) -- every indent in the table.tmdl builder
below is a literal tab character.

_PAGES_SCHEMA and _PAGE_SCHEMA moved here from the original
serialiser.py's "Fully-fixed templates" section, alongside their only
usage sites (_build_pages_json, _build_page_json) -- see the note in
templates.py for why. Their VALUES are unchanged.

_build_table_tmdl is exercised directly by its own unit test in
tests/test_pbir_compiler.py (TestTMDLFormatting.
test_m_query_uses_csv_document_only), in addition to being used
internally by serialiser.write_pbip. serialiser.py re-exports it so
`from pbir.compiler.serialiser import _build_table_tmdl` continues to
work unchanged.
"""
from __future__ import annotations

from pbir.models.page import Page
from pbir.models.table import DataTable

from pbir.compiler.m_query import _build_m_partition_source

_PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
_PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"


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

