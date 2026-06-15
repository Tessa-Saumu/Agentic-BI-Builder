"""
PBIRProject — top-level model for the full .pbip folder.
Serialises to the Power BI Project JSON file structure.
"""
from pydantic import BaseModel
from typing import List
from pbir.models.page import Page
from pbir.models.measure import Measure


class PBIRProject(BaseModel):
    report_name: str
    pages: List[Page] = []
    measures: List[Measure] = []
    source_table: str = "data"
    source_path: str = ""
