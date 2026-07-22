"""
visual.json builder.

Extracted from serialiser.py's original "visual.json builder" section
(the module docstring's own sectioning). Builds visual.json
(pbir_reference.md Section 2.8), the deepest and most complex file in
the format.

Role shape per visual type (Section 5 summary table), strictly
followed:

    cardVisual            Data role, single Measure projection, no
                           filter-worthy category.
    clusteredColumnChart  Category role (plain Column) + Y role
                           (Measure).
    lineChart              Same shape as clusteredColumnChart's
                           Category/Y.
    tableEx                One role, Values, ALL fields (grouping
                           column + every measure) as flat sibling
                           projections. No Rows role -- the #1 way to
                           break this by copying pivotTable's shape
                           (Section 2.8.1). This compiler never emits
                           pivotTable (KPISpec has no chart_type for
                           it), so Rows is simply never used.

Scope (mentor-confirmed, minimal): no date-hierarchy binding (Section
2.8.2's HierarchyLevel/PropertyVariationSource group) -- every
Category-role field is a plain Column projection regardless of the
column's dtype, since auto-generated date tables/hierarchies are
explicitly out of scope.

filterConfig is always emitted, one filter per bound field.

FIX (2026-07-12) -- two bugs fixed here (see the two numbered notes
inline below, carried over unchanged from the original serialiser.py):
filter `name` collisions from a truncation bug in filter_id(), and a
hardcoded "Advanced" filter type that should vary by field kind.

_VISUAL_CONTAINER_SCHEMA moved here from the original serialiser.py's
"Fully-fixed templates" section, alongside its only usage site
(_build_visual_json) -- see the note in templates.py for why. Its
VALUE is unchanged.

_local_filter_id is exercised directly by its own unit tests in
tests/test_pbir_compiler.py (TestTMDLFormatting), in addition to being
used internally by _build_visual_json below. serialiser.py re-exports
it so `from pbir.compiler.serialiser import _local_filter_id`
continues to work unchanged.
"""
from __future__ import annotations

from pbir.models.field_ref import (
    column_field,
    measure_field,
    column_projection,
    measure_projection,
    sort_entry,
)
from pbir.models.visual import Visual

_VISUAL_CONTAINER_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json"


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
# filterConfig is always emitted, one filter per bound field.
#
# FIX (2026-07-12) -- two bugs here:
#
# 1. Filter `name` collisions. filter_id() (pbir/models/common.py, NOT
#    reviewed as part of this fix -- see note below) builds something
#    equivalent to f"{namespace}_{field_name.lower()}"[:40], truncating
#    the CONCATENATED string to a fixed 40-char cap. Once `namespace`
#    (the visual_id) alone reaches ~39-40+ chars, the differentiating
#    field-derived suffix -- and sometimes the trailing `idx` too -- gets
#    sliced off entirely, so multiple filters on the same visual collapse
#    onto an IDENTICAL "name". Confirmed empirically against a real
#    compiled report: e.g. a tableEx with 4 bound fields produced 4
#    filters that all shared the name "viz_employee_sentiment_profile_by_
#    job_ro" (exactly 40 chars, mid-word-truncated). Duplicate keys in a
#    dict-like structure Desktop needs to be unique are a strong
#    candidate for the null-reference crash seen when Desktop tries to
#    build the enhanced report document.
#    Fix: build filter names locally here instead of delegating to
#    filter_id(), with NO length cap, as f"{visual_id}_{idx}". visual_id
#    is already unique per visual across the whole report (confirmed),
#    and idx is unique within one visual's filter list, so this is
#    globally collision-free with zero truncation risk.
#    filter_id() in pbir/models/common.py has the same bug for any other
#    caller -- it wasn't in the files reviewed here, so it still needs
#    fixing at its source; see the accompanying write-up.
#
# 2. `type` was hardcoded to "Advanced" for every field regardless of
#    kind. A real Desktop export consistently uses "Categorical" for
#    plain Column-bound filters and "Advanced" for Measure-bound (and
#    HierarchyLevel) filters -- confirmed across every filterConfig in a
#    known-good reference report, no exceptions. Lower-severity than (1)
#    (an isolated wrong enum value is unlikely to crash Desktop the way a
#    duplicate key can) but fixed here too for fidelity to the proven
#    pattern. _filter_type() below picks it from the field kind.
# =====================================================================


def _filter_type(field: dict) -> str:
    return "Categorical" if "Column" in field else "Advanced"


def _local_filter_id(visual_id: str, idx: int, max_len: int = 50) -> str:
    """Collision-safe filter name: see FIX note above.

    FIX (2026-07-12, round 2): round 1 assumed no length limit existed and
    used f"{visual_id}_{idx}" uncapped. Desktop's validator confirmed a
    real cap: "Filter names cannot be empty and must be between 1 and 50
    characters" -- caught on the one visual whose name is 49 chars
    (viz_average_monthly_income_by_department_barchart + "_0" = 51).
    Reserve space for the "_<idx>" suffix FIRST, then truncate the base to
    fit, so the differentiator is never what gets cut (that was the
    original truncation bug) while the real 50-char ceiling is respected.
    """
    suffix = f"_{idx}"
    base = visual_id[: max_len - len(suffix)]
    return f"{base}{suffix}"


def _safe_visual_id(visual_id: str, max_len: int = 50) -> str:
    """
    Truncates visual_id to Desktop's 50-char limit for the visual's own
    name -- the same cap _local_filter_id above already respects for
    derived filter names, but visual_id itself was never capped at its
    source. visual_slug() (pbir/models/common.py) has no length limit, so
    a sufficiently descriptive KPI name (more common from some LLM
    providers than others) can produce a visual_id over 50 chars, which
    Desktop rejects outright: "The /name property ... exceeded its maximum
    length" plus "Invalid visual name ... must be between 1 and 50
    characters".

    No differentiating suffix is added (unlike _local_filter_id, which
    needs one to keep multiple filters on the same visual apart) --
    visual_id is already unique per KPI before truncation, and two KPI
    names differing only after character 50 is not a case this project
    has hit. If it ever is, this would need the same suffix-reservation
    treatment _local_filter_id already uses.

    Every caller of visual.visual_id must use this function's return
    value consistently (visual directory name, visual.json's own "name",
    and the visual_id passed into _filters_for_card /
    _filters_for_category_y / _filters_for_table) -- using the raw,
    untruncated visual_id in any one of these while truncating it in
    another would make the visual's folder name, its JSON self-reference,
    and its filter names disagree.
    """
    return visual_id[:max_len]


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


def _filters_for_card(entity: str, measure_name: str, visual_id: str) -> list:
    field = measure_field(entity, measure_name)
    return [
        {
            "name": _local_filter_id(visual_id, 0),
            "field": field,
            "type": _filter_type(field),
        }
    ]


def _filters_for_category_y(entity: str, category_col: str, measure_name: str, visual_id: str) -> list:
    col_field = column_field(entity, category_col)
    measure_field_ = measure_field(entity, measure_name)
    return [
        {
            "name": _local_filter_id(visual_id, 0),
            "field": col_field,
            "type": _filter_type(col_field),
        },
        {
            "name": _local_filter_id(visual_id, 1),
            "field": measure_field_,
            "type": _filter_type(measure_field_),
        },
    ]


def _filters_for_table(entity: str, category_col, measure_names: list, visual_id: str) -> list:
    filters = []
    idx = 0
    if category_col:
        col_field = column_field(entity, category_col)
        filters.append(
            {
                "name": _local_filter_id(visual_id, idx),
                "field": col_field,
                "type": _filter_type(col_field),
            }
        )
        idx += 1
    for m in measure_names:
        measure_field_ = measure_field(entity, m)
        filters.append(
            {
                "name": _local_filter_id(visual_id, idx),
                "field": measure_field_,
                "type": _filter_type(measure_field_),
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
    safe_visual_id = _safe_visual_id(visual.visual_id)

    if visual.chart_type == "card":
        query_state = _card_query_state(entity, primary_measure)
        filters = _filters_for_card(entity, primary_measure, safe_visual_id)
        sort = [sort_entry(entity, primary_measure, is_measure=True)]
        container_objects = _visual_container_objects(visual.title)
        objects: dict = {}
    elif visual.chart_type in ("barChart", "lineChart"):
        category_col = visual.category_ref or ""
        query_state = _category_y_query_state(entity, category_col, primary_measure)
        filters = _filters_for_category_y(entity, category_col, primary_measure, safe_visual_id)
        sort = [sort_entry(entity, primary_measure, is_measure=True)]
        container_objects = _visual_container_objects(visual.title)
        objects = {}
    elif visual.chart_type == "table":
        category_col = visual.category_ref
        query_state = _table_values_query_state(entity, category_col, measure_names)
        filters = _filters_for_table(entity, category_col, measure_names, safe_visual_id)
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
        "name": safe_visual_id,
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
