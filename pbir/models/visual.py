"""
Visual — Pydantic model for a single Power BI visual definition.
chart_type: card | barChart | lineChart | table
"""
from pydantic import BaseModel
from typing import Literal, Optional


class Visual(BaseModel):
    visual_id: str
    chart_type: Literal["card", "barChart", "lineChart", "table"]
    title: str
    measure_ref: str
    x: int = 0
    y: int = 0
    width: int = 300
    height: int = 200
