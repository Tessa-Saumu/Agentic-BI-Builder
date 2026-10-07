#!/bin/bash
# ─────────────────────────────────────────────────────────────
# HISTORICAL SCAFFOLD SCRIPT — DO NOT RUN.
#
# This script was used only during Phase 1 (June 2026) to create
# the initial directory structure. Running it will overwrite
# `agent/state.py` and other implemented modules with stubs.
# Preserved here for reference only.
# ─────────────────────────────────────────────────────────────
echo "ERROR: HISTORICAL SCAFFOLD SCRIPT — DO NOT RUN." >&2
exit 1
set -e
echo "🤖 Scaffolding Agentic BI Builder project structure..."

# ── 1. Create top-level directories ──────────────────────────
mkdir -p agent
mkdir -p data/raw
mkdir -p data/processed
mkdir -p data/profiles
mkdir -p notebooks
mkdir -p output/chinook_report
mkdir -p output/online_retail_report
mkdir -p output/hr_report
mkdir -p pbir/models
mkdir -p pbir/compiler
mkdir -p tests
mkdir -p docs
mkdir -p assets

# ── 2. Remove any stray getkeep files ────────────────────────
find . -name "getkeep" -delete

# ── 3. Create agent node stubs ───────────────────────────────
cat > agent/__init__.py << 'PY'
# Agentic BI Builder — LangGraph agent package
PY

cat > agent/state.py << 'PY'
"""
AgentState — typed Pydantic model representing the full LangGraph state
passed between nodes at every step of the pipeline.
"""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class AgentState(BaseModel):
    input_path: str = ""
    output_path: str = ""
    data_profile: Optional[dict] = None
    domain_hypothesis: Optional[dict] = None
    kpi_specs: List[dict] = []
    query_results: List[dict] = []
    reflection_notes: List[dict] = []
    pbir_project: Optional[dict] = None
    errors: List[str] = []
PY

cat > agent/profiler.py << 'PY'
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
PY

cat > agent/domain_kpi.py << 'PY'
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
PY

cat > agent/sql_executor.py << 'PY'
"""
SQL Executor node — loads CSV into in-memory SQLite,
runs each KPI SQL query, records QueryResult per KPI
(dataframe, row count, columns, pass/fail + error message).
"""
from agent.state import AgentState


def run_sql_executor(state: AgentState) -> AgentState:
    # TODO: sqlite3 in-memory DB, execute KPI queries, capture results
    raise NotImplementedError
PY

cat > agent/reflector.py << 'PY'
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
PY

cat > agent/graph.py << 'PY'
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
PY

# ── 4. Create PBIR package stubs ─────────────────────────────
cat > pbir/__init__.py << 'PY'
# PBIR — Power BI Project (.pbip) compiler package
PY

cat > pbir/models/__init__.py << 'PY'
# Pydantic models representing the PBIR JSON structure
PY

cat > pbir/models/visual.py << 'PY'
"""
Visual — Pydantic model for a single Power BI visual definition.
chart_type: card | barChart | lineChart | table
"""
from pydantic import BaseModel
from typing import Literal, Optional


class Visual(BaseModel):
    visual_id: str
    chart_type: Literal["card", "barChart", "lineChart", "table"]
    title: str
    measure_ref: str
    x: int = 0
    y: int = 0
    width: int = 300
    height: int = 200
PY

cat > pbir/models/measure.py << 'PY'
"""
Measure — Pydantic model for a DAX measure expression.
Supports basic DAX only: SUM, AVERAGE, COUNT, DIVIDE, IF.
"""
from pydantic import BaseModel


class Measure(BaseModel):
    name: str
    expression: str   # e.g. "SUM('sales'[revenue])"
    format_string: Optional[str] = None

    class Config:
        from __future__ = True
PY

cat > pbir/models/page.py << 'PY'
"""
Page — one report page containing a list of visuals.
"""
from pydantic import BaseModel
from typing import List
from pbir.models.visual import Visual


class Page(BaseModel):
    page_id: str
    display_name: str
    visuals: List[Visual] = []
PY

cat > pbir/models/project.py << 'PY'
"""
PBIRProject — top-level model for the full .pbip folder.
Serialises to the Power BI Project JSON file structure.
"""
from pydantic import BaseModel
from typing import List
from pbir.models.page import Page
from pbir.models.measure import Measure


class PBIRProject(BaseModel):
    report_name: str
    pages: List[Page] = []
    measures: List[Measure] = []
    source_table: str = "data"
    source_path: str = ""
PY

cat > pbir/compiler/__init__.py << 'PY'
# PBIR compiler — maps validated KPI results to Pydantic models
# and writes the .pbip folder to disk
PY

cat > pbir/compiler/builder.py << 'PY'
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
PY

cat > pbir/compiler/serialiser.py << 'PY'
"""
Serialiser — writes PBIRProject model to the correct .pbip folder layout:
  report.pbip/
    definition/
      pages/        one JSON per page
      visuals/      visual definitions
      expressions/  DAX measures
      model.json    data model + table schema
      connections.json  data source connection
"""
import json
from pathlib import Path
from pbir.models.project import PBIRProject


def write_pbip(project: PBIRProject, output_dir: Path) -> None:
    # TODO: create folder tree and write JSON files
    raise NotImplementedError
PY

# ── 5. Create run_agent.py entry point ───────────────────────
cat > run_agent.py << 'PY'
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
PY

# ── 6. Create notebook stubs ──────────────────────────────────
touch notebooks/01_dataset_profiling_exploration.ipynb
touch notebooks/02_kpi_proposal_review.ipynb
touch notebooks/03_sql_validation_and_reflection.ipynb
touch notebooks/04_pbir_output_inspection.ipynb

# ── 7. Create test stubs ──────────────────────────────────────
cat > tests/__init__.py << 'PY'
PY

touch tests/test_profiler.py
touch tests/test_sql_executor.py
touch tests/test_reflector.py
touch tests/test_pbir_compiler.py

# ── 8. Create .env.example ────────────────────────────────────
cat > .env.example << 'ENV'
# Copy this file to .env and fill in your API key
# LLM provider: "anthropic" or "openai"
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_key_here
OPENAI_API_KEY=your_openai_key_here
ENV

# ── 9. Create requirements.txt ────────────────────────────────
cat > requirements.txt << 'REQS'
# Agent orchestration
langgraph
langchain-core
langchain-anthropic
langchain-openai

# LLM providers
anthropic
openai

# Data
pandas
numpy
openpyxl

# SQL
# sqlite3 is part of Python stdlib — no install needed

# Structured outputs
pydantic>=2.0

# Notebooks
jupyter
ipykernel

# Utilities
python-dotenv
rich
REQS

# ── 10. Create .gitignore ─────────────────────────────────────
cat > .gitignore << 'IGNORE'
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
*.egg-info/
dist/
build/
.venv/
venv/
env/

# Environment
.env

# Jupyter
.ipynb_checkpoints/
*.ipynb_checkpoints

# OS
.DS_Store
Thumbs.db

# Output reports (large binary-ish folders — exclude from git)
output/*/
!output/.gitkeep

# Data (comment out if you want to push sample CSVs)
# data/raw/*.csv
# data/raw/*.sqlite
IGNORE

# ── 11. Add .gitkeep to empty leaf dirs ──────────────────────
find . -type d \
  ! -path "./.git/*" \
  ! -name ".git" \
  -exec sh -c '
    if [ -z "$(ls -A "$1")" ]; then
      touch "$1/.gitkeep"
      echo "  + .gitkeep → $1"
    fi
  ' _ {} \;

echo ""
echo "✅ Done! Agentic BI Builder structure created:"
echo ""
tree -a --dirsfirst -I '.git' 2>/dev/null || find . ! -path './.git/*' | sort