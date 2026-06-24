"""
AgentState — typed Pydantic model representing the full LangGraph state
passed between nodes at every step of the pipeline.
"""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel
from agent.models import DataProfile


class AgentState(BaseModel):
    input_path: str = ""
    output_path: str = ""
    data_profile: Optional[DataProfile] = None
    domain_hypothesis: Optional[dict] = None
    kpi_specs: List[dict] = []
    query_results: List[dict] = []
    reflection_notes: List[dict] = []
    pbir_project: Optional[dict] = None
    errors: List[str] = []
