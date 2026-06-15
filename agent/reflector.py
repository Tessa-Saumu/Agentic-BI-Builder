"""
Reflector node — LLM reviews full state (profile + KPIs + results)
and produces ReflectionNotes flagging issues:
  - null-heavy column aggregations
  - wrong grouping logic
  - implausible result values
Failed KPIs re-enter the SQL executor for one retry cycle.
"""
from agent.state import AgentState


def run_reflector(state: AgentState) -> AgentState:
    # TODO: call LLM with full context, parse flagged KPIs, trigger retries
    raise NotImplementedError
