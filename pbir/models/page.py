"""
Page — one report page containing a list of visuals.
"""
from pydantic import BaseModel
from typing import List
from pbir.models.visual import Visual


class Page(BaseModel):
    page_id: str
    display_name: str
    visuals: List[Visual] = []
