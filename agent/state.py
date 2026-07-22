"""
AgentState — typed Pydantic model representing the full LangGraph state
passed between nodes at every step of the pipeline.
"""
from __future__ import annotations
from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from agent.models import DataProfile, DomainHypothesis, KPISpec, QueryResult, ReflectionNote
from pbir.models.project import PBIRProject


class AgentState(BaseModel):
    input_path: str = ""
    output_path: str = ""
    data_profile: Optional[DataProfile] = None
    domain_hypothesis: Optional[DomainHypothesis] = None
    kpi_specs: List[KPISpec] = Field(default_factory=list)
    query_results: List[QueryResult] = Field(default_factory=list)
    reflection_notes: List[ReflectionNote] = Field(default_factory=list)
    kpis_to_retry: List[str] = Field(
        default_factory=list,
        description="KPISpec.name values that reflector.py flagged with a "
                    "usable fixed_sql_query, already applied to the matching "
                    "KPISpec.sql_query in kpi_specs. Read by graph.py's "
                    "conditional edge to decide whether to route to "
                    "sql_executor.run_sql_executor_retry (non-empty) or "
                    "straight to pbir_compiler (empty). Set only by "
                    "run_reflector; cleared by run_sql_executor_retry once "
                    "it has processed every name in the list, so the field "
                    "never carries stale state past the retry step.",
    )
    pbir_project: Optional[PBIRProject] = None
    errors: List[str] = Field(default_factory=list)
    node_timings: Dict[str, float] = Field(
        default_factory=dict,
        description="Wall-clock seconds per node, keyed by node name (e.g. "
                    "'profiler', 'domain_kpi'). Populated exclusively by "
                    "graph.py's time_node() wrapper at execution time — no "
                    "node sets this itself. Read by run_agent.py to print "
                    "per-node and total timing once the graph finishes.",
    )