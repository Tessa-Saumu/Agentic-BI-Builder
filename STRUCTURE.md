# Repository Structure

```
agentic-bi-builder/
│
├── agent/                      # Core agent logic (LangGraph pipeline)
│   ├── domain_kpi.py
│   ├── graph.py
│   ├── llm_client.py
│   ├── models.py
│   ├── profiler.py
│   ├── reflector.py
│   ├── sql_executor.py
│   └── state.py
│
├── assets/                     # Individual Report Visuals, Repository artifacts
│   ├── chinook/
│   ├── hr_analytics/
│   ├── online_retail/
│   ├── architecture_diagram.png
│   └── demo.gif
│
├── pbir/                       # PBIR compiler (core innovation)
│   ├── compiler/
│   │   ├── theme_assets
│   │   ├── builder.py
│   │   ├── layout.py
│   │   ├── m_query.py
│   │   ├── serialiser.py
│   │   ├── sql_to_dax.py
│   │   ├── templates.py
│   │   ├── tmdl.py
│   │   └── visual_json.py
│   │
│   └── models/
│       ├── column.py
│       ├── common.py
│       ├── dtypes.py
│       ├── field_ref.py
│       ├── measure.py
│       ├── page.py
│       ├── project.py
│       ├── table.py
│       └── visual.py
│
├── scripts/                    # Execution pipelines
│   ├── _scaffold_phase1_reference.sh   # HISTORICAL ONLY -- do not run (overwrites modules)
│   ├── prepare_chinook.py
│   ├── profile_datasets.py
│   ├── run_domain_kpi_all.py
│   ├── run_sql_reflector_all.py
│   ├── run_reflector_stress_test.py
│   └── run_pbir_compiler_all.py
│
├── evidence/                   # Committed, auditable run artifacts (flagship bundle)
│   └── v1/
│       ├── README.md           # provenance: historical vs. regenerated
│       ├── metadata.json       # env, models, dates, regen commands
│       ├── chinook/            # profile, KPIs, query results, reflection,
│       └── online_retail/      # sabotaged KPIs, stress reflection, run summary
│
├── data/
│   ├── raw/                    # Input datasets
│   │   ├── chinook.csv
│   │   ├── chinook.sqlite
│   │   ├── hr_analytics.csv
│   │   └── online_retail.csv
│   │
│   └── profiles/               # Generated profiling + KPI outputs (gitignored)
│       ├── *_profile.json
│       ├── *_kpis.json
│       └── *_reflection.json
│
├── output/                     # Generated reports (gitignored except .gitkeep)
│   ├── .gitkeep
│   ├── reference_report/       # hand-authored reverse-engineering artifact (tracked)
│   └── <dataset>_report/       # per-run .pbip output + run_summary.json
│
├── tests/                      # Unit tests
│   ├── fixtures/
│   │   ├── online_retail_profile.json
│   │   └── kpis/               # deterministic KPI fixtures per dataset
│   │       ├── chinook_kpis.json
│   │       ├── hr_analytics_kpis.json
│   │       └── online_retail_kpis.json
│   ├── test_demo_app.py        # deterministic demo (demo_core.py + app.py)
│   ├── test_domain_kpi.py
│   ├── test_end_to_end.py
│   ├── test_graph.py
│   ├── test_llm_client.py
│   ├── test_pbir_compiler.py
│   ├── test_prepare_chinook.py
│   ├── test_profiler.py
│   ├── test_reflector.py
│   └── test_sql_executor.py
│
├── notebooks/                  # Exploration / validation notebooks
│   ├── README.md
│   ├── 02_kpi_proposal_review.ipynb
│   └── 03_sql_validation_and_reflection.ipynb
│
├── docs/
│   ├── Project Description.md
│   └── pbir_reference.md        # 1,129-line reverse-engineered PBIR spec
│
├── .github/workflows/tests.yml # CI: pytest on Python 3.10 / 3.11 / 3.12
├── .streamlit/config.toml      # demo app config (Community Cloud / local)
│
├── run_agent.py                # Entry point (writes <output>/run_summary.json)
├── app.py                      # Streamlit demo UI (deterministic, zero API keys)
├── demo_core.py                # Headless demo core (no Streamlit, no LLM imports)
├── requirements.txt            # agent + tests
├── requirements-demo.txt       # adds streamlit, for app.py only
├── .gitignore
├── .env.example
├── LICENSE                     # MIT
├── README.md
├── STRUCTURE.md
```

Generated artifacts (`output/<dataset>_report/`, `data/profiles/`, caches, and
the demo's temp-dir `.pbip`/zip output) omitted for clarity except where noted.
See `.gitignore` for what is excluded from version control.
