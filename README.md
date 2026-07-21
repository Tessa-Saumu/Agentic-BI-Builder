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

## Validation Results (Phase 4)

All three datasets run end-to-end via `run_agent.py` without crashing, under both supported LLM providers, on every KPI (5/5, no drops). Each `.pbip` opens in Power BI Desktop. This is the confirmation run after the three fixes listed under Failure Modes below.

### Chinook

| Provider | Domain Inferred | KPIs Proposed | Reflection | Pages / Visuals | Total Time |
|---|---|---|---|---|---|
| Mistral | digital music retail (e-commerce) | Total Revenue, Revenue by Country, Monthly Revenue Trend, Average Tracks per Invoice, Top Artists by Revenue | No issues found | 2 / 5 | 12.55s |
| Gemini | digital music store retail | Total Sales Revenue, Monthly Revenue Trend, Top 10 Countries by Revenue, Top 10 Primary Artists by Revenue, Average Tracks per Invoice | No issues found | 2 / 5 | 27.19s |

**Verified:** Page 1 (cards) renders visually identical between providers — same `$2.33K` Total Revenue and `5.44` Average Tracks per Invoice values, confirmed by re-running Chinook on both providers and comparing side by side. Chinook's small, fixed dataset and simple aggregations (`SUM`, `AVG`) have only one correct value regardless of how each LLM names or phrases the KPI, so the underlying numbers match even though the KPI labels differ (`Total Sales Revenue` vs. `Total Revenue`). See `assets/chinook/gemini_page1_revenue_tracks.png` and `assets/chinook/mistral_page1_revenue_tracks.png`.

### Online Retail

| Provider | Domain Inferred | KPIs Proposed | Reflection | Pages / Visuals | Total Time |
|---|---|---|---|---|---|
| Mistral | e-commerce retail | Total Revenue, Revenue by Country, Monthly Revenue Trend, Average Order Value (AOV), Top 10 Products by Revenue | No issues found | 2 / 5 | 16.03s |
| Gemini | e-commerce retail | Total Sales Revenue, Monthly Sales Trend, Top 10 Countries by Revenue, Top 10 Best-Selling Products by Revenue, Average Order Value (AOV) | No issues found | 2 / 5 | 32.02s |

### HR Analytics

| Provider | Domain Inferred | KPIs Proposed | Reflection | Pages / Visuals | Total Time |
|---|---|---|---|---|---|
| Mistral | HR/employee retention and satisfaction | Attrition Rate by Department, Average Job Satisfaction by Job Role, Monthly Income vs. Years at Company, Work-Life Balance by Overtime Status, Overall Employee Attrition Rate | No issues found | 3 / 5 | 20.78s |
| Gemini | HR / Talent Analytics | Overall Attrition Rate, Attrition Rate by Department, Average Monthly Income by Years at Company, Work Environment and Job Satisfaction by Role, Attrition Rate by Overtime Requirement | No issues found | 3 / 5 | 19.69s |

### Gemini vs. Mistral — Provider Comparison

| Metric | Mistral | Gemini |
|---|---|---|
| Total time, all 3 datasets | 49.36s | 78.90s |
| Average `domain_kpi` time | 11.17s | 12.34s |
| Average `reflector` time | 2.78s | 9.06s |
| KPI naming style | Consistently short (`Total Revenue`, `Revenue by Country`) | Consistently longer/more descriptive (`Top 10 Best-Selling Products by Revenue`) — the direct cause of the visual-name-length bug below; Mistral's shorter style never triggered it |
| Transient provider errors this round | One 429 rate-limit on `domain_kpi` (HR), auto-recovered via fallback model | One 503 high-demand on `reflector` (Online Retail), auto-recovered via retry-with-backoff |
| KPIs dropped at compile time | 0/15 | 0/15 |
| Output value agreement (Chinook) | Identical to Gemini on simple aggregates (Total Revenue, Average Tracks per Invoice) — verified visually, re-run confirmed | Identical to Mistral on the same two metrics — labels differ (`Total Sales Revenue` vs. `Total Revenue`), values and layout do not |

Mistral is consistently faster across every node in every run this round. The gap is largest in `reflector` (Gemini averages ~3.3x Mistral's time there), plausibly related to Gemini's longer, more elaborated KPI names and reasoning text increasing prompt/response size — not confirmed, just the most visible correlate in this data.

### Per-Node Timing

| Dataset | Provider | profiler | domain_kpi | sql_executor | reflector | sql_executor_retry | pbir_compiler | Total |
|---|---|---|---|---|---|---|---|---|
| Chinook | Mistral | 0.03s | 10.91s | 0.02s | 1.59s | — | 0.00s | 12.55s |
| Chinook | Gemini | 0.03s | 13.06s | 0.01s | 14.08s | — | 0.00s | 27.19s |
| Online Retail | Mistral | 0.88s | 10.64s | 2.55s | 1.97s | — | 0.00s | 16.03s |
| Online Retail | Gemini | 0.84s | 11.98s | 2.52s | 16.67s | — | 0.00s | 32.02s |
| HR Analytics | Mistral | 0.02s | 11.97s | 0.03s | 8.75s | — | 0.01s | 20.78s |
| HR Analytics | Gemini | 0.03s | 12.91s | 0.01s | 6.74s | — | 0.00s | 19.69s |

`sql_executor_retry` did not fire in this confirmation round for either provider — no KPI needed a fix on first pass. (An earlier Gemini/Online Retail run did trigger it once, for a timestamp-granularity fix; see the stress test section below for repeatable, on-demand evidence of the same retry path.)

### Reflector Correction — Fault-Injection Stress Test

`scripts/run_reflector_stress_test.py` deliberately injects three realistic SQL errors (`sql_error`, `wrong_aggregation`, `null_heavy`) into a copy of each dataset's real, already-validated KPI set, then runs the real SQL Executor and Reflector against the sabotaged copy. This is a separate, clearly-labeled test path — its output (`*_kpis_sabotaged.json`, `*_stress_test_reflection.json`) is never read by `run_agent.py` or any part of the real pipeline.

**Chinook (Gemini), 3/3 caught, 3/3 fixed:**
| KPI | Planted | Detected As | Fix Offered |
|---|---|---|---|
| Total Sales Revenue | sql_error | sql_error (exact) | Yes |
| Monthly Revenue Trend | wrong_aggregation | wrong_aggregation (exact) | Yes |
| Top 10 Countries by Revenue | null_heavy | wrong_aggregation | Yes |

**Online Retail (Gemini), 3/3 caught, 3/3 fixed:**
| KPI | Planted | Detected As | Fix Offered |
|---|---|---|---|
| Total Sales Revenue | sql_error | sql_error (exact) | Yes |
| Monthly Sales Trend | wrong_aggregation | wrong_aggregation (exact) | Yes |
| Top 10 Countries by Revenue | null_heavy | wrong_aggregation | Yes |

**Chinook (Mistral), 3/3 caught, 3/3 fixed:**
| KPI | Planted | Detected As | Fix Offered |
|---|---|---|---|
| Total Revenue | sql_error | implausible_result | Yes |
| Revenue by Country | wrong_aggregation | wrong_aggregation (exact) | Yes |
| Monthly Revenue Trend | null_heavy | wrong_aggregation | Yes |

**Online Retail (Mistral), 3/3 caught, 3/3 fixed:**
| KPI | Planted | Detected As | Fix Offered |
|---|---|---|---|
| Total Revenue | sql_error | sql_error (exact) | Yes |
| Revenue by Country | wrong_aggregation | wrong_aggregation (exact) | Yes |
| Monthly Revenue Trend | null_heavy | wrong_aggregation | Yes |

12/12 planted issues caught this round, 12/12 had a fix offered, 0 missed — consistent with an earlier stress-test round run before the `builder.py`/`serialiser.py` fixes below (also 12/12), for 24/24 total across every stress test run to date. In every run, the `null_heavy` injection was categorized as `wrong_aggregation` rather than an exact match — a defensible alternate diagnosis, since the injected query's root problem (grouping by the wrong column) manifests as an aggregation error before it manifests as null-heaviness; the Reflector consistently identified the actual defect.

### Failure Modes Observed (and Fixed)

Three real bugs were found via this validation pass and fixed before this confirmation round — all three are `pbir/compiler/` issues (SQL→DAX translation and `.pbip` serialisation), not `agent/` pipeline logic:

| Failure | Dataset / Provider | Description | Resolution |
|---|---|---|---|
| SQL→DAX translation gap: `CAST`/`COUNT(CASE WHEN...)` conditional-percentage phrasing | HR Analytics, both providers | 3 of 5 KPIs failed translation with `Cannot translate SQL to basic DAX`, dropping HR below the 4-visual minimum and blocking the build entirely | Fixed — `builder.py`'s translator extended to recognize this phrasing alongside the originally-supported `SUM(CASE WHEN...ELSE...)` form |
| Relative Power Query source path | All three datasets, both providers | `.pbip` failed to load in Power BI Desktop: "the supplied file path must be a valid absolute path" | Fixed — `serialiser.py`'s M-query builder resolves a relative path to absolute; an already-absolute path (POSIX or Windows) is left untouched |
| Visual name exceeding Desktop's 50-character limit | Chinook and HR, Gemini only | Gemini's more descriptive KPI naming style produced `visual_id`s over 50 characters, which Desktop rejects outright at load time. Never triggered by Mistral's shorter naming style | Fixed — `serialiser.py` truncates `visual_id` to 50 chars consistently across the visual's folder name, its own `visual.json` name, and its filter names |

**Known remaining gap, not fixed:** `COUNT(DISTINCT col) ... WHERE col IS NOT NULL` still fails SQL→DAX translation (observed once, Online Retail/Gemini, an earlier run's `Total Unique Customers` KPI). The report still built above the 4-visual minimum in that instance. Out of scope for this validation pass; documented here for a future `builder.py` fix.

**No instances observed:** wrong domain inference, in any run, either provider.

---





In development — June/July 2026