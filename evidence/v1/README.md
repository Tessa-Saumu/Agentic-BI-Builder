# Evidence bundle v1 — Agentic BI Builder

Auditable artifacts behind the results reported in the README: profile →
KPI specs → SQL results → reflection → compile summary, plus the
fault-injection stress-test outputs. See `metadata.json` for environment
provenance (Python/package versions, model IDs, dates).

## What is in here

| Directory | Contents |
|---|---|
| `chinook/` | Full set: profile, KPI specs, query results, reflection log, sabotaged KPIs, stress-test reflection, run summary |
| `online_retail/` | Full set, including the one organic Reflector catch (`online_retail_reflection.json`, timestamp-granularity fix) |

HR Analytics is intentionally not included: no reflection or stress-test
logs were ever committed for it, and its committed KPI sets are superseded
by the confirmation run whose raw artifacts were never retained (see below).

## Provenance: historical vs. regenerated

Each dataset directory mixes two artifact kinds. They are labeled here
because they mean different things:

**Historical (verbatim from git history, commit `6fed674`, 2026-07-18 —
"Reran full pipeline; generated mistral assets"):**

- `*_kpis.json` — real LLM output (domain hypothesis + 5 KPI specs with SQL)
- `*_kpis_sabotaged.json`, `*_stress_test_reflection.json` — real
  fault-injection harness outputs (3 planted issues each, all caught)
- `online_retail_reflection.json` — the real organic Reflector catch
  (timestamp-granularity fix, 2026-07-18)

**Regenerated deterministically on 2026-10-07 with the pinned environment
(`requirements.txt`, Python 3.11.2 — see `metadata.json`):**

- `*_profile.json` — profiler output. The profiler is deterministic; the
  schema is unchanged since July (same top-level and per-column keys as the
  historical profiles), so these match what the historical runs saw.
- `*_query_results.json` — historical KPI SQL re-executed against the
  committed CSVs via `agent/sql_executor.py`. Deterministic given
  profile + SQL; no LLM calls.
- `*_run_summary.json` — machine-readable summary (`run_agent.py`
  `_build_run_summary`) over the deterministic path: profiler → historical
  KPI specs → executor → compiler, with LLM nodes skipped. `provider` /
  `model` record the effective environment defaults at generation time,
  not the historical runs' models (which were not recorded — see below).

**Placeholder (neither historical nor regenerated):**

- `chinook/chinook_reflection.json` — `{"notes": []}` with an explanatory
  `provenance` field. The historical Chinook run flagged zero issues, and
  `run_reflector` writes no file in that case by design, so no historical
  Chinook reflection log exists to extract. The placeholder records that
  absence explicitly rather than leaving the gap ambiguous.

## Honest limits of this bundle

1. **The historical runs' provider and model IDs were never recorded.**
   The `6fed674` commit message mentions Mistral assets, but the KPI
   naming/domain style resembles the Gemini confirmation outputs described
   in the README — conflicting weak signals. Treat the historical
   artifacts' provider as **unknown**, not as either provider.
2. **These are July development runs, not the August confirmation runs.**
   The README's per-provider result tables describe the final confirmation
   round (August 2026), whose raw KPI/reflection JSONs were never
   committed (removed in `356670c`, 2026-07-23). KPI names here differ
   slightly from those tables. This bundle proves the pipeline's
   mechanisms (real LLM specs → real execution → real reflection →
   real compile) with traceable artifacts; it does not reproduce the
   confirmation tables cell-for-cell.
3. **Compile outcomes reflect current code, not July code.** The
   historical Online Retail run dropped "Total Unique Customers" at
   compile time (the `COUNT(DISTINCT …) … WHERE … IS NOT NULL` gap); the
   regenerated `online_retail_run_summary.json` shows 5/5 compiled because
   that gap was closed during flagship hardening (G20). The historical
   `*_kpis.json` SQL is unchanged — only the compiler improved.
4. **No `.pbip` folders are committed.** They embed the compiling
   machine's absolute CSV path and are regenerable from this bundle's
   profile + KPI specs; see "Regenerating" below.

## Regenerating

**Full live run (requires an API key):**

```bash
pip install -r requirements.txt
cp .env.example .env   # add GEMINI_API_KEY and/or MISTRAL_API_KEY
python run_agent.py --input data/raw/chinook.csv --output output/chinook_report
```

**Deterministic path without keys** (what produced the regenerated files
above — same shape as `tests/test_end_to_end.py`):

```bash
python scripts/profile_datasets.py   # profiles for all three datasets
```

then load a bundled `*_kpis.json` into `AgentState`, run
`agent.sql_executor.run_sql_executor` → `pbir.compiler.builder.run_pbir_compiler`
→ `run_agent._build_run_summary`, as `tests/test_end_to_end.py` does.
