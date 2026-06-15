"""
Profiler node — deterministic Pandas-based schema analysis.
Produces a DataProfile with column types, null rates,
distinct counts, min/max values, and sample values.
"""
import pandas as pd
from pathlib import Path
from agent.state import AgentState


def run_profiler(state: AgentState) -> AgentState:
    # TODO: load CSV, compute per-column stats, return DataProfile dict
    raise NotImplementedError
