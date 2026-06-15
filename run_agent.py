"""
run_agent.py — CLI entry point for the Agentic BI Builder pipeline.

Usage:
    python run_agent.py --input data/raw/chinook.csv --output output/chinook_report
"""
import argparse
from agent.state import AgentState
from agent.graph import build_graph


def main():
    parser = argparse.ArgumentParser(description="Agentic BI Builder")
    parser.add_argument("--input", required=True, help="Path to input CSV or SQLite file")
    parser.add_argument("--output", required=True, help="Path to output .pbip folder")
    args = parser.parse_args()

    graph = build_graph()
    initial_state = AgentState(input_path=args.input, output_path=args.output)
    final_state = graph.invoke(initial_state)

    print(f"\n✅ Report written to: {final_state.output_path}")
    if final_state.errors:
        print(f"⚠️  Errors encountered: {final_state.errors}")


if __name__ == "__main__":
    main()
