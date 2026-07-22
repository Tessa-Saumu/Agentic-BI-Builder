"""
Visual — Pydantic model for a single Power BI visual definition.

chart_type here matches the KPISpec/agent schema's chart_type field
("card" | "barChart" | "lineChart" | "table"); visual_type is the PBIR
visualType string it maps to (pbir_reference.md §2.8):

    card      -> cardVisual
    barChart  -> clusteredColumnChart
    lineChart -> lineChart
    table     -> tableEx   (NOT "table" -- legacy internal naming, §2.8)

Only these 4 chart_type values / 5 visualType strings (pivotTable is
available but unused by this compiler, since KPISpec never emits it) are
supported. Any other value is a hard error at build time rather than a
silent guess, per the reference doc's caution against unconfirmed
visualType strings.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from pbir.models.common import new_guid

ChartType = Literal["card", "barChart", "lineChart", "table"]
VisualType = Literal["cardVisual", "clusteredColumnChart", "lineChart", "tableEx", "pivotTable"]

CHART_TYPE_TO_VISUAL_TYPE: dict[str, VisualType] = {
    "card": "cardVisual",
    "barChart": "clusteredColumnChart",
    "lineChart": "lineChart",
    "table": "tableEx",
}


class Position(BaseModel):
    x: float = 0
    y: float = 0
    z: float = 0
    height: float = 200
    width: float = 300
    tab_order: int = 0


class Visual(BaseModel):
    visual_id: str  # deterministic slug, also the folder name (§3)
    chart_type: ChartType
    title: str
    measure_ref: str  # the KPI's measure name (Measure.name)
    category_ref: Optional[str] = None  # column name for barChart/lineChart/table grouping
    entity: str = "data"  # source table name in the semantic model

    position: Position = Field(default_factory=Position)
    lineage_tag: str = Field(default_factory=new_guid)

    @property
    def visual_type(self) -> VisualType:
        return CHART_TYPE_TO_VISUAL_TYPE[self.chart_type]