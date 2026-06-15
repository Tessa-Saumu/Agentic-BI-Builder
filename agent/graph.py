"""
LangGraph pipeline definition.
Wires all nodes into the graph and defines conditional edges
for the reflection retry loop.
"""
from langgraph.graph import StateGraph
from agent.state import AgentState
from agent.profiler import run_profiler
from agent.domain_kpi import run_domain_kpi
from agent.sql_executor import run_sql_executor
from agent.reflector import run_reflector
from pbir.compiler.builder import run_pbir_compiler


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("profiler", run_profiler)
    graph.add_node("domain_kpi", run_domain_kpi)
    graph.add_node("sql_executor", run_sql_executor)
    graph.add_node("reflector", run_reflector)
    graph.add_node("pbir_compiler", run_pbir_compiler)

    graph.set_entry_point("profiler")
    graph.add_edge("profiler", "domain_kpi")
    graph.add_edge("domain_kpi", "sql_executor")
    graph.add_edge("sql_executor", "reflector")
    # TODO: add conditional edge — retry loop back to sql_executor or proceed
    graph.add_edge("reflector", "pbir_compiler")
    graph.set_finish_point("pbir_compiler")

    return graph.compile()
