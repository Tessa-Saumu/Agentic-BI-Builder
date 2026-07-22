"""
Serialiser -- writes PBIRProject model to the correct .pbip folder layout
(pbir_reference.md Section 1):

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
    StaticResources/SharedResources/BaseThemes/<baseTheme>.json
    StaticResources/SharedResources/BuiltInThemes/<customTheme>.json
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

Excluded entirely (Section 2.15): .pbi/localSettings.json,
.pbi/cache.abf, .pbi/editorSettings.json, diagramLayout.json,
definition/cultures/en-US.tmdl.

REFACTORED: this module previously contained five
sections inline (fully-fixed templates; the Power Query M
partition-source builder; pages.json/page.json builders; the
<table>.tmdl builder; the visual.json builder) ahead of the
write_pbip orchestration, totaling ~800 LOC. Those five sections have
been extracted verbatim into their own modules --
pbir/compiler/templates.py, pbir/compiler/m_query.py,
pbir/compiler/tmdl.py, and pbir/compiler/visual_json.py -- leaving
this file as the orchestration layer only: write_pbip() and its
direct helpers (_write_json, _write_text, _measure_names_for_visual).

No logic changed as part of this split -- every function body moved
unmodified; only its containing file changed. Three schema-URL
constants that were originally declared alongside the fully-fixed
templates but are only ever used by code that now lives elsewhere
(_PAGES_SCHEMA, _PAGE_SCHEMA -> tmdl.py; _VISUAL_CONTAINER_SCHEMA ->
visual_json.py) moved with their usage sites rather than staying
behind in templates.py -- see the note at the top of templates.py.

All names that were previously importable from this module
(_build_m_partition_source, _build_table_tmdl, _local_filter_id,
_safe_visual_id, _BASE_THEME_NAME, _CUSTOM_THEME_NAME,
_THEME_ASSETS_DIR, write_pbip) remain importable from here via the
re-export below, so `from pbir.compiler.serialiser import write_pbip`
(etc.) continues to work exactly as before for any existing caller or
test -- see tests/test_pbir_compiler.py, which accesses
_BASE_THEME_NAME and _CUSTOM_THEME_NAME as serialiser.<name> module
attributes (in patched_theme_assets) in addition to importing the
other names directly from this module.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from pbir.models.project import PBIRProject

from pbir.compiler.templates import (
    _pbip_root_json,
    _platform_json,
    _definition_pbir_json,
    _definition_pbism_json,
    _report_json,
    _version_json,
    _theme_assets,
    _THEME_ASSETS_DIR,
    _BASE_THEME_NAME,
    _CUSTOM_THEME_NAME,
    _DATABASE_TMDL,
    _model_tmdl,
)
from pbir.compiler.m_query import _build_m_partition_source
from pbir.compiler.tmdl import _build_pages_json, _build_page_json, _build_table_tmdl
from pbir.compiler.visual_json import _build_visual_json, _safe_visual_id, _local_filter_id

__all__ = [
    "_build_m_partition_source",
    "_build_table_tmdl",
    "_local_filter_id",
    "_safe_visual_id",
    "_BASE_THEME_NAME",
    "_CUSTOM_THEME_NAME",
    "_THEME_ASSETS_DIR",
    "write_pbip",
]


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

    for relative_dest, source_asset in _theme_assets().items():
        dest = report_dir / "StaticResources" / "SharedResources" / relative_dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not source_asset.is_file():
            raise FileNotFoundError(
                f"Theme asset missing: {source_asset}. Vendor the real MS theme "
                f"JSON files under {_THEME_ASSETS_DIR} (see _theme_assets() docstring)."
            )
        shutil.copy2(source_asset, dest)

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
            visual_dir = page_dir / "visuals" / _safe_visual_id(visual.visual_id)
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