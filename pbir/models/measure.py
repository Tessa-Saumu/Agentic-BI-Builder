"""
Measure — Pydantic model for a DAX measure expression.
Supports basic DAX only: SUM, AVERAGE, COUNT, DIVIDE, IF.

One Measure maps to one `measure` block in a TMDL <table>.tmdl file
(pbir_reference.md §2.12), and its `name` is what appears in Power BI's
field list under the semantic model table.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from pbir.models.common import new_guid


class Measure(BaseModel):
    name: str
    expression: str  # e.g. "SUM('data'[Total])"
    format_string: Optional[str] = None
    lineage_tag: str = Field(default_factory=new_guid)
    is_currency: bool = False  # if True, attach the PBI_FormatHint annotation
