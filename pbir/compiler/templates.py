"""
Fully-fixed JSON templates.

Extracted from serialiser.py's original "Fully-fixed templates"
section (the module docstring's own sectioning). Fully fixed, copied
near-verbatim per run with only name/GUID substitution
(pbir_reference.md Section 2.15, Section 5 "Fully fixed, copy
verbatim" row).

The three schema-URL constants that were originally defined alongside
these (in the same block in the pre-split serialiser.py) but are only
ever USED by functions that stayed in other modules after this split
-- _PAGES_SCHEMA / _PAGE_SCHEMA (used by tmdl.py's pages.json/page.json
builders) and _VISUAL_CONTAINER_SCHEMA (used by visual_json.py's
visual.json builder) -- now live in those modules instead, next to
their one usage site, rather than here where nothing in this file
reads them. _REPORT_SCHEMA, _VERSION_SCHEMA, and _PLATFORM_SCHEMA stay
here because _report_json(), _version_json(), and _platform_json()
(their only users) all stay in this module. No behavior changes as a
result -- every constant's VALUE and every function's OUTPUT is
unchanged; only which .py file each constant is declared in moved, to
sit next to where it's actually read.
"""
from __future__ import annotations

from pathlib import Path


# =====================================================================
# Fully-fixed templates
#
# Fully fixed, copied near-verbatim per run with only name/GUID
# substitution (pbir_reference.md §2.15, §5 "Fully fixed, copy verbatim"
# row).
#
# NOTE on theme JSONs (2026-07-12 fix): the previous version of this
# section shipped a single self-invented placeholder theme
# ("PBIRCompilerDefault") and pointed BOTH baseTheme and customTheme at
# it. That is now replaced with byte-verbatim copies of the two real
# MS-shipped theme files (CY26SU05.json / AccessibleCityPark.json),
# exactly as pbir_reference.md §2.15/§5 specifies ("copy the two files
# verbatim as static assets"). Bundle their real bytes as
# _BASE_THEME_JSON / _CUSTOM_THEME_JSON below (extracted once from a
# known-good Desktop export) rather than reconstructing them field by
# field.
# =====================================================================

_REPORT_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json"
_VERSION_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"
_PLATFORM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"

# Real MS-shipped theme names (see StaticResources/*.json alongside this
# module, or plug in your own bundled bytes -- see _theme_assets() below).
_BASE_THEME_NAME = "CY26SU05"
_CUSTOM_THEME_NAME = "AccessibleCityPark"

# Where the two real, byte-verbatim theme JSON assets are shipped relative
# to this module. Adjust to match wherever you vendor them in your repo
# (e.g. package_data / MANIFEST.in if this ships as an installed package).
_THEME_ASSETS_DIR = Path(__file__).parent / "theme_assets"


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
    template per the reference doc; theme names point at the two real,
    byte-verbatim-bundled MS theme files (see _theme_assets() below).

    FIX (2026-07-12, round 1) — resourcePackages nesting + reportVersionAtImport
    shape (see prior comment in git history / write-up). Fixed a
    NullReferenceException in Desktop's report-view renderer.

    FIX (2026-07-12, round 2) — the round-1 fix left "$schema" pointed at
    report/1.4.0 while giving reportVersionAtImport the object shape that
    belongs to LATER schema versions. Confirmed by fetching Microsoft's
    actual report/3.1.0/schema.json (developer.microsoft.com/json-schemas/
    fabric/item/report/definition/report/3.1.0/schema.json):
      - ThemeVersion (reportVersionAtImport) is an object with
        visual/report/page, each pattern ^[0-9]+\\.[0-9]+\\.[0-9]+$ -- so an
        object is only valid when $schema matches a version that defines it
        that way. Mismatched $schema vs. field shape is exactly what threw
        "was not provided as the correct type".
      - Root-level "required" is only ["$schema", "themeCollection"], with
        additionalProperties: false -- "layoutOptimization" is NOT a
        recognized property at this schema version at all (it belongs to
        older schemas like 1.0.0, which uses the string-shaped
        reportVersionAtImport instead). Do NOT add it here.
      - "settings" (ExplorationSettings) has NO "useNewFilterPaneExperience"
        property (additionalProperties: false rejects it), and
        "exportDataMode" is a const enum of exactly "AllowSummarized" |
        "AllowSummarizedAndUnderlying" | "None" -- "Underlying" is not a
        member.
    Fix: pin $schema to 3.3.0 (matching a real, proven Desktop export) and
    make every field conform to that version, copying the proven report's
    exact reportVersionAtImport/settings values rather than inventing new
    ones.
    """
    return {
        "$schema": _REPORT_SCHEMA,
        "themeCollection": {
            "baseTheme": {
                "name": _BASE_THEME_NAME,
                "reportVersionAtImport": {"visual": "2.9.0", "report": "3.3.0", "page": "2.3.1"},
                "type": "SharedResources",
            },
            "customTheme": {
                "name": _CUSTOM_THEME_NAME,
                "reportVersionAtImport": {"visual": "2.10.0", "report": "3.4.0", "page": "2.3.1"},
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
                "name": "SharedResources",
                "type": "SharedResources",
                "items": [
                    {
                        "type": "CustomTheme",
                        "name": _CUSTOM_THEME_NAME,
                        "path": f"BuiltInThemes/{_CUSTOM_THEME_NAME}.json",
                    },
                    {
                        "type": "BaseTheme",
                        "name": _BASE_THEME_NAME,
                        "path": f"BaseThemes/{_BASE_THEME_NAME}.json",
                    },
                ],
            }
        ],
        "settings": {
            "useStylableVisualContainerHeader": True,
            "exportDataMode": "AllowSummarized",
            "defaultDrillFilterOtherVisuals": True,
            "allowChangeFilterTypes": True,
            "useEnhancedTooltips": True,
            "useDefaultAggregateDisplayName": True,
        },
    }


def _theme_assets() -> dict[str, Path]:
    """
    Maps each theme's on-disk destination (relative to the .Report folder)
    to the source asset file to copy verbatim (§2.15: "Copy the two files
    verbatim as static assets bundled with your compiler rather than
    generating them").

    Ship the two real MS theme files as actual .json assets next to this
    module (e.g. `pbir/serialiser_theme_assets/BaseThemes/CY26SU05.json` and
    `.../BuiltInThemes/AccessibleCityPark.json` -- copy them in verbatim from
    a real Desktop export, or from `reference_report.zip`'s
    StaticResources/SharedResources/ folder) and point _THEME_ASSETS_DIR at
    that folder. This intentionally does NOT regenerate theme JSON from
    scratch -- these are Microsoft-authored files; the compiler's only job
    is to place verbatim copies at the right paths.
    """
    return {
        f"BaseThemes/{_BASE_THEME_NAME}.json": _THEME_ASSETS_DIR / "BaseThemes" / f"{_BASE_THEME_NAME}.json",
        f"BuiltInThemes/{_CUSTOM_THEME_NAME}.json": _THEME_ASSETS_DIR / "BuiltInThemes" / f"{_CUSTOM_THEME_NAME}.json",
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
