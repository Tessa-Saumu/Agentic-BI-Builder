"""
LangGraph pipeline: profiler -> domain_kpi -> sql_executor -> reflector ->
[sql_executor_retry if flagged, else skip] -> resolve_source_path ->
pbir_compiler.

Retry is graph-level, not inside reflector.py — reflector only sets
state.kpis_to_retry. sql_executor_retry has one outgoing edge (no path
back to reflector), which is what makes "one retry only" hold.
"""
import os
import time
from pathlib import Path
from typing import Callable

from langgraph.graph import StateGraph
from agent.state import AgentState
from agent.profiler import run_profiler
from agent.domain_kpi import run_domain_kpi
from agent.sql_executor import run_sql_executor, run_sql_executor_retry
from agent.reflector import run_reflector
from pbir.compiler.builder import run_pbir_compiler


def resolve_absolute_source_path(state: AgentState) -> AgentState:
    """
    Converts state.data_profile.source_path to an absolute path.

    profiler.py stores source_path relative to the project root, but
    serialiser.py writes it directly into Power Query's File.Contents(...),
    which needs an absolute path — a relative one produces "supplied file
    path must be a valid absolute path" in Power BI Desktop.
    """
    if state.data_profile is None:
        return state

    raw_path = state.data_profile.source_path
    if os.path.isabs(raw_path):
        return state

    abs_path = os.path.abspath(os.path.join(Path.cwd(), raw_path))
    state.data_profile = state.data_profile.model_copy(update={"source_path": abs_path})
    return state


def time_node(node_name: str, node_fn: Callable[[AgentState], AgentState]) -> Callable[[AgentState], AgentState]:
    """Wraps a node so its execution time lands in state.node_timings[node_name]."""

    def _wrapped(state: AgentState) -> AgentState:
        start = time.monotonic()
        result_state = node_fn(state)
        elapsed = time.monotonic() - start
        result_state.node_timings[node_name] = round(elapsed, 3)
        return result_state

    _wrapped.__name__ = f"timed_{node_name}"
    return _wrapped


def _route_after_reflection(state: AgentState) -> str:
    """Routes to sql_executor_retry if reflector flagged fixes, else straight to resolve_source_path."""
    return "sql_executor_retry" if state.kpis_to_retry else "pbir_compiler"


def build_graph(dataset_name: str = "dataset") -> StateGraph:
    """
    Build and compile the pipeline graph.

    dataset_name is bound at construction time because LangGraph nodes
    take only (state) — no per-invocation kwargs — so reflector's
    dataset_name has to come from here, not a default.
    """
    graph = StateGraph(AgentState)

    def _reflector_for_dataset(state: AgentState) -> AgentState:
        return run_reflector(state, dataset_name=dataset_name)

    graph.add_node("profiler", time_node("profiler", run_profiler))
    graph.add_node("domain_kpi", time_node("domain_kpi", run_domain_kpi))
    graph.add_node("sql_executor", time_node("sql_executor", run_sql_executor))
    graph.add_node("reflector", time_node("reflector", _reflector_for_dataset))
    graph.add_node("sql_executor_retry", time_node("sql_executor_retry", run_sql_executor_retry))
    graph.add_node("resolve_source_path", time_node("resolve_source_path", resolve_absolute_source_path))
    graph.add_node("pbir_compiler", time_node("pbir_compiler", run_pbir_compiler))

    graph.set_entry_point("profiler")
    graph.add_edge("profiler", "domain_kpi")
    graph.add_edge("domain_kpi", "sql_executor")
    graph.add_edge("sql_executor", "reflector")

    # Both branches converge on resolve_source_path before pbir_compiler,
    # and neither loops back to reflector or sql_executor_retry.
    graph.add_conditional_edges(
        "reflector",
        _route_after_reflection,
        {
            "sql_executor_retry": "sql_executor_retry",
            "pbir_compiler": "resolve_source_path",
        },
    )
    graph.add_edge("sql_executor_retry", "resolve_source_path")
    graph.add_edge("resolve_source_path", "pbir_compiler")

    graph.set_finish_point("pbir_compiler")

    return graph.compile()