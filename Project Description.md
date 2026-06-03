# Project Description — Agentic BI Builder

## Overview

Agentic BI Builder is an agentic AI project that builds a LangGraph-based pipeline capable of taking a raw structured dataset (CSV or SQLite table) and producing a valid Power BI Project (.pbip) folder as output — one that opens directly in Power BI Desktop as a structured report with pages, visuals, and DAX measures.

The agent automates the initial scaffolding phase of dashboard creation: dataset profiling, KPI proposal, SQL generation, output validation with self-reflection, and Power BI report compilation.

---

## Problem

Starting a BI project from a new dataset requires repetitive, time-consuming setup: inspecting the schema, deciding which metrics are meaningful, writing aggregation queries, and mapping results into a dashboard layout. This process is largely mechanical, yet it requires enough domain inference that it cannot be fully replaced by simple rules or templates. The question this project explores is: can a LangGraph-based agentic system automate this entire setup phase — from raw CSV to an openable Power BI report — reliably enough to be useful across different dataset types?

---

## Objectives

1. Accept a CSV or SQLite table as input and run a deterministic profiling step that captures column types, null rates, distinct value counts, and sample values
2. Use an LLM agent with structured output (Pydantic) to infer the dataset's business domain and propose five relevant KPIs, each with a description, SQL query, chart type, and reasoning
3. Load the dataset into a local SQLite instance and execute each generated SQL query, capturing results and errors
4. Implement a reflection node where the LLM reviews the full context (profile + KPI proposals + query results) and flags issues such as aggregating null-heavy columns, incorrect grouping logic, or implausible result values — then triggers targeted regeneration for failed KPIs
5. Build a PBIR compiler in Python — a set of Pydantic models representing the Power BI Project JSON structure — that the agent populates and serialises to a valid `.pbip` folder
6. Demonstrate the full pipeline running successfully on at least three structurally different datasets with different domains

---

## Expected Outcomes

### Deliverable 1 — LangGraph agent scaffold
A runnable LangGraph pipeline with a typed `AgentState` Pydantic model and all nodes wired together. The pipeline accepts a file path and produces an output folder path.

### Deliverable 2 — Profiler node
A deterministic Pandas-based profiling module that produces a structured `DataProfile` object: column names, inferred types, null rates, distinct counts, min/max, and five sample values per column.

### Deliverable 3 — Domain/KPI node
An LLM-powered node that takes the DataProfile as input and returns a `DomainHypothesis` (domain label + confidence) and a list of five `KPISpec` objects, each containing: name, description, SQL query, chart type (card / barChart / lineChart / table), and reasoning.

### Deliverable 4 — SQL executor node
A node that loads the input CSV into an in-memory SQLite instance and runs each KPI's SQL query, producing a `QueryResult` per KPI: output dataframe, row count, column names, and pass/fail status with error message if applicable.

### Deliverable 5 — Reflector node
An LLM-powered node that reviews the full state (profile, KPIs, results) and produces `ReflectionNotes`: a list of flagged KPIs with reasons and specific fix instructions. Failed KPIs re-enter the SQL generator node for one retry cycle.

### Deliverable 6 — PBIR compiler
A Python module with Pydantic models representing the Power BI Project file structure (`Page`, `Visual`, `Measure`, `Table`, `Connection`, `PBIRProject`). The compiler takes validated KPI results, maps them to the appropriate visual types, generates DAX measure expressions, and serialises the full project to a `.pbip` folder on disk.

### Deliverable 7 — Test dataset runs
Documented agent runs on three datasets — Chinook (music retail), Online Retail (e-commerce), and an HR/payroll dataset — with sample profile JSONs, KPI lists, SQL logs, reflection outputs, and screenshots of the opened Power BI report for each.

### Deliverable 8 — Documentation
A GitHub repository with a README, LangGraph architecture diagram, demo GIF showing CSV-to-report end-to-end, and per-dataset output samples.

---

## Technical Constraints and Assumptions

- Input: single-table CSV or SQLite table (no multi-table joins required for MVP; 2-table join as stretch goal)
- SQL dialect: SQLite only — all generated queries must be valid SQLite syntax
- LLM: Anthropic Claude (claude-sonnet-4-20250514) or OpenAI GPT-4o — configurable via environment variable
- Structured outputs: all LLM responses must use Pydantic-validated structured output, not free-form text parsing
- PBIR: the compiler is built by reverse-engineering a manually created `.pbip` export from Power BI Desktop — this is done once as a foundation step before agent development begins
- Power BI: Desktop only — no Power BI Service, no gateway, no embedded publishing in scope for MVP
- DAX: basic measure expressions only (SUM, AVERAGE, COUNT, DIVIDE, IF) — complex DAX patterns are out of scope
- Retry logic: maximum one reflection-triggered retry per KPI before that KPI is dropped from the output

---

## Tech Stack

Python, LangGraph, Pydantic, pandas, SQLite, Anthropic/OpenAI API, Power BI Desktop

---

## Out of Scope

- Multi-table joins or complex relational schema support
- Full autonomous PBIX generation from scratch (PBIR/PBIP folder approach is used instead)
- Complex DAX (time intelligence, CALCULATE with multiple filters, etc.)
- Universal compatibility with any dataset type — the agent is optimised for structured tabular data with identifiable business domains
- Power BI Service publishing, scheduled refresh, or embedded deployment
- A user interface (CLI only for MVP; Streamlit is a stretch goal for debugging only)
