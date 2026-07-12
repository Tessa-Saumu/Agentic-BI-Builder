"""
pbir/models/field_ref.py — field-binding shape builders for visual.json's
query.queryState (pbir_reference.md §2.8).

Two field shapes, matching this compiler's minimal scope (no date
hierarchy -- mentor sign-off excludes auto-generated date tables and
hierarchies):

  - column_field(entity, property)   -> plain Column binding
  - measure_field(entity, property)  -> plain Measure binding
"""
from __future__ import annotations


def column_field(entity: str, property_name: str) -> dict:
    return {
        "Column": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": property_name,
        }
    }


def measure_field(entity: str, property_name: str) -> dict:
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": property_name,
        }
    }


def column_projection(entity: str, property_name: str, *, active: bool = False) -> dict:
    proj = {
        "field": column_field(entity, property_name),
        "queryRef": f"{entity}.{property_name}",
        "nativeQueryRef": property_name,
    }
    if active:
        proj["active"] = True
    return proj


def measure_projection(entity: str, property_name: str, *, active: bool = False) -> dict:
    proj = {
        "field": measure_field(entity, property_name),
        "queryRef": f"{entity}.{property_name}",
        "nativeQueryRef": property_name,
    }
    if active:
        proj["active"] = True
    return proj


def sort_entry(entity: str, property_name: str, *, is_measure: bool, direction: str = "Descending") -> dict:
    """
    sortDefinition.sort[] entry (§2.8). Safe to always include per the
    reference doc ("false/absent is the same as not present").
    """
    field = measure_field(entity, property_name) if is_measure else column_field(entity, property_name)
    return {
        "field": field,
        "direction": direction,
    }