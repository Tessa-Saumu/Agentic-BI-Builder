"""
PBIRProject — top-level model for the full .pbip folder.

Note on ownership: measures belong to the semantic model's DataTable, not
floating at the project root -- this matches how TMDL actually structures
them (a `measure` block lives inside `table <name>` in <table>.tmdl), unlike
the original scaffolding which had a project-level `measures: List[Measure]`
alongside pages.

Scope: no relationships, no auto-generated date tables, single table only
(mentor sign-off).
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from pbir.models.page import Page
from pbir.models.table import DataTable
from pbir.models.common import new_guid


class PBIRProject(BaseModel):
    report_name: str
    pages: List[Page] = Field(default_factory=list)
    data_table: DataTable = Field(default_factory=DataTable)

    # Source metadata (from DataProfile) -- carried through so the serialiser
    # can build the M partition and know the source_table for AgentState.
    source_path: str = ""
    source_table: str = "data"

    report_logical_id: str = Field(default_factory=new_guid)
    semantic_model_logical_id: str = Field(default_factory=new_guid)