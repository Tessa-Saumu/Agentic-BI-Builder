# Agentic BI Builder

> A LangGraph-powered analytics agent that profiles a structured dataset, proposes relevant KPIs, generates and validates SQL queries, reflects on its own outputs, and compiles a real Power BI Project (.pbip) folder — ready to open directly in Power BI Desktop.

---

## Problem Statement

Starting a BI project from a new dataset involves hours of repetitive scaffolding work: inspecting the schema, deciding which metrics matter, writing aggregation queries, and manually mapping results into a dashboard layout. This process is largely mechanical — yet it still requires enough domain inference that it can't be fully automated with simple rules. This project explores whether a LangGraph-based agentic system can automate that entire setup phase, taking a raw CSV as input and producing a working Power BI report as output.

---

## Objectives

1. Accept a CSV or SQLite table as input and automatically profile its schema, null rates, cardinality, and value distributions
2. Use an LLM agent to infer the dataset's business domain and propose relevant KPIs with reasoning
3. Generate executable SQL queries for each KPI and run them against a local SQLite instance
4. Implement a reflection pass where the LLM reviews its own outputs, identifies mismatches, and triggers targeted regeneration
5. Compile the validated query results into a real Power BI Project (.pbip) folder by emitting the PBIR JSON structure programmatically
6. Demonstrate generalisation across at least three structurally different datasets

---

## Expected Outcomes

- A working LangGraph agent with six documented nodes
- Automated dataset profiling output (JSON) for any CSV input
- LLM-generated KPI list with domain classification, SQL, chart type, and reasoning — per dataset
- SQL execution logs with pass/fail status and retry records
- Reflection notes showing the agent catching and correcting its own errors
- A valid `.pbip` folder output that opens in Power BI Desktop as a structured report with pages, visuals, and DAX measures
- Demonstrated runs on three datasets (Chinook music store, retail sales, HR/payroll)
- GitHub repository with architecture diagram, demo GIF, README, and sample outputs per dataset

---

## Architecture

```
CSV input
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    LANGGRAPH AGENT                      │
│                                                         │
│  Profiler ──▶ Domain/KPI Node ──▶ SQL Executor          │
│  (Pandas)      (LLM + Pydantic)    (SQLite)             │
│                                         │               │
│                                         ▼               │
│  PBIR Compiler ◀── Reflector ◀── Validation check       │
│  (Python)          (LLM)                                │
└─────────────────────────────────────────────────────────┘
    │
    ▼
.pbip folder → open in Power BI Desktop
```

---

## Agent Nodes

| Node | Type | What it does |
|---|---|---|
| Profiler | Deterministic | Pandas-based schema analysis — column types, null rates, distinct counts, sample values |
| Domain/KPI | LLM | Infers business domain (retail, HR, finance, etc.) and proposes 5 KPIs with SQL, chart type, and reasoning |
| SQL Executor | Deterministic | Loads CSV into SQLite, runs each KPI query, captures results and errors |
| Reflector | LLM | Reviews profile + KPI list + results, flags mismatches (wrong aggregations, null-heavy columns, implausible values), requests targeted fixes |
| PBIR Compiler | Deterministic | Maps validated query results to Pydantic PBIR models and writes the `.pbip` folder structure |

---

## PBIR Output Structure

The agent emits a valid Power BI Project folder that Power BI Desktop opens natively:

```
output/report.pbip
├── definition/
│   ├── pages/          # one JSON per report page
│   ├── visuals/        # visual definitions (card, bar, line, table)
│   ├── expressions/    # DAX measure definitions
│   ├── model.json      # data model and table schema
│   └── connections.json # data source connection
```

This structure is reverse-engineered from a real `.pbip` export and modelled as Pydantic classes, so the agent populates typed Python objects — not raw JSON strings.

---

## Tech Stack

| Layer | Tools |
|---|---|
| Agent orchestration | LangGraph |
| LLM | Google Gemini (gemini-3.1-flash / gemini-3.1 Pro) or Mistral AI (open-mixtral-8x7b / mistral-large) |
| Data profiling | pandas |
| SQL execution | SQLite (sqlite3) |
| Structured outputs | Pydantic |
| PBIR generation | Python (custom PBIR compiler) |
| Visualisation | Power BI Desktop |
| Version control | Git, GitHub |

---

## Test Datasets

| Dataset | Domain | Source |
|---|---|---|
| Chinook | Music retail | Public SQLite sample DB |
| Online Retail | E-commerce | UCI ML Repository |
| HR Analytics | Human resources | Kaggle public dataset |

---

## Setup

```bash
git clone https://github.com/your-username/agentic-bi-builder
cd agentic-bi-builder
pip install -r requirements.txt
cp .env.example .env       # add your GEMINI_API_KEY or MISTRAL_API_KEY
python run_agent.py --input data/chinook.csv --output output/chinook_report
```

Then open `output/chinook_report/report.pbip` in Power BI Desktop.

---

## Project Status

In development — June/July 2026
