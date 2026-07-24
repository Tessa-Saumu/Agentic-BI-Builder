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
├── assets/                      # Individual Report Visuals,  Repository artifacts  
│   ├── chinook/
│   ├── hr_analytics/
│   ├── online_retail/
│   ├── architecture_diagram.png
│   └── demo.gif
│
├── pbir/                       # PBIR compiler (core innovation)
│   ├── compiler/
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
│   ├── prepare_chinook.py
│   ├── profile_datasets.py
│   ├── run_domain_kpi_all.py
│   ├── run_sql_reflector_all.py
│   ├── run_reflector_stress_test.py
│   └── run_pbir_compiler_all.py
│
├── data/
│   ├── raw/                    # Input datasets
│   │   ├── chinook.csv
│   │   ├── hr_analytics.csv
│   │   └── online_retail.csv
│   │
│   └── profiles/               # Generated profiling + KPI outputs
│       ├── *_profile.json
│       ├── *_kpis.json
│       └── *_reflection.json
│
├── tests/                      # Unit tests
│   ├── test_domain_kpi.py
│   ├── test_llm_client.py
│   ├── test_pbir_compiler.py
│   ├── test_profiler.py
│   ├── test_reflector.py
│   └── test_sql_executor.py
│
├── notebooks/                  # Exploration / validation - not utilized for implementation
│   ├── 01_dataset_profiling_exploration.ipynb 
│   ├── 02_kpi_proposal_review.ipynb
│   ├── 03_sql_validation_and_reflection.ipynb
│   └── 04_pbir_output_inspection.ipynb
│
├── docs/
│   └── pbir_reference.md
│
├── run_agent.py                # Entry point
├── requirements.txt
├── README.md
└── STRUCTURE.md
```

Generated artifacts (`output/`, PBIR builds, caches) omitted for clarity. The structure above reflects core system design. See `.gitignore` for what is excluded from version control.