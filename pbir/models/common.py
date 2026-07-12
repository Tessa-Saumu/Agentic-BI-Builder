"""
pbir/models/common.py — shared ID generation and formatting-wrapper helpers.

Two distinct ID schemes are used throughout PBIR (see pbir_reference.md §3):

1. Folder/file IDs (page, visual, filter names) — human-readable deterministic
   slugs are fine; Power BI Desktop does not require Microsoft's exact hex
   generation algorithm, only internal consistency between a folder name and
   the `name` field inside its own .json, plus any place that references it
   (e.g. pages.json.pageOrder).
2. lineageTag / logicalId / relationship GUIDs — these are genuine UUIDs used
   by Power BI's internal change tracking. Always generate real uuid4()
   values for these, never slugs.

Also implements the recurring "expr/Literal" formatting wrapper (§4) used in
report.json, page.json, and every visual.json's objects/visualContainerObjects.
"""
from __future__ import annotations

import re
import uuid


def new_guid() -> str:
    """A fresh UUID4 string, for lineageTag / logicalId / relationship IDs."""
    return str(uuid.uuid4())


def slugify(text: str) -> str:
    """
    Deterministic, human-readable slug for folder/file IDs (page, visual).
    Not a hex ID — Desktop only requires internal consistency (§3), and
    readable slugs make generated projects far easier to debug.
    """
    slug = text.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "item"


def page_slug(display_name: str, index: int) -> str:
    """Deterministic page folder/name id, e.g. 'page_1_overview'."""
    return f"page_{index}_{slugify(display_name)}"


def visual_slug(kpi_name: str, chart_type: str) -> str:
    """Deterministic visual folder/name id, e.g. 'viz_total_revenue_card'."""
    return f"viz_{slugify(kpi_name)}_{slugify(chart_type)}"


def filter_id(visual_slug_value: str, field_name: str, index: int) -> str:
    """
    Short id for filterConfig.filters[].name. Unique only within the
    containing visual's filters[] array is required (§3) — no cross-file
    consistency needed, unlike folder IDs.
    """
    return slugify(f"{visual_slug_value}_{field_name}_{index}")[:40]


def literal_prop(value: str) -> dict:
    """
    The recurring 'expr/Literal' wrapper (§4). Literal values in PBIR are
    always strings, even for numbers/booleans — e.g. "true", "15D" (D suffix
    marks a double), "'left'" (single quotes mark a DAX string literal).
    Caller is responsible for passing the correctly-stringified value.
    """
    return {"expr": {"Literal": {"Value": value}}}


def theme_color_prop(color_id: int, percent: float = 0.0) -> dict:
    """The recurring ThemeDataColor wrapper (§4) for color properties."""
    return {
        "solid": {
            "color": {
                "expr": {
                    "ThemeDataColor": {"ColorId": color_id, "Percent": percent}
                }
            }
        }
    }


def prop_group(properties: dict, selector_id: str = "default") -> list[dict]:
    """
    Wraps a properties dict in the [{properties, selector}] list shape used
    for every entry in objects/visualContainerObjects property groups.
    """
    return [{"properties": properties, "selector": {"id": selector_id}}]