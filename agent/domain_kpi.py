"""
Domain/KPI node — LLM-powered (Claude or GPT-4o).
Takes DataProfile and returns:
  - DomainHypothesis (domain label + confidence)
  - List[KPISpec] (name, description, SQL, chart_type, reasoning)
Uses Pydantic structured output — no free-form text parsing.
"""
from agent.state import AgentState


def run_domain_kpi(state: AgentState) -> AgentState:
    # TODO: call LLM with structured output, populate kpi_specs
    raise NotImplementedError
