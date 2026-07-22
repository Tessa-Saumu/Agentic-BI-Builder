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
    Short id for filterConfig.filters[].name.

    BUG FIX (2026-07-12): the prior version built
    slugify(f"{visual_slug_value}_{field_name}_{index}")[:40] -- truncating
    the CONCATENATED string to a fixed cap. Once visual_slug_value alone
    approached that cap, the differentiating field_name/index suffix got
    sliced off entirely, so multiple filters on the same visual collapsed
    onto an identical name (confirmed against a real compiled report: a
    4-field tableEx produced 4 filters all named
    "viz_employee_sentiment_profile_by_job_ro", each exactly 40 chars).
    Desktop's real constraint (confirmed via its own schema validation
    error) is "1-50 characters", not the 40 originally assumed here.

    Fix: reserve room for the index suffix FIRST, then truncate the base
    (visual_slug_value + field_name) to fit within the real 50-char cap --
    so the differentiator is never what gets cut, and multiple filters on
    one visual are always unique regardless of how long the visual's own
    slug is. This mirrors the fix already applied locally in
    pbir/compiler/serialiser.py's _local_filter_id() for the same bug;
    kept in sync here since this function is still part of the public
    common.py surface other callers may reach for.
    """
    suffix = f"_{index}"
    max_len = 50
    base = slugify(f"{visual_slug_value}_{field_name}")[: max_len - len(suffix)]
    return f"{base}{suffix}"


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