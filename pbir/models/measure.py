"""
Measure — Pydantic model for a DAX measure expression.
Supports basic DAX only: SUM, AVERAGE, COUNT, DIVIDE, IF.
"""
from pydantic import BaseModel


class Measure(BaseModel):
    name: str
    expression: str   # e.g. "SUM('sales'[revenue])"
    format_string: Optional[str] = None

    class Config:
        from __future__ = True
