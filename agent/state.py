"""
AgentState — typed Pydantic model representing the full LangGraph state
passed between nodes at every step of the pipeline.
"""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
from agent.models import DataProfile, DomainHypothesis, KPISpec


class AgentState(BaseModel):
    input_path: str = ""
    output_path: str = ""
    data_profile: Optional[DataProfile] = None
    domain_hypothesis: Optional[DomainHypothesis] = None
    kpi_specs: List[KPISpec] = Field(default_factory=list)
    query_results: List[dict] = Field(default_factory=list)
    reflection_notes: List[dict] = Field(default_factory=list)
    pbir_project: Optional[dict] = None
    errors: List[str] = Field(default_factory=list)