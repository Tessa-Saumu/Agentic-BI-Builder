"""
LangGraph pipeline definition.
Wires all nodes into the graph, including the conditional retry edge after
"reflector": profiler -> domain_kpi -> sql_executor -> reflector ->
[sql_executor_retry, if reflector flagged and fixed at least one KPI] OR
[straight to pbir_compiler, if not] -> pbir_compiler.

The retry endpoint (sql_executor_retry) never routes back to "reflector" —
it has exactly one outgoing edge, straight to "pbir_compiler". This is what
enforces "one retry only": there is no graph edge that could route a KPI
through a second reflection or a second retry, so the guarantee comes from
the graph's topology, not from a counter anywhere in state.

reflector.py has no import of and makes no call to anything in
sql_executor.py — it only writes state.kpis_to_retry, a plain list of KPI
names. This graph is the only place that decides what "retry" means (which
node runs, and how many times) — reflector.py's job is limited to deciding
*whether* a KPI needs retrying and what its corrected SQL should be.

Each node's wall-clock time is recorded into state.node_timings via
time_node() below, so run_agent.py can report per-node and total timing
without any node needing to know about timing itself.
"""
import time
from typing import Callable

from langgraph.graph import StateGraph
from agent.state import AgentState
from agent.profiler import run_profiler
from agent.domain_kpi import run_domain_kpi
from agent.sql_executor import run_sql_executor, run_sql_executor_retry
from agent.reflector import run_reflector
from pbir.compiler.builder import run_pbir_compiler


def time_node(node_name: str, node_fn: Callable[[AgentState], AgentState]) -> Callable[[AgentState], AgentState]:
    """
    Wrap a LangGraph node function so its wall-clock execution time is
    recorded into state.node_timings[node_name], in seconds.

    This is a wrapper around each node at graph-construction time, not a
    change to any node itself -- profiler.py, domain_kpi.py, sql_executor.py,
    reflector.py, and builder.py stay exactly as they are, with zero
    awareness that timing exists. That separation is the point: timing is
    cross-cutting infrastructure, not pipeline logic, so it shouldn't leak
    into files whose job is profiling data or calling an LLM. It also means
    every node is timed the same consistent way with one implementation,
    rather than five node files each adding their own start/stop calls that
    could drift out of sync with each other.
    """

    def _wrapped(state: AgentState) -> AgentState:
        start = time.monotonic()
        result_state = node_fn(state)
        elapsed = time.monotonic() - start
        result_state.node_timings[node_name] = round(elapsed, 3)
        return result_state

    _wrapped.__name__ = f"timed_{node_name}"
    return _wrapped


def _route_after_reflection(state: AgentState) -> str:
    """
    Conditional-edge routing function for the edge out of "reflector".

    Reads only state.kpis_to_retry — set exclusively by run_reflector,
    listing KPI names whose SQL was fixed and needs re-execution before the
    report is built. Empty means either no issues were found, or every
    flagged issue had no available fix (those KPIs are already dropped by
    run_reflector itself, so there's nothing left to retry).

    Returns a node name, which graph.add_conditional_edges below maps to
    the actual next node via its path map.
    """
    return "sql_executor_retry" if state.kpis_to_retry else "pbir_compiler"


def build_graph(dataset_name: str = "dataset") -> StateGraph:
    """
    Build and compile the pipeline graph.

    dataset_name is threaded in here (rather than left to run_reflector's
    own default) because LangGraph calls every node as node_fn(state) only —
    there's no mechanism to pass extra per-invocation kwargs like
    dataset_name through graph.add_node / graph.invoke. Without this, every
    dataset's run would silently fall back to run_reflector's
    dataset_name="dataset" default, and every run's reflection log would
    write to the same data/profiles/dataset_reflection.json, overwriting
    the previous dataset's log instead of producing
    data/profiles/chinook_reflection.json,
    data/profiles/online_retail_reflection.json,
    data/profiles/hr_analytics_reflection.json separately. Binding
    dataset_name into a closure at graph-construction time is what makes
    run_reflector's per-dataset behavior actually reachable through the
    graph, since run_agent.py invokes the graph once per dataset anyway.
    """
    graph = StateGraph(AgentState)

    def _reflector_for_dataset(state: AgentState) -> AgentState:
        return run_reflector(state, dataset_name=dataset_name)

    graph.add_node("profiler", time_node("profiler", run_profiler))
    graph.add_node("domain_kpi", time_node("domain_kpi", run_domain_kpi))
    graph.add_node("sql_executor", time_node("sql_executor", run_sql_executor))
    graph.add_node("reflector", time_node("reflector", _reflector_for_dataset))
    graph.add_node("sql_executor_retry", time_node("sql_executor_retry", run_sql_executor_retry))
    graph.add_node("pbir_compiler", time_node("pbir_compiler", run_pbir_compiler))

    graph.set_entry_point("profiler")
    graph.add_edge("profiler", "domain_kpi")
    graph.add_edge("domain_kpi", "sql_executor")
    graph.add_edge("sql_executor", "reflector")

    # The conditional edge this module's docstring describes. Note there is
    # no path map entry routing anywhere back to "reflector" or to
    # "sql_executor_retry" a second time — that omission is what makes "one
    # retry only" a property of the graph's shape, not of a counter.
    graph.add_conditional_edges(
        "reflector",
        _route_after_reflection,
        {
            "sql_executor_retry": "sql_executor_retry",
            "pbir_compiler": "pbir_compiler",
        },
    )
    graph.add_edge("sql_executor_retry", "pbir_compiler")

    graph.set_finish_point("pbir_compiler")

    return graph.compile()