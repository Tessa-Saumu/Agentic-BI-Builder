"""
PBIR Compiler node — takes validated KPI results from AgentState,
maps them to PBIRProject Pydantic models,
and serialises the full .pbip folder structure to disk.
"""
from agent.state import AgentState


def run_pbir_compiler(state: AgentState) -> AgentState:
    # TODO: map kpi query_results to Page/Visual/Measure models
    # TODO: serialise PBIRProject to output_path/.pbip folder
    raise NotImplementedError
