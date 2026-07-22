"""
run_agent.py — CLI entry point for the Agentic BI Builder pipeline.

Usage:
    python run_agent.py --input data/raw/chinook.csv --output output/chinook_report
"""
import argparse
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; fall back to whatever's already in the environment

from agent.state import AgentState
from agent.graph import build_graph
from agent.domain_kpi import save_kpi_output
from pbir.compiler.serialiser import write_pbip


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

    # profile_datasets.py and run_domain_kpi_all.py write these when run as
    # standalone scripts; run_agent.py runs the same nodes but never called
    # either write, so data/profiles/ stayed empty. Same writes, same
    # target directory, called here instead.
    profiles_dir = "data/profiles"
    os.makedirs(profiles_dir, exist_ok=True)

    if final_state.data_profile is not None:
        profile_path = os.path.join(profiles_dir, f"{dataset_name}_profile.json")
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(final_state.data_profile.model_dump(), f, indent=2, default=str)
        print(f"Profile written to: {profile_path}")

    if final_state.domain_hypothesis is not None and final_state.kpi_specs:
        kpi_path = save_kpi_output(final_state, dataset_name, output_dir=profiles_dir)
        print(f"KPIs written to: {kpi_path}")

    # write_pbip is called here, not inside agent/graph.py's "pbir_compiler"
    # node, because run_pbir_compiler() only ever builds the in-memory
    # PBIRProject — by builder.py's own module docstring, and by the Phase 3
    # issue's own task list, serialising to disk is a deliberately separate
    # function with its own signature (write_pbip(project, output_dir)).
    # scripts/run_pbir_compiler_all.py already reflects that split by
    # calling both steps separately in its own script body; this mirrors
    # that same shape for run_agent.py's CLI entry point, keeping
    # agent/graph.py limited to node wiring with no I/O of its own.
    report_written = False
    if final_state.pbir_project is not None:
        print(f"\n[PBIR Compiler] Writing .pbip folder to '{final_state.output_path}'...")
        try:
            write_pbip(final_state.pbir_project, final_state.output_path)
            report_written = True
        except Exception as exc:
            final_state.errors.append(f"run_agent: write_pbip failed: {exc}")

    if report_written:
        n_pages = len(final_state.pbir_project.pages)
        n_visuals = sum(len(p.visuals) for p in final_state.pbir_project.pages)
        print(
            f"✅ Report written to: {final_state.output_path} "
            f"({n_pages} page(s), {n_visuals} visual(s))"
        )
    else:
        print(f"\n❌ No report was written to {final_state.output_path} "
              f"— see errors below for why.")

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