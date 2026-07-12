"""
Column — Pydantic model for a single TMDL `column` block (pbir_reference.md §2.12).

Represents one source column in the semantic model's table. Every field here
maps directly to a line in the generated <table>.tmdl file.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from pbir.models.common import new_guid

DaxType = Literal["dateTime", "string", "int64", "decimal"]
SummarizeBy = Literal["none", "sum", "average", "count"]


class Column(BaseModel):
    name: str
    data_type: DaxType
    source_column: str  # must match the column name after M partition transforms
    summarize_by: SummarizeBy = "none"
    format_string: Optional[str] = None
    lineage_tag: str = Field(default_factory=new_guid)