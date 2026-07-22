"""
DataTable — Pydantic model for the semantic model's single data table
(pbir_reference.md §2.12 — "the core dynamic file").

Scope decision (confirmed by mentor sign-off): single table per dataset only.
Every test dataset (Chinook, Online Retail, IBM HR) loads as one SQLite/CSV
table, so multi-table TMDL generality (real FK relationships between two data
tables) is explicitly out of scope for this compiler. Auto-generated date
tables, relationships, and hierarchies are also explicitly out of scope
(mentor sign-off: "do not expand the scope to cover ... auto-generated date
tables ... unless you truly want to experience it").
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from pbir.models.column import Column
from pbir.models.measure import Measure
from pbir.models.common import new_guid


class DataTable(BaseModel):
    name: str = "data"  # matches AgentState's SQL table name convention
    lineage_tag: str = Field(default_factory=new_guid)
    columns: List[Column] = Field(default_factory=list)
    measures: List[Measure] = Field(default_factory=list)

    # .pbip-relative path to the source CSV, for the M partition.
    source_csv_path: str = ""