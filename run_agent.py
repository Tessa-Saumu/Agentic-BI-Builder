"""
run_agent.py — CLI entry point for the Agentic BI Builder pipeline.

Usage:
    python run_agent.py --input data/raw/chinook.csv --output output/chinook_report
"""
import argparse
import os
from pathlib import Path

from agent.state import AgentState
from agent.graph import build_graph


def _dataset_name_from_input(input_path: str) -> str:
    """
    Derive a dataset name from --input for two things: (1) the reflection
    log filename (data/profiles/<dataset_name>_reflection.json, written by
    agent/reflector.py's run_reflector), and (2) this script's own timing
    and summary headers below. E.g. "data/raw/hr_analytics.csv" -> "hr_analytics".
    """
    return Path(input_path).stem


def main():
    parser = argparse.ArgumentParser(description="Agentic BI Builder")
    parser.add_argument("--input", required=True, help="Path to input CSV or SQLite file")
    parser.add_argument("--output", required=True, help="Path to output .pbip folder")
    args = parser.parse_args()

    dataset_name = _dataset_name_from_input(args.input)

    # dataset_name is bound into the graph at construction time (see
    # agent/graph.py's build_graph docstring) because LangGraph invokes
    # every node as node_fn(state) only -- there is no per-invocation kwarg
    # path from graph.invoke() down into an individual node. Without this,
    # run_reflector would silently fall back to its own dataset_name="dataset"
    # default and every dataset's reflection log would overwrite the last.
    graph = build_graph(dataset_name=dataset_name)
    initial_state = AgentState(input_path=args.input, output_path=args.output)

    print(f"=== Running pipeline for '{dataset_name}' ===")
    print(f"  Input:  {args.input}")
    print(f"  Output: {args.output}\n")

    try:
        raw_result = graph.invoke(initial_state)
    except NotImplementedError as e:
        print(f"\n[Phase 1 Scaffold] Pipeline node not yet implemented: {e}")
        print("This is expected — nodes raise NotImplementedError until Phase 2.")
        raise

    # A compiled LangGraph StateGraph's .invoke() always returns a plain
    # dict of the final state's fields, never the Pydantic model instance
    # that was passed in -- true regardless of which BaseModel subclass was
    # used to build the graph. Rehydrating it here is what makes
    # final_state.node_timings / .errors / .reflection_notes usable as
    # normal attributes below, instead of dict lookups scattered through
    # this function.
    final_state = AgentState(**raw_result)

    print(f"\n✅ Report written to: {final_state.output_path}")

    if final_state.node_timings:
        print("\n--- Timing ---")
        total_seconds = 0.0
        # Print in pipeline order (insertion order == execution order,
        # since every node writes to node_timings exactly once, in the
        # sequence graph.py wires them) rather than sorting alphabetically,
        # so the printout reads top-to-bottom the same way the pipeline ran.
        for node_name, seconds in final_state.node_timings.items():
            print(f"  {node_name:<15} {seconds:>8.2f}s")
            total_seconds += seconds
        print(f"  {'TOTAL':<15} {total_seconds:>8.2f}s")

    if final_state.reflection_notes:
        n_fixed = sum(1 for n in final_state.reflection_notes if n.fixed_sql_query is not None)
        n_dropped = len(final_state.reflection_notes) - n_fixed
        print(f"\n--- Reflection ---")
        print(f"  {len(final_state.reflection_notes)} issue(s) flagged: "
              f"{n_fixed} fixed on retry, {n_dropped} dropped (no fix available).")
        print(f"  {len(final_state.kpi_specs)} KPI(s) remaining in final report.")
    else:
        print(f"\n--- Reflection ---")
        print(f"  No issues found. All {len(final_state.kpi_specs)} KPI(s) passed review as-is.")

    if final_state.errors:
        print(f"\n⚠️  Errors encountered: {final_state.errors}")


if __name__ == "__main__":
    main()