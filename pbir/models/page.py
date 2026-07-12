"""
Page — one report page containing a list of visuals.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel

from pbir.models.visual import Visual


class Page(BaseModel):
    page_id: str  # deterministic slug, also the folder name (§3)
    display_name: str
    visuals: List[Visual] = []