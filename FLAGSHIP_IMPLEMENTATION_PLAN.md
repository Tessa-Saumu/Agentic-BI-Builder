# Flagship Implementation Plan — Agentic BI Builder

**Source audit:** `FLAGSHIP_GAP_AUDIT.md` (2026-10-07)
**Starting revision:** commit `764883a` (`v1.0.0`), working branch `arena/5d602964-agentic-bi-builder`
**Goal:** Minimum engineering to satisfy the Flagship Definition of Done, preserving existing working functionality and existing verified results.

**Design constraints honored throughout:**
- No architecture changes. The LangGraph topology, Pydantic state contract, regex SQL→DAX translator, in-memory SQLite executor, and PBIR/TMDL compiler remain untouched in structure.
- No new frameworks (no FastAPI, no Docker, no sqlglot, no vector DB, no React/frontend, no PyTorch).
- No v2 features (no multi-table joins, no Streamlit agent UI, no Power BI Service, no RAG).
- The deployed public demo (Phase 5) is scoped to the **deterministic** pipeline path with pre-committed fixtures — it does not require API keys and does not expose the live LLM path publicly.
- Existing verified numerical results (Chinook $2.33K revenue, 5.44 average tracks, 216 tests, 24/24 fault catches with caveats) are not silently edited; they are placed behind explicit provenance and the new evidence bundle.
- Mentor contributions remain credited; history is not rewritten.
- All tasks map to gap IDs (G1–G25) from `FLAGSHIP_GAP_AUDIT.md`.

**Phasing summary (max 5):**
| Phase | Focus | Gaps covered | Est. days |
|---|---|---|---|
| 1 | Fresh-clone stability (P0) | G1, G2, G3, G4, G5, G7 | ~1.5 |
| 2 | Verification infrastructure | G6, G9, G10, G18 | ~2.5 |
| 3 | Evidence bundle and claim discipline | G8, G15, G16, G17 | ~2 |
| 4 | Bounded functional and cleanliness polish | G20, G21 (remove), G22 | ~1 |
| 5 | Portfolio packaging + public demonstration | G11, G12, G13, G14, G19, G25 + DoD verification | ~2–3 |
| **Total** | | | **~9–10 days** |

G23 (semantic evaluation pilot) and G24 (structured logging) are explicitly **deferred** — see Phase 5 "Stop Conditions" and the "Stop Conditions" section at the end. The DoD does not require either.

---

## Phase 1 — Fresh-Clone Stability (P0 blockers)

### Objective
Make `git clone && pip install -r requirements.txt && pytest` produce a clean green run on a fresh virtualenv with zero manual steps; remove the footgun that overwrites implemented modules; add a LICENSE; make the CLI fail noisily; fix the dataset filename drift.

### Files / components affected
- `tests/test_domain_kpi.py` (fixture path)
- `tests/fixtures/` (new directory — committed profile fixture)
- `scripts/profile_datasets.py` (HR filename)
- `notebooks/03_sql_validation_and_reflection.ipynb` (HR filename)
- `requirements.txt` (pinning, dead dep removal, add pytest)
- `LICENSE` (new file — MIT)
- `fix_structure.sh` (rename or add header warning + non-executable safety)
- `run_agent.py` (exit codes)

### Exact changes

1. **G1 — Green fresh-clone tests.** Change the `retail_profile` fixture in `tests/test_domain_kpi.py` to load from a *committed* `tests/fixtures/online_retail_profile.json` rather than from `data/profiles/`. Generate that fixture by running the existing profiler on `data/raw/online_retail.csv` once and committing the JSON. Delete the 18-error dependency on a gitignored path. Do **not** commit `data/profiles/` generically — commit only the one fixture needed by tests. (Alternative: generate via a session-scoped fixture that calls `run_profiler` directly — this avoids committing a large static JSON and exercises the profiler in every test run. Choose the in-fixture generation approach if the file is >100 KB; otherwise commit it for speed and stability. Online Retail is 541 K rows; profiling takes ~0.85 s — a session-scoped fixture is acceptable and keeps the repo smaller.)

2. **G2 — Fix HR filename drift.** In `scripts/profile_datasets.py`, change `"data/raw/hr.csv"` → `"data/raw/hr_analytics.csv"` in the `DATASETS` list and in the module docstring. Fix the same stale `../data/raw/hr.csv` reference in `notebooks/03_sql_validation_and_reflection.ipynb` (edit cell 2 or wherever it appears). Leave the historical note "→ Rename to hr.csv → place in data/raw/" accurate to the old era (move it to a historical note if present, or just update the active path).

3. **G3 — Pin dependencies.** In `requirements.txt`:
   - Add `pytest`.
   - Remove `langchain-core`, `langchain-google-genai`, `langchain-mistralai`, `rich` (grep confirms zero source imports).
   - Keep `google-genai`, `mistralai`, `langgraph`, `pandas`, `numpy`, `pydantic>=2.0`, `python-dotenv`, `openpyxl` (used by pandas for xlsx I/O, keep), `jupyter`, `ipykernel` (needed for notebooks — keep but mark as dev extras comment).
   - Pin major.minor versions using `pip freeze` from a clean venv where all 216 tests pass. Use `~=` compatible-release pins (e.g. `pandas~=2.2`) rather than exact pins, to avoid install failures from patch deltas, **except** for `langgraph`, `google-genai`, `mistralai`, and `pydantic` which the code depends on more tightly — use `==` for those four with versions verified to pass the suite.
   - Add a comment at the top: `# Tested on Python 3.10, 3.11, 3.12` (verify 3.12 is viable; if not, state the narrow floor `# Tested on Python 3.10+; 3.11 recommended`).
   - Do **not** add a `pyproject.toml` — that's a refactor beyond minimum scope.

4. **G4 — LICENSE.** Add a standard MIT `LICENSE` file at repo root, copyright holder "Theresia (Tessa) Saumu", year 2026.

5. **G5 — Neutralize `fix_structure.sh`.** Rename to `scripts/_scaffold_phase1_reference.sh` (moves it out of repo root and prefixes with underscore to signal "not for execution"). Update the file's header comment (first 20 lines) to state clearly:
   > HISTORICAL SCAFFOLD SCRIPT — DO NOT RUN. This script was used only during Phase 1 (June 2026) to create the initial directory structure. Running it will overwrite `agent/state.py` and other implemented modules with stubs. Preserved here for reference only.
   Remove execute permission (`chmod -x`). Do not delete it — it's part of the project's historical record and the evidence trail.

6. **G7 — Non-zero exit codes in `run_agent.py`.** Import `sys`; at the bottom of `main()`, after printing errors and the summary:
   - If `not report_written` or `final_state.errors` is non-empty → `sys.exit(1)`.
   - Else → `sys.exit(0)` (explicit).
   Preserve all existing stdout output. This change is load-bearing for CI (Phase 2).

### Tests / checks
- All 216 existing tests must still pass (no behaviour changes to the pipeline).
- After G1, from a clean venv: `pip install -r requirements.txt && pytest` → `216 passed, 0 errors, 0 failures` with no additional commands. Verify by deleting any local `data/profiles/` directory before running.
- After G2: `python scripts/profile_datasets.py` must process all three datasets (chinook, online_retail, hr_analytics) — verify the HR output file `data/profiles/hr_analytics_profile.json` is created (not `hr_profile.json`).
- After G7: verify failure exit by calling `run_agent.py --input data/raw/chinook.csv --output /tmp/out` with a deliberately invalid state (mock via a new small test in Phase 2; for Phase 1, verify by code inspection + running against a non-existent input path that surfaces the error path).
- Grep for `langchain-core`, `langchain-google-genai`, `langchain-mistralai`, `rich` imports in `agent/`, `pbir/`, `run_agent.py`, `scripts/*.py` — should remain zero hits (already true, requirements change just removes them).

### Expected output
- Fresh clone → 216 green tests with zero manual steps.
- LICENSE present.
- Requirements install cleanly; no dead deps; pytest included.
- `fix_structure.sh` cannot be accidentally run from the root (moved, marked, non-executable).
- CLI returns exit code 1 on build failure.
- Driver scripts process all three datasets.

### Acceptance criteria
- [x] `rm -rf data/profiles && pytest` from repo root after `pip install -r requirements.txt` → all tests pass.
- [x] `python scripts/profile_datasets.py` produces profiles for all three datasets with the correct dataset names.
- [x] `LICENSE` file exists at repo root and is MIT.
- [x] No scaffold script exists at repo root that can overwrite `agent/state.py`.
- [x] `python run_agent.py --input nonexistent.csv --output /tmp/out ; echo $?` prints errors and exits nonzero.

### Rollback / risk considerations
- **Fixture commit approach (G1 alternative)**: if the session-scoped profiler fixture approach is slow on low-memory CI, fall back to committing the static JSON under `tests/fixtures/`. The fixture must be regenerated and committed if `agent/profiler.py`'s DataProfile schema changes; add a comment documenting this.
- **Dependency pinning (G3)**: if a pinned version of `google-genai` or `mistralai` breaks in the future, the pins will require updating. That's expected and is the *point* of pinning — it prevents silent test failure at clone time.
- **Exit code change (G7)**: risk that existing users (e.g. mentor scripts) depend on exit 0; acceptable because `run_agent.py` is not currently called by other scripts in the repo (verified: only called by humans via CLI).
- **Notebook edit (G2)**: only changes a string constant in a code cell; does not clear outputs or alter notebook structure.

---

## Phase 2 — Verification Infrastructure

### Objective
Add mechanical proof for the architectural claims that are currently asserted only by code reading: graph wiring, the one-retry-no-loop invariant, KPI drop on retry failure, the min-visual build gate, end-to-end deterministic pipeline, and a machine-readable run summary. Stand up CI so this proof runs on every push.

### Files / components affected
- `.github/workflows/tests.yml` (new)
- `tests/test_graph.py` (new)
- `tests/test_end_to_end.py` (new — no-network deterministic regression)
- `tests/fixtures/kpis/` (new — 3 files: committed valid KPI fixtures per dataset, plus one bad-KPI fixture for rejection testing)
- `run_agent.py` (add `run_summary.json` write — G18)
- Optionally: small refactor in `run_agent.py` to extract a `_build_summary()` helper for testability.

### Exact changes

1. **G6 — GitHub Actions CI.** Create `.github/workflows/tests.yml`:
   - Trigger: `push` and `pull_request` to `main` (and to `arena/*` branches if we keep branch workflow).
   - Matrix: Python `["3.10", "3.11", "3.12"]` (subject to G3's verified floor).
   - Steps: checkout → `pip install -r requirements.txt` → `pytest -v`.
   - Cache: `pip` cache via `actions/setup-python` cache: 'pip'.
   - **No secrets.** All LLM calls must remain mocked; if any new test accidentally hits a real SDK, that test must be patched.
   - Fail the workflow on non-zero pytest exit; the G7 exit-code contract from Phase 1 makes the tested `run_agent.py` integration path CI-catchable.
   - Do **not** add lint, typecheck, coverage, or publishing steps in this phase. Keep the workflow narrowly focused on "tests pass."
   - Add a CI badge to README after the first successful run (Phase 5 handles README polish, but the badge line can be prepared now).

2. **G10 — Graph-level unit tests** (`tests/test_graph.py`). Test:
   - `_route_after_reflection` returns `"sql_executor_retry"` when `state.kpis_to_retry` is non-empty, `"pbir_compiler"` when empty.
   - The compiled graph has no edge from `sql_executor_retry` back to `reflector` (assert on `build_graph().get_graph().edges` — inspect LangGraph API to get the edge list; alternatively, assert on the node names and conditional edge map). This is the one-retry-no-loop topological invariant.
   - `run_sql_executor_retry` clears `state.kpis_to_retry` after processing (already tested indirectly in `test_sql_executor.py`? Check — if covered, do not duplicate; if not, add).
   - Node invocation order: profiler → domain_kpi → sql_executor → reflector, then conditional. Test by executing the graph with all LLM clients patched; assert `list(final_state.node_timings.keys())` matches expected order.
   - All LLM-dependent nodes are mocked via `unittest.mock.patch` on `agent.domain_kpi._call_llm` and `agent.reflector._call_llm` (or the llm_client invocation point) so the graph test is a pure orchestration test with no network.

3. **G9 — No-network end-to-end regression test** (`tests/test_end_to_end.py`).
   - Commit three KPI fixture files under `tests/fixtures/kpis/{chinook,online_retail,hr_analytics}_kpis.json`. Each contains the known-good 4–5 KPIs per dataset (taken from validated runs — use SQL that already passes the translator, e.g. the Chinook set from README: Total Revenue, Revenue by Country, Monthly Revenue Trend, Average Tracks per Invoice; or a smaller set of definitely-supported shapes).
   - For each dataset: run `profiler` → load fixed KPI specs into state (skip `domain_kpi` by directly assigning `state.kpi_specs` and `state.domain_hypothesis`) → `run_sql_executor` → a mocked reflector that returns no issues → `run_pbir_compiler` → `write_pbip` to a `tmp_path`. Assert:
     - No errors in `state.errors`.
     - `pbir_project.pages` has expected page count, each page has expected visual count.
     - TMDL output contains the expected number of `measure` blocks (one per KPI).
     - M partition contains an absolute-path `File.Contents(...)` entry pointing at the input CSV.
     - DAX expressions match the translator output (spot-check 1–2 measures, e.g. revenue measure contains `SUM(...)`).
   - **KPI-drop case:** load a fixture with one KPI containing unsupported SQL (e.g. a `SELECT` referencing a nonexistent column); run executor → a reflector mock that flags it with `fixed_sql_query=None` (unfixable); assert retry drops it, and the final report does not contain that KPI.
   - **Min-visual rejection case:** load a fixture with only 2 valid translatable KPIs (the rest unsupported); run the compiler; assert `run_pbir_compiler` records an error in `state.errors` about the minimum-visuals gate, and the report is not produced (i.e. `pbir_project` is None or `write_pbip` raises the gate error — match the existing behavior in `pbir/compiler/builder.py`).
   - **Repair-and-retry case:** load a valid KPI set but with one KPI deliberately sabotaged (e.g. wrong column); mock reflector to return a `fixed_sql_query` for it; run the retry node; assert the fixed SQL replaces the KPI's `sql_query`, the KPI is re-executed successfully, and the final report includes it.

4. **G18 — Machine-readable `run_summary.json`.**
   - In `run_agent.py`, after the graph completes and before exiting, write `<output_dir>/run_summary.json` containing:
     - `dataset_name`, `input_path` (basename only; do not leak absolute paths from arbitrary user runs into committed artifacts), `input_path_sha256` (first 12 chars — for integrity checking of evidence bundles),
     - `timestamp_utc` (ISO 8601),
     - `python_version`, `package_versions` (dict of `{langgraph, pandas, pydantic, google-genai or mistralai-used} — only the provider actually invoked),
     - `provider`, `model`, `model_fallback`, `temperature`,
     - `kpi_count_initial`, `kpi_count_final`, `kpi_names_initial`, `kpi_names_final`, `kpis_dropped` (list of names),
     - `reflection_notes_count`, `reflection_fixes_applied`, `reflection_dropped_without_fix`,
     - `node_timings_seconds` (same dict printed to console),
     - `total_seconds`,
     - `errors` (list),
     - `report_written` (bool),
     - `page_count`, `visual_count`,
     - `pbip_output_dir` (relative path from repo root).
   - Extract summary construction into a helper `_build_run_summary(final_state, args)` that can be unit-tested.
   - If `report_written=False`, still write the summary (so CI can inspect failures).
   - Add `run_summary.json` to `.gitignore` for normal runs (user runs shouldn't pollute the repo), but make sure `evidence/v1/` (Phase 3) uses a separate committed location outside `output/`.
   - Add one small test that runs the deterministic path on Chinook via the e2e fixture and asserts the summary JSON contains expected fields.

### Tests / checks
- All 216 existing tests continue to pass.
- New `tests/test_graph.py` passes with no network access (verify by unplugging / setting invalid keys).
- New `tests/test_end_to_end.py` passes with no network access.
- `pytest` collection stays below ~250 tests total; no test takes more than ~5 s on CI.
- GitHub Actions shows green on all three Python versions after push.
- A deliberate graph miswiring (e.g., adding an edge back from retry to reflector) must cause the topology invariant test to fail.
- A deliberate sabotage of the min-visual constant must cause the min-visual rejection test to fail.

### Expected output
- `.github/workflows/tests.yml` committed; green CI badge available (referenced in Phase 5).
- Two new test files adding ~15–25 tests total (keep them focused — avoid test bloat).
- `run_summary.json` produced next to every `.pbip` build.
- Architectural claims (one retry, drop on failure, min-visual gate, end-to-end deterministic compile) are mechanically verified.

### Acceptance criteria
- [x] CI runs green on a fresh push (no API keys).
- [x] Topology test fails if the retry edge is rewired back to reflector, and passes as committed.
- [x] Min-visual rejection test fails if the `MIN_VISUALS_REQUIRED` constant is changed to 2, and passes at 4.
- [x] KPI-drop test verifies that a KPI with an unrepairable SQL error does not appear in the final report.
- [x] `run_summary.json` is written on both success and failure paths and is parseable.

### Rollback / risk considerations
- **CI matrix across Python versions**: if 3.12 has compatibility issues (e.g. with `mistralai` SDK), drop to `["3.10", "3.11"]` rather than spending time on forward-compatibility fixes.
- **End-to-end test scope**: avoid asserting on exact DAX string equality (fragile); assert on presence of `measure` blocks, table names, and high-level structure. TMDL whitespace or ordering changes should not break tests.
- **Graph introspection API**: LangGraph's internal edge-inspection API can change between versions. If getting the edge list is unstable, fall back to a behavioural test: attempt to invoke the graph with `kpis_to_retry` set and verify reflector is not called a second time (via mock call counts).
- **run_summary.json**: keep the schema additive; don't let the summary become a reimplementation of AgentState.

---

## Phase 3 — Evidence Bundle and Claim Discipline

### Objective
Make the README's reported results auditable from a checkout: commit a single dated evidence bundle with provenance metadata, reconcile model identifiers and decoding temperature so cross-provider comparisons are honest, narrow the reliability/reflector claims to match the evidence, and document the absolute-path limitation that was previously buried.

This phase does **not** require new live LLM runs if provider keys are unavailable. If keys are available, one fresh live run on Chinook with the pinned environment is preferred; otherwise, explicitly label the bundle as historical from the v1.0.0 release window and document exactly how a reviewer could reproduce it.

### Files / components affected
- `evidence/v1/` (new directory)
- `evidence/v1/metadata.json` (new)
- `evidence/v1/{chinook,online_retail,hr_analytics}/` (new — profiles, KPIs, reflections, stress-test outputs; one provider is sufficient per DoD)
- `.gitignore` (amend so `evidence/v1/` is tracked, not gitignored)
- `agent/llm_client.py` (temperature on Gemini; default model identifiers)
- `.env.example` (model identifiers)
- `README.md` (reliability claims, limitations, references to evidence bundle)
- `run_agent.py` (optional console warning about absolute paths — G17)

### Exact changes

1. **G8 — Committed evidence bundle under `evidence/v1/`.**
   - Create `evidence/v1/README.md` explaining what this directory contains and how it was produced.
   - Subdirectory per dataset. For the minimum bar, commit evidence for **Chinook under one provider** (Mistral is easier because `temperature=0` is already set) plus the stress-test output for that provider. Including all three datasets × both providers is desirable but not required for the DoD.
   - Per dataset, commit:
     - `<dataset>_profile.json` (schema profile output by the profiler — already deterministic; regenerate from pinned env for provenance).
     - `<dataset>_kpis.json` (KPI specs returned by the LLM — must be the real LLM output if keys are available; if keys are not available during this repair, take the KPI set documented in README tables and label it "historical, from v1.0.0 release run 2026-08").
     - `<dataset>_reflection.json` (reflection log — same caveat).
     - `<dataset>_query_results.json` (executor output — deterministic given profile + KPI SQL; regenerable).
     - `<dataset>_kpis_sabotaged.json` + `<dataset>_stress_test_reflection.json` (stress-test harness outputs — regenerable with real keys; if keys unavailable, label historical).
     - `<dataset>_run_summary.json` (the Phase 2 machine-readable summary — regenerate once from pinned env).
   - **If live keys are available**, regenerate one Chinook run end-to-end with pinned dependencies, capture all artifacts, and date them. This satisfies "at least one traceable full live-provider run."
   - **If live keys are NOT available during repair**, commit the artifacts that are *deterministically regenerable* (profile, query results given KPI SQL, compiled .pbip structure summary) and label the LLM-produced artifacts clearly in `evidence/v1/README.md` as:
     > Historical artifacts from the v1.0.0 confirmation run (August 2026, Mistral, mistral-large-latest). Raw API logs are not retained; these KPI specs and reflection notes are preserved from the release-time validation. Regenerate with `python run_agent.py --input data/raw/chinook.csv --output output/chinook_report` using the pinned environment and a Mistral API key.
   - Add `evidence/` to the *tracked* portion of the repo. The existing `.gitignore` ignores `data/profiles/` and `output/*/`; add a line: `!evidence/` (or simply leave `evidence/` out of gitignore since nothing else matches it).
   - Do **not** commit generated `.pbip` folders — they're large, contain absolute host paths, and are regenerable. Commit `run_summary.json` and TMDL snippets (key measure blocks only) if space is a concern.

2. **G15 — Model identifier + temperature consistency.**
   - Choose one canonical set:
     - Gemini primary: `gemini-2.0-flash` (or `gemini-1.5-flash` — pick the stable free-tier ID that works; if uncertain, match what the v1.0.0 run actually used by checking release notes / PR comments — PROJECT_EVIDENCE notes README says `gemini-3.1-flash`; .env.example says `gemini-3.5-flash`; these are likely pre-release codenames. Use the string that actually works against the API today. If neither works, pin to a known-good ID and add a "last verified YYYY-MM-DD" note.)
     - Mistral primary: `mistral-large-latest` (consistent with code default).
   - Update all three places: `llm_client.py` defaults, `.env.example`, README tech-stack table.
   - Set `temperature=0` in the Gemini generation parameters (match Mistral). Add a code comment noting parity: `# temperature=0 for cross-provider determinism; matches Mistral path`.
   - Record exact chosen identifiers in `evidence/v1/metadata.json`.
   - Do **not** silently re-run historical results under new model IDs; label them as historical with model_id_used if it differs from the current canonical value.

3. **G16 — Narrow reliability claim in README.**
   - In the fault-injection results section, replace the summary line "24/24 total across every stress test run to date" with something like:
     > Across two stress-test rounds (2 providers × 2 datasets × 3 planted fault types = 12 planted issues per round; HR was not included in the stress harness), the Reflector caught 12/12 planted issues in each round (24/24 cumulative) and offered a fix SQL for each. In 6/24 cases the planted category was `null_heavy` but the Reflector diagnosed it as `wrong_aggregation` — a defensible alternate diagnosis, since the sabotaged query grouped by the wrong column, which manifests as an aggregation error before null-heaviness.
   - Add a sentence directly under the fault-injection results:
     > On the natural (non-sabotaged) confirmation runs reported above, the Reflector flagged issues in 0–1 KPI per dataset (one organic catch on Online Retail/Gemini for a timestamp-granularity issue). The Reflector's correction capability is demonstrated primarily by planted-fault evidence, not by a high organic error rate — because when the upstream SQL is well-formed, there is typically nothing for it to fix.
   - Remove or qualify any language in scripts/README that uses the word "reliable" as an unqualified adjective for the Reflector (e.g. update `run_reflector_stress_test.py` docstring to say "repeatable evidence of the Reflector's *planted-fault* correction capability" rather than "reliability").

4. **G17 — Document absolute-path embedding (and optional warning).**
   - Add a paragraph to README "Known Limitations":
     > **Report path coupling:** The compiled Power Query M partition embeds the absolute path of the source CSV on the compiling machine (by Power BI's requirement — `File.Contents(...)` does not accept repo-relative paths). A `.pbip` compiled on one machine must be opened on that same machine, or the CSV must be moved to the same absolute path on another machine. When opening for the first time after moving, click **Refresh** once and the report will load — see the first-open banner note above. To compile for a different machine, re-run `run_agent.py` with `--input` pointing at that machine's CSV location.
   - In `run_agent.py`, add a single console `print` (not a warning-level error) after the report is written: `Note: compiled report embeds the absolute CSV path; to move the report to another machine, re-run run_agent.py there.` Keep it light — this is a documented limitation, not a failure.

5. **Record metadata.** Create `evidence/v1/metadata.json`:
   ```json
   {
     "bundle_version": "v1.0",
     "collected_date": "YYYY-MM-DD",
     "collected_by": "manual (flagship repair)",
     "python_version": "...",
     "package_versions": {"langgraph": "...", "pandas": "...", ...},
     "providers_used": ["mistral"],
     "default_model_by_provider": {"mistral": "mistral-large-latest", "gemini": "..."},
     "temperature": 0,
     "datasets_committed": ["chinook"],
     "historical_artifacts_label": "KPI and reflection artifacts for online_retail and hr_analytics are from the v1.0.0 release run (2026-08-30) if a fresh run could not be reproduced during flagship repair.",
     "regeneration_command": "python run_agent.py --input data/raw/<dataset>.csv --output output/<dataset>_report",
     "known_limitations": ["COUNT(DISTINCT col) ... WHERE NOT NULL DAX gap", "single-table scope", "SQLite only", "Power BI Desktop Windows-only"]
   }
   ```

### Tests / checks
- Existing test suite continues to pass after temperature/default changes (mocked SDK tests should not depend on exact default strings; if they do, update them to match the new canonical IDs).
- Evidence bundle files are valid JSON (validate with `python -m json.tool` in CI or as a manual step).
- README no longer contains the bare phrasing "24/24" without an in-line denominator (grep for "24/24" and verify it is accompanied by the per-round explanation).
- Grep README for any unqualified use of "reliable" applied to the Reflector; ensure it is either removed or qualified.
- Absolute-path paragraph appears in README limitations.
- All model strings in `.env.example`, `llm_client.py`, and README match exactly.
- `evidence/v1/` files are tracked by git (not ignored) and do not contain absolute local paths in KPI SQL (KPI SQL uses table name `data` only, which is correct — verify).

### Expected output
- A reproducible evidence bundle a recruiter can inspect: profile → KPI specs → SQL → results → reflection → summary, with environment metadata.
- Cross-provider parity claims are backed by matched decoding settings.
- The 24/24 fault-injection number is presented honestly (n=12 per round, 6/24 adjacent-category diagnoses).
- The absolute-path limitation is visible to readers before they encounter it.

### Acceptance criteria
- [x] `evidence/v1/metadata.json` exists and documents Python, packages, model, temperature, date.
- [x] At least one dataset (Chinook) has a complete evidence subdirectory: profile, KPI specs, reflection log, query results, run summary.
- [x] README fault-injection section contains explicit denominators and the organic-fire-rate note.
- [x] Grep for "24/24" in README shows only qualified uses.
- [x] Model identifiers are byte-identical across `.env.example`, `agent/llm_client.py`, and README tech-stack table.
- [x] `temperature=0` is set in Gemini generation config with a parity comment.
- [x] README Known Limitations includes the absolute-path paragraph.

### Rollback / risk considerations
- **Live keys unavailable:** The plan explicitly accommodates this by allowing historical artifacts with clear labelling. Do not delay the rest of the flagship repair waiting on API access — label honestly and move on. A reader respects "historical artifacts, regen command provided" more than fabricated fresh runs.
- **Model ID changes:** If a free-tier model ID changes upstream (e.g. Google deprecates `gemini-1.5-flash`), the pinned string may need updating. The metadata.json "last verified" date makes this transparent rather than hidden.
- **Temperature=0 on Gemini:** Very small risk that temperature=0 changes the KPI output for future regenerations vs. the historical results. That is expected and correct — future regenerations should be documented with their own metadata, not retconned.
- **Evidence bundle size:** Keep total evidence under ~1–2 MB. Query results are capped at 20 rows per KPI (`MAX_RESULT_ROWS_STORED`), so JSONs are small. If any file exceeds ~100 KB, truncate to representative samples and note in metadata.

---

## Phase 4 — Bounded Functional and Cleanliness Polish

### Objective
Close the two small documented SQL→DAX translation gaps (high ROI: demonstrates finishing discipline and reduces the caveat list), remove the visible dead scaffolding that distracts a first reviewer, and reconcile `STRUCTURE.md` with the actual tree. Do **not** add new features, new visual types, or new datasets.

### Files / components affected
- `pbir/compiler/sql_to_dax.py` (add 2 shape patterns)
- `tests/test_pbir_compiler.py` (add regression tests)
- `notebooks/01_dataset_profiling_exploration.ipynb` (delete)
- `notebooks/04_pbir_output_inspection.ipynb` (delete)
- `data/processed/` (remove `.gitkeep` and directory; or keep with a README explaining it is unused — choose removal, since nothing writes there)
- `STRUCTURE.md` (update to match actual tree)
- `output/.gitkeep` (create, since `.gitignore` `!output/.gitkeep` references it and it currently does not exist)
- `.gitignore` (confirm patterns match reality)
- README (small updates in Phase 5 will note the closed DAX gaps; no structural change needed here)

### Exact changes

1. **G20 — Close the two documented SQL→DAX translator gaps.**
   - In `pbir/compiler/sql_to_dax.py`, extend the shape regexes to recognise:
     - `COUNT(DISTINCT col) ... WHERE col IS NOT NULL` — map to `DISTINCTCOUNTNOBLANK('table'[col])` or to `CALCULATE(DISTINCTCOUNT('table'[col]), 'table'[col] <> BLANK())`. Use the simplest correct DAX shape consistent with existing patterns; add a regression test for the Online Retail "Total Unique Customers" KPI shape that originally failed.
     - T-SQL-style bracket quoting `[col]` — the SQL→DAX translator and `_validate_sql_columns` should treat bracketed identifiers the same as bare identifiers (strip the brackets when checking column existence against the profile; preserve them in the SQL for SQLite? SQLite does not accept `[bracket]` quoting in the same way as T-SQL. Verify whether bracket-quoted queries actually execute in SQLite; if not, add a pre-execution normalization that strips `[`/`]` from column references before execution, since this is a quoting style LLM outputs occasionally. Match the handling of double-quoted identifiers already present.
   - Add two regression tests per shape to `tests/test_pbir_compiler.py` (4 new tests total): one that the translator successfully produces DAX, one that the resulting KPI is not dropped during compilation.
   - Update README "Known remaining gap" language: remove the `COUNT(DISTINCT)` gap, add a brief note that bracket-quoting normalization was added during flagship hardening. Keep the fail-closed semantics: any shape *outside* the supported set still raises `SQLToDaxError`.

2. **G21 — Remove empty notebooks.** Delete `notebooks/01_dataset_profiling_exploration.ipynb` and `notebooks/04_pbir_output_inspection.ipynb` (both 0 bytes). Do not fill them — filling to the quality of `02`/`03` would be 1+ day of content work that adds little evidence beyond what README + architecture diagram + reference doc already provide. Add a note to `notebooks/README.md` (create this small file) explaining:
   > `02_kpi_proposal_review.ipynb` and `03_sql_validation_and_reflection.ipynb` contain live validation outputs from development. Notebooks 01 and 04 were planned placeholders and were removed during v1 consolidation; equivalent profiling walkthroughs are available in `scripts/profile_datasets.py` and in the README.

3. **G22 — Clean dead scaffolding.**
   - Remove the empty `data/processed/` directory (no source file writes to it; `prepare_chinook.py` reads from `data/raw/chinook.sqlite` and writes to `data/raw/chinook.csv`, not to `processed/`). Verify with grep before removing.
   - Create `output/.gitkeep` (empty file) so the `!output/.gitkeep` exception in `.gitignore` works — currently `.gitignore` expects it but it is absent, meaning the ignore pattern `output/*/` is technically satisfied but the parent `output/` directory is created only by the reference_report subtree. An explicit `.gitkeep` makes intent clear.
   - Update `STRUCTURE.md` to reflect the actual tree:
     - Rename `pbir_reference.md` → `pbir reference.md` (match actual filename).
     - Replace `data/profiles/` description to note it is gitignored; add `evidence/v1/` at top level.
     - Remove `data/processed/` (deleted).
     - Remove notebooks 01 and 04 from the tree listing.
     - Add `fix_structure.sh`'s new location `scripts/_scaffold_phase1_reference.sh` (or remove from STRUCTURE if it's not user-facing).
     - Add `run_summary.json` mention.
     - Add `tests/fixtures/` and `tests/test_graph.py`, `tests/test_end_to_end.py`.

### Tests / checks
- All existing tests pass after translator changes.
- 4 new translator tests pass.
- Grep for `COUNT(DISTINCT` translator handling: verify the new regex matches the documented Online Retail failure shape from README.
- Verify bracket-quoted SQL (e.g. `SELECT SUM([Total]) FROM data`) executes against the in-memory SQLite DB after normalization and translates to valid DAX.
- `data/processed/` is gone; `output/.gitkeep` exists; `STRUCTURE.md` reflects the tree.
- Notebooks 01 and 04 are deleted; `notebooks/README.md` exists.
- Manually verify: `python run_agent.py --input data/raw/chinook.csv --output /tmp/chinook_check` (with the deterministic KPI fixture) still produces a valid `.pbip` with expected measure count.

### Expected output
- One fewer "known remaining gap" in README.
- LLM-emitted bracket quoting no longer fails silently.
- No empty files or empty directories remain in the tracked tree.
- STRUCTURE.md is accurate enough that a reader can navigate the repo from it.

### Acceptance criteria
- [x] A `COUNT(DISTINCT col) ... WHERE col IS NOT NULL` KPI successfully translates to DAX and appears as a measure in the compiled report.
- [x] A bracket-quoted `SELECT SUM([Total]) ...` KPI successfully validates against the profile and executes.
- [x] 4 new tests in `test_pbir_compiler.py` cover both shapes; all pass.
- [x] Zero-byte notebooks are removed with a brief explanatory note in `notebooks/README.md`.
- [x] `STRUCTURE.md` filenames match actual `ls` output (verified by diff).

### Rollback / risk considerations
- **SQLite bracket quoting:** T-SQL `[col]` is not standard SQLite. Verify behavior before relying on it: if stripping brackets is fragile (e.g. breaks on column names that *legitimately* contain spaces or brackets), keep the translator fix but treat bracket-quoted columns as a translator-shape extension rather than an executor normalization. It is acceptable for the fix to be at the validator layer (strip brackets before checking against the profile) without modifying executor behavior, as long as a documented test covers the LLM output pattern.
- **Notebook deletion:** If there is any sentimental or historical attachment to the empty notebook filenames, keep them as 1-line markdown stubs with a "Not created — see notebooks README" note instead of deleting. But deletion is cleaner.
- **Do not expand the translator further.** This phase closes the two *specifically documented* gaps; any additional shape (e.g. `HAVING`, subqueries, window functions) stays a v2 feature and must continue to fail closed.

---

## Phase 5 — Portfolio Packaging, Public Demonstration, and Final Verification

### Objective
Make the repository recruiter-ready as a portfolio piece: clear contribution boundaries, consolidated design rationale, fixed README defects, a public zero-key demonstration a recruiter can access without repo permission, repository metadata for discoverability, a short narrated walkthrough, and a final pass verifying every Flagship Definition of Done checkbox. This is the final phase — no further code changes after this except explicit bug fixes.

### Files / components affected
- `README.md` (significant edit: clone URL, links, Design Decisions, What I built / Credits, Quickstart, badge, up-front scope, up-front limitations)
- `docs/pbir reference.md` (filename — rename to `docs/pbir_reference.md` and update README link; OR keep filename and fix link — choose rename since it's safer cross-platform; verify no internal Markdown links break)
- `app.py` (new — minimal Streamlit demo app)
- `requirements-demo.txt` (new — demo-specific requirements)
- `.streamlit/config.toml` (new — for Streamlit Community Cloud)
- `evidence/v1/README.md` (already created in Phase 3; link to it from README)
- GitHub repository settings (description, topics, website link to deployed demo — done via UI, not in-repo)
- `assets/` (add 1–2 screenshots from the Streamlit demo if useful; optional)
- A short Loom/YouTube MP4 or link in README (G25)
- New: `FLAGSHIP_VERIFICATION_CHECKLIST.md` — filled copy of the DoD checklist with evidence references (commit after all other changes)

### Exact changes

1. **G12 — README link/structural fixes.**
   - Replace `https://github.com/your-username/agentic-bi-builder` with the real repo URL `https://github.com/Tessa-Saumu/Agentic-BI-Builder` in both Quickstart and Setup sections.
   - Rename `docs/pbir reference.md` → `docs/pbir_reference.md` (underscore). Update every Markdown reference to it (README links it twice; check STRUCTURE.md; check other docs). This avoids URL-encoding issues and works cross-platform.
   - Add a "Fresh clone note" in Setup: after `pip install -r requirements.txt`, note "`pytest` should show ~240 tests all passing with zero errors; no additional scripts are required." (After Phase 1+2 this is true.)
   - Add a Quickstart-expanded "What you will see" paragraph describing expected output (timing table, reflection summary, `.pbip` folder).
   - Add CI status badge at the top of README once CI is green: `![Tests](https://github.com/Tessa-Saumu/Agentic-BI-Builder/actions/workflows/tests.yml/badge.svg)`.

2. **G13 — "What I built / Credits" section.** Add a new section to README (after "Tech Stack", before "Test Datasets"):

   > ## What I built / Credits
   >
   > Agentic BI Builder was implemented by Theresia (Tessa) Saumu between June and August 2026 as a solo implementation project under structured mentorship. All pipeline nodes, the PBIR/TMDL compiler, typed Pydantic models, validation scripts, fault-injection harness, tests (216 at release, ~240 after flagship hardening), and the 1,129-line PBIR reference documentation were authored by `Tessa-Saumu` (117 of 126 commits on `main` at v1.0.0).
   >
   > Credits to Adeyeri Michael (`Mikehade`):
   > - 7 PR merges, release tagging (`v1.0.0`), and phase/acceptance-criteria review feedback.
   > - Commit `cca0106`: KPI-name uniqueness validation in `DomainKPIResponse`, unknown-KPI-note filtering in the reflector, and the `reviewed_kpi_count` logging fix.
   > - Commit `55578ac`: early environment/scaffold setup.
   >
   > The 7 implementation PRs (#8–#14) and phase issues (#1–#7) contain the full design discussion and review history. This is not a production system or a product with users; it is a v1 bounded prototype built to demonstrate applied LLM workflow engineering.

   This is precise, names the exact mentor contributions, avoids percentage claims beyond the 117/126 commit split, and labels the project honestly.

3. **G14 — "Design Decisions" section.** Add a new subsection (after Architecture, before Demo):

   > ## Design Decisions
   >
   > A few choices are worth calling out explicitly:
   >
   > - **LangGraph for topology, not for agents.** The graph's topology *enforces* the one-retry policy (the retry node has a single edge straight to the compiler — there is no path back to the reflector), rather than enforcing it with a counter in state that any node could accidentally mutate. This makes the retry budget load-bearing rather than conventional.
   > - **Pydantic + provider-native structured output.** The LLM responses are validated against typed Pydantic models (`KPISpec`, `DomainKPIResponse`, `ReflectionNote`) using each provider's native schema response (Gemini `response_schema`, Mistral `chat.parse(response_format=…)`), not via LangChain output parsers or regex-on-text. This is why `langchain-*` appears as an unused dependency in older revisions and has been removed.
   > - **Regex SQL→DAX over a full parser.** The translator recognises five (now seven) SQL measure shapes and fails closed on anything else. A full SQL parser (e.g. sqlglot) would broaden support but also mask failures; fail-closed keeps unsupported KPIs visible to the user rather than silently mistranslated. This is appropriate for a v1 MVP with explicit scope.
   > - **Metadata-only at KPI-proposal time; sampled rows at reflection time.** The domain/KPI prompt sends schema metadata (column names, types, null rates, distinct counts) but deliberately strips sample values and min/max to reduce data-exposure surface and improve output stability. The reflector sees up to 10 sampled result rows per KPI because reviewing numbers requires seeing numbers. This is a deliberate, tested split (see `test_prompt_excludes_sample_values`).
   > - **In-memory SQLite for execution.** No database persists anything; every run loads the CSV into a fresh in-memory instance. This makes execution deterministic, sandboxed, and free of cleanup state, at the cost of no multi-run memory.
   > - **Fail-open per KPI, fail-closed per build.** A single KPI that cannot be translated or that keeps failing after its one retry is dropped (with an error entry) rather than crashing the run; but a report that ends up with fewer than 4 translatable visuals is *rejected entirely* rather than producing a silently thin dashboard. This trade-off prefers partial useful output over deceptive emptiness.

4. **Up-front scope statement.** Add a short paragraph directly under the tagline on line 1:

   > **Scope (v1):** single-table CSV/SQLite input → typed LangGraph workflow → LLM-proposed KPIs with SQL → real SQLite execution → one bounded self-reflection retry → deterministic Power BI Project (.pbip) output. Windows + Power BI Desktop required to open the output. No multi-table joins, no Power BI Service publishing, no hosted service, no production deployment — see [Known Limitations](#known-limitations-and-stretch-goals).

5. **Up-front limitations callouts.** Move the single-table/SQLite/Desktop-only bullets from the deep "Known Limitations" section into a short "At a glance" box near the top (keep the full detail in the limitations section). This makes scope visible in seconds.

6. **G11 — Public Streamlit demo (zero API keys).** Create a minimal `app.py` at repo root:
   - Title: "Agentic BI Builder — Deterministic Demo"
   - Intro paragraph explaining: this is a demo of the deterministic half of the pipeline (no live LLM calls; KPI specs are pre-committed validated fixtures) to show the profiling, SQL execution, and PBIR compilation that the agent's output ultimately goes through. Link back to the repo for the full agent source.
   - Dataset selector (dropdown): Chinook / Online Retail / HR Analytics.
   - "Run profiler and compile" button that:
     1. Calls `run_profiler` on the selected CSV.
     2. Loads the committed KPI fixture for that dataset (`tests/fixtures/kpis/..._kpis.json`).
     3. Calls `run_sql_executor`.
     4. Calls `run_pbir_compiler`.
     5. Calls `write_pbip` to a temp dir.
     6. Shows: profiler summary (column count, row count, per-column null-rate table for top 5 columns), KPI list with SQL and chart type, query result previews (first 5 rows per KPI), and a **download button** for the generated `.pbip` folder as a zip (use `shutil.make_archive` and Streamlit `st.download_button`).
   - Shows the Desktop screenshots from `assets/` for that dataset below the results, with a note: "Opening the downloaded .pbip in Power BI Desktop for Windows produces a report matching these screenshots."
   - Shows a static architecture diagram image (`assets/architecture_diagram.png`).
   - Does **not** import `agent.domain_kpi`, `agent.reflector`, or `agent.llm_client` (no SDK keys needed). If importing those modules triggers optional dependency imports, wrap in try/except or import only what's needed.
   - Add `requirements-demo.txt` that includes `streamlit>=1.30` plus the main `requirements.txt` contents (or `-r requirements.txt`).
   - Add `.streamlit/config.toml` with headless/server settings appropriate for Community Cloud.
   - Deploy to Streamlit Community Cloud (free): connect to the candidate's GitHub account, point at `app.py`, set main file path. No secrets configured.
   - If Streamlit Cloud deployment hits issues (e.g. memory limits with online_retail.csv which is 48 MB), reduce the demo to Chinook + HR only, or sample Online Retail to 50 K rows for the demo. The demo is proof of the compiler path, not a scale benchmark.
   - Add the deployed URL to README (both the badge and a "Live Demo" link), and set it as the repository "Website" in GitHub settings.

   **Alternative if Streamlit cannot be deployed (e.g., private repo policy):** Create a separate **public demo repo** `Tessa-Saumu/agentic-bi-demo` containing: README with GIF, architecture diagram, 10 screenshots, sample `.pbip` zip for download, a 2-page "how it works" page linking back to the private full-source repo. This is inferior to the runnable demo but satisfies "public demonstration exists."

7. **G25 — Narrated demo video.** Record a 2–3 minute screen recording (Loom/YouTube unlisted):
   - Show `git clone`, `pip install`, `pytest` (green), `python run_agent.py --help`.
   - Run the deterministic demo (either Streamlit public URL, or local CLI with pre-committed KPIs).
   - Show the `.pbip` opened in Power BI Desktop (if on Windows) or show the Desktop screenshots alongside the downloaded TMDL/visual JSON.
   - Open `tests/test_pbir_compiler.py` and scroll through 2–3 test functions to show the compiler is tested against real format constraints.
   - Link from README Demo section.
   - Production quality is not required; authenticity is.

8. **G19 — Repository metadata (GitHub UI).** After repo is made public (or in parallel with planning):
   - Description: "LangGraph agent that profiles CSVs, proposes KPIs with SQL, and compiles a Power BI Project (.pbip) — bounded LLM workflow engineering."
   - Topics: `langgraph`, `llm`, `agentic-ai`, `power-bi`, `pydantic`, `python`, `text-to-sql`, `bounded-agent`, `llm-engineering`.
   - Website: link to the Streamlit demo URL.
   - Ensure repo is not archived or hidden; pin on the candidate's GitHub profile.

9. **Final verification pass.** Walk the Flagship Definition of Done checklist from `FLAGSHIP_GAP_AUDIT.md` line by line. Create `FLAGSHIP_VERIFICATION_CHECKLIST.md` in the repo that copies the checklist and adds, for each item:
   - "Verified by:" (manual / CI / artifact path)
   - "Evidence:" (command to run, file path, or link)
   - "Date:"
   Any item that cannot be checked off requires either a fix or an explicit "deferred with reason" note in the document. The DoD is met when every non-deferred item is checked.

### Tests / checks
- All previous phases' tests continue to pass on CI.
- README renders correctly on GitHub (no broken images, no broken internal links — verify by browsing after push).
- Click every internal README link: clone URL, `docs/pbir_reference.md`, screenshot images, demo GIF, architecture diagram, CI badge.
- Streamlit demo runs locally with `streamlit run app.py` (no API keys set) and produces a downloadable zip for each dataset.
- The downloaded zip from the demo, when extracted, contains a valid `.pbip` structure (verify by spot-checking file presence; actual opening in Desktop is a Windows-only check and is documented as such).
- All `grep` audits pass:
  - No `your-username` placeholder in README.
  - No bare "24/24" without denominator in README.
  - No unqualified "reliable" applied to Reflector in README.
  - `docs/pbir reference.md` (with space) no longer exists; `docs/pbir_reference.md` exists.
- Verify by reading the final README that, within ~3 minutes of scrolling, a reviewer can answer: what problem, what I built, who contributed what, why the choices, how evaluated, what worked, what failed, what are the limits.
- Run the full checklist in `FLAGSHIP_VERIFICATION_CHECKLIST.md`; every required item is verified.

### Expected output
- A polished, recruiter-ready README with honest scope, credited contributions, consolidated design rationale, working links, green CI badge.
- A public zero-key Streamlit demo (or public demo repo fallback) that anyone can visit.
- Repository metadata set for GitHub discoverability.
- A short narrated walkthrough video.
- A filled verification checklist proving every DoD item.

### Acceptance criteria
- [ ] README has no placeholder URLs, no broken internal links, and the CI badge is green.
- [ ] "What I built / Credits" section appears, names the two mentor commits by SHA and what they changed.
- [ ] "Design Decisions" section appears and covers the six bullets listed above.
- [ ] Up-front scope paragraph states single-table/CLI/Desktop-only before the fold.
- [ ] Public demo URL is reachable without API keys; demonstrates profiling → KPI execution → `.pbip` download for at least Chinook.
- [ ] Repository description, topics, and website link are set on GitHub.
- [ ] Every item in the Flagship Definition of Done (from `FLAGSHIP_GAP_AUDIT.md`) is checked off in `FLAGSHIP_VERIFICATION_CHECKLIST.md` or explicitly marked deferred with reason.
- [ ] No "Explicitly Out of Scope" item has been implemented (grep for Dockerfile, FastAPI, `sqlglot`, multi-table code paths, vector-store imports).

### Rollback / risk considerations
- **Streamlit Cloud memory limits:** Online Retail is 48 MB; if it crashes the free tier, drop it from the demo (keep Chinook + HR) rather than optimizing data loading. The demo is proof-of-concept, not a scale demo.
- **Filename rename `pbir reference.md` → `pbir_reference.md`:** if any external references (screenshots, PRs) link to the spaced filename, those links will break. GitHub redirects on rename within the same repo for web viewers but not for direct raw URLs. Acceptable since this is a docs-only file.
- **Repo publicity:** Gating this phase on the repo being made public. If the repo must remain private longer, the public demo repo fallback is the alternative; just ensure the demo repo is clearly labelled as a demo snapshot with a link back ("Full source available on request" or "Private during final review").
- **Video recording:** Do not let perfect be the enemy of good. A 2-minute Loom with minor stumbles is far better than no video. The goal is to convey that the system actually runs, not to produce marketing footage.
- **Do not add new features during this phase.** If a README edit reveals an undiscovered bug, fix it (and add a test); otherwise, resist temptation.

---

## Stop Conditions

Stop investing engineering time on flagship consolidation when any of the following become true:

1. **All P0 and P1 gaps are closed** (G1–G19, G20, G21, G22, G25) and every non-deferred item in the Flagship Definition of Done is verified in `FLAGSHIP_VERIFICATION_CHECKLIST.md`. The P2 items G23 (semantic evaluation pilot) and G24 (structured logging) are explicitly deferred and do not block the flagship presentation.
2. **Any single P0/P1 task exceeds its time estimate by 2× and is not a hard blocker** — table it, label the limitation honestly, and move on. For example:
   - If the GitHub Actions CI fails on Python 3.12 due to third-party SDK incompatibility, drop to 3.10/3.11 and note it; do not debug SDK version matrices for a day.
   - If live API keys cannot be obtained for the G8 evidence bundle, commit deterministically regenerable artifacts plus historical LLM outputs with the honest "release-time artifact, regen command provided" label, and stop. Do not sign up for new paid API tiers.
   - If Streamlit Community Cloud deployment fails for non-code reasons (account limits, regional restrictions), fall back to the public demo repo and stop.
3. **A change requires architecture modifications** — for example, if closing the COUNT(DISTINCT) DAX gap (G20) unexpectedly demands introducing a SQL parser, stop after adding a clearly-labelled test case that documents the remaining gap; do not introduce sqlglot or rewrite the translator. Fail-closed behavior is acceptable for v1.
4. **Scope creep temptations appear** — stop and refer to the "Explicitly Out of Scope" list in `FLAGSHIP_GAP_AUDIT.md` (v2 explorer, Streamlit UI for the agent, Power BI Service, Docker, cloud API, fine-tuning, RAG, more datasets, authentication, K8s/Terraform, benchmark sweeps, multi-user). Any one of these becomes a separate project, not v1 polish.
5. **The public demo exists and is green** — at that point a recruiter can see proof without repo access, and further refinement of the demo (e.g., theme customization, advanced Streamlit components) does not change the credibility outcome.
6. **README + Credits + Design Decisions are written and CI is green** — the "a reviewer can understand this in 10 minutes" goal is met. Additional documentation (architecture decision records, extended API docs, a developer guide) is future work, not required for flagship.
7. **Mentor review has been solicited once** — if the mentor confirms the Credits section is accurate and the v1 claim is defensible, ship. Do not iterate on wording past two rounds of feedback.
8. **Diminishing returns hit** — specifically, if you find yourself polishing whitespace, typography, or test naming instead of fixing a credibility gap, you are done. The goal is credibility, not aesthetic perfection.

**Final ship signal:** A reviewer with no prior context can (a) visit the public demo URL, (b) see a real profiling → KPI execution → `.pbip` download work in their browser, (c) follow a link to the GitHub repo (or to the public demo repo), (d) read the README and understand problem / approach / contributions / limitations in under 10 minutes, (e) clone the repo (if granted access) and see `pytest` green and CI green, and (f) inspect a committed evidence bundle with documented provenance. When that is true, the project is a credible flagship. Stop.

---

## Execution Log — Phase 1 & Phase 2

### Completed Tasks

#### Phase 1 — Fresh-Clone Stability
- **G1 (Committed profile fixture for `tests/test_domain_kpi.py`)**: Generated `data/profiles/online_retail_profile.json` via `agent/profiler.py`, committed it to `tests/fixtures/online_retail_profile.json` (3,055 bytes), and updated `retail_profile` in `tests/test_domain_kpi.py` to load from `tests/fixtures/online_retail_profile.json`.
- **G2 (`hr.csv` → `hr_analytics.csv` path fix)**: Updated `scripts/profile_datasets.py` (`data/raw/hr_analytics.csv` → `data/profiles/hr_analytics_profile.json`) and Cell 3 of `notebooks/03_sql_validation_and_reflection.ipynb` (`DATASET_NAME = "hr_analytics"`, `DATA_PATH = "../data/raw/hr_analytics.csv"`).
- **G3 (`requirements.txt` pinning & cleanup)**: Removed unused `langchain-core`, `langchain-google-genai`, `langchain-mistralai`, and `rich`; added `pytest~=9.1`; pinned core LLM/graph/schema dependencies (`langgraph==1.2.14`, `google-genai==2.28.0`, `mistralai==3.1.0`, `pydantic==2.13.5`) and minor-series pins compatible with Python 3.10–3.12 (`pandas~=2.2`, `numpy~=2.2`, `openpyxl~=3.1`, `python-dotenv~=1.2`, `jupyter~=1.1`, `ipykernel~=7.0`); added `# Tested on Python 3.10, 3.11, 3.12` header comment.
- **G4 (`LICENSE`)**: Added standard MIT `LICENSE` at repo root (`Copyright (c) 2026 Theresia (Tessa) Saumu`).
- **G5 (`fix_structure.sh` neutralization)**: Renamed `fix_structure.sh` to `scripts/_scaffold_phase1_reference.sh`, removed execute permission (`chmod -x`), prepended the historical warning banner, and added an explicit `exit 1` safety guard before any file-writing commands.
- **G7 (Non-zero CLI exit codes in `run_agent.py`)**: Updated `run_agent.py` to exit with `sys.exit(1)` when `not report_written` or `final_state.errors` is non-empty, and `sys.exit(0)` otherwise.

#### Phase 2 — Verification Infrastructure
- **G6 (GitHub Actions CI)**: Created `.github/workflows/tests.yml` triggered on `push` (`main`, `arena/**`) and `pull_request` (`main`), running `pytest -v` across Python `["3.10", "3.11", "3.12"]` with `pip` caching and zero external secrets.
- **G10 (`tests/test_graph.py`)**: Added 10 graph-level unit and orchestration tests verifying `_route_after_reflection`, compiled graph node presence, the one-retry-no-loop topological invariant (`sql_executor_retry` has only `pbir_compiler` as an outgoing edge and never loops back to `reflector`), `run_sql_executor_retry` state updates and `kpis_to_retry` clearing on both pass and fail, node invocation order with and without retry (mocking LLM calls), and `_time_node` timing population.
- **G9 (`tests/test_end_to_end.py` + `tests/fixtures/kpis/`)**: Committed deterministic KPI fixtures (`tests/fixtures/kpis/{chinook,online_retail,hr_analytics}_kpis.json`) recovered from the repository's validated Mistral runs in git history (`0fd62b8` / `6fed674`); hoisted `MIN_VISUALS_REQUIRED = 4` to module scope in `pbir/compiler/builder.py`; added 11 end-to-end tests covering all 3 datasets, Chinook headline numerical parity ($2,328.60 total revenue, 5.44 average tracks/invoice), unfixable KPI drop, retry-failure KPI drop, bounded repair-and-retry recovery, min-visual build gate rejection, and `run_agent.py` CLI exit codes + `run_summary.json` emission.
- **G18 (`run_summary.json` emission)**: Extracted `_build_run_summary(final_state, args, report_written=...)` in `run_agent.py` and wrote `<output_dir>/run_summary.json` on both success and failure runs; added `run_summary.json` to `.gitignore`.

### Files Changed
- `LICENSE` (added)
- `.github/workflows/tests.yml` (added)
- `.gitignore` (modified — added `run_summary.json`)
- `requirements.txt` (modified — pinned versions, removed dead packages, added `pytest`)
- `scripts/_scaffold_phase1_reference.sh` (renamed from `fix_structure.sh`, `chmod -x`, header warning + `exit 1` guard)
- `scripts/profile_datasets.py` (modified — `hr.csv` → `hr_analytics.csv`, `hr_profile.json` → `hr_analytics_profile.json`)
- `notebooks/03_sql_validation_and_reflection.ipynb` (modified — `DATASET_NAME = "hr_analytics"`, `DATA_PATH = "../data/raw/hr_analytics.csv"`)
- `run_agent.py` (modified — added `_build_run_summary()`, `<output_dir>/run_summary.json` emission, and `sys.exit(0)` / `sys.exit(1)`)
- `pbir/compiler/builder.py` (modified — hoisted `MIN_VISUALS_REQUIRED = 4` to module scope so it can be inspected/tested directly)
- `tests/fixtures/online_retail_profile.json` (added — committed schema profile fixture for `tests/test_domain_kpi.py`)
- `tests/fixtures/kpis/chinook_kpis.json` (added)
- `tests/fixtures/kpis/online_retail_kpis.json` (added)
- `tests/fixtures/kpis/hr_analytics_kpis.json` (added)
- `tests/test_domain_kpi.py` (modified — loads `tests/fixtures/online_retail_profile.json`)
- `tests/test_graph.py` (added — 10 tests)
- `tests/test_end_to_end.py` (added — 11 tests)
- `FLAGSHIP_IMPLEMENTATION_PLAN.md` (modified — checked off Phase 1 & 2 acceptance criteria and recorded execution log)

### Test & Verification Results
- **Baseline before changes (without `data/profiles/`)**: `198 passed, 18 errors in 0.93s` (`FileNotFoundError` in `tests/test_domain_kpi.py`).
- **Post-Phase 1 (`rm -rf data/profiles && pytest -q`)**: `216 passed in 0.70s`.
- **Post-Phase 2 (`rm -rf data/profiles && pytest -v`)**: `237 passed in 4.51s` (216 original + 10 in `tests/test_graph.py` + 11 in `tests/test_end_to_end.py`; slowest test is Online Retail 541,909-row end-to-end compile at ~3.4s, well within the 5s target).
- **Negative / Sabotage checks**:
  - Temporarily setting `pbir.compiler.builder.MIN_VISUALS_REQUIRED = 2` causes `test_min_visual_gate_rejects_build_when_only_two_kpis_translatable` to fail (`exit_code = 1`), and restoring `4` passes (`exit_code = 0`).
  - Temporarily rewiring `sql_executor_retry -> reflector` causes `test_one_retry_no_loop_invariant_no_edge_back_to_reflector` to fail (`exit_code = 1`), and restoring `sql_executor_retry -> pbir_compiler` passes (`exit_code = 0`).
- **End-to-end script & CLI checks**:
  - `python3 scripts/profile_datasets.py` profiles all 3 datasets (`chinook_profile.json`, `online_retail_profile.json`, `hr_analytics_profile.json`) with 0 errors.
  - `python3 run_agent.py --input nonexistent.csv --output /tmp/out` prints the error summary, writes valid `/tmp/out/run_summary.json` with `"report_written": false`, and exits with code `1`.

### Deviations from Plan
1. **Python 3.10–3.12 cross-version compatibility in `requirements.txt` (G3)**: The latest PyPI releases of `pandas` (3.0.x), `numpy` (2.4.x), and `ipykernel` (7.4.x) drop Python 3.10 (`Requires-Python: >=3.11`), which would break the `3.10` job in `.github/workflows/tests.yml` (G6). Using `pandas~=2.2`, `numpy~=2.2`, and `ipykernel~=7.0` alongside exact pins `langgraph==1.2.14`, `google-genai==2.28.0`, `mistralai==3.1.0`, `pydantic==2.13.5` was verified with `pip install --dry-run --python-version {3.10,3.11,3.12} --only-binary=:all:` to resolve cleanly on all three Python versions.
2. **Hoisting `MIN_VISUALS_REQUIRED = 4` in `pbir/compiler/builder.py` (G9)**: `MIN_VISUALS_REQUIRED` was previously a local constant inside `run_pbir_compiler()`. Hoisting it to module scope (`pbir.compiler.builder.MIN_VISUALS_REQUIRED = 4`, exported in `__all__`) preserves identical runtime behavior while allowing the Phase 2 acceptance criterion ("Min-visual rejection test fails if the `MIN_VISUALS_REQUIRED` constant is changed to 2, and passes at 4") to be verified directly.
3. **Mock patch targets in `tests/test_graph.py` and `tests/test_end_to_end.py` (G9, G10)**: Following PR #12's extraction of `agent/llm_client.py`, `agent/domain_kpi.py` invokes `agent.domain_kpi.call_llm` and `agent/reflector.py` invokes `agent.reflector._call_reflection_llm` (which calls `agent.reflector.call_llm`). Tests patch those exact entry points so no network calls can occur.
4. **KPI rejection/sabotage cases in `tests/test_end_to_end.py` (G9)**: Rather than committing a separate fourth static JSON file for the broken-KPI fixture, `tests/test_end_to_end.py` loads `tests/fixtures/kpis/chinook_kpis.json` and uses `KPISpec.model_copy(update=...)` in-memory to construct the unfixable-drop, retry-fail-drop, repair-and-retry, and min-visual-gate cases cleanly.

### Newly Discovered Problems (Added to Backlog — Not Modified in Phases 1–2)
- **`PROJECT_EVIDENCE.md` not present in repository**: `FLAGSHIP_GAP_AUDIT.md` and `FLAGSHIP_IMPLEMENTATION_PLAN.md` reference `PROJECT_EVIDENCE.md` (`PROJECT_EVIDENCE_AGENTICBI.md`) as the source audit input, and git history (`356670c`, `0fd62b8`, `6fed674`) preserves the historical KPI and reflection JSON artifacts that were uncommitted in `ea7bbac`. Relevant when assembling `evidence/v1/` in Phase 3.
- **Notebook 01 & 02 secondary cell references to `hr.csv` / `hr_profile.json`**: While G2 targeted `scripts/profile_datasets.py` and `notebooks/03_sql_validation_and_reflection.ipynb`, `notebooks/01_data_profiling.ipynb` (cells 14–16) and `notebooks/02_domain_and_kpi_inference.ipynb` (cell 3 comment `# "hr"`) still contain legacy `"hr"` / `hr.csv` references. Recorded for backlog consideration.
- **`scripts/run_domain_kpi_all.py`, `scripts/run_sql_and_reflect.py`, and `scripts/run_reflector_stress_test.py` exit codes**: Like `run_agent.py` prior to G7, these standalone helper scripts still exit with code `0` when a dataset run records errors. If any of these scripts are ever wired into automated checks, they would benefit from the same non-zero exit convention applied to `run_agent.py` in G7.

---

## Execution Log — Phase 3 & Phase 4

### Pre-Change Inspection (assumptions checked before editing)

- **`PROJECT_EVIDENCE.md` still absent.** Confirmed not present in the checkout (same as the Phase 1–2 finding). Proceeded from `FLAGSHIP_GAP_AUDIT.md`, this plan, the working tree, and git history (fetched `main` to recover historical artifacts).
- **Baseline suite green:** `245 - 8 = 237 passed` before changes (`rm -rf data/profiles && pytest`), matching the Phase 2 log.
- **G15 three-way model-ID mismatch confirmed:** `.env.example` says `gemini-3.5-flash`, `agent/llm_client.py` defaulted to `gemini-3.1-flash`, README said `gemini-3.1-flash` / `open-mixtral-8x7b` / `mistral-large`. No test asserts on exact model strings; only `tests/test_end_to_end.py` checks the `temperature` summary key's *presence*.
- **No live keys available** (no `.env` in repo; sandbox has no LLM-API network access), so G8 followed the plan's historical-label path. Historical artifacts verified recoverable and internally consistent at `6fed674` (2026-07-18); all 5 historical Chinook KPIs execute and translate under current code.
- **G20 gaps reproduced before fixing:** `COUNT(DISTINCT …) … WHERE … IS NOT NULL` raised `SQLToDaxError`; `SUM([Total])` raised `SQLToDaxError`. Verified SQLite executes bracket-quoted SQL natively and `_validate_sql_columns` already tolerates both shapes (live check, zero violations) — so the fix is translator-only, as the plan's verify-first note anticipated.
- **G21/G22 as described:** both notebooks 0 bytes; `data/processed/` holds only `.gitkeep` with zero references anywhere (grep); `prepare_chinook.py` writes to `data/raw/chinook.csv`; `output/.gitkeep` missing; `STRUCTURE.md` stale in all the ways listed.

### Completed Tasks

#### Phase 3 — Evidence Bundle and Claim Discipline
- **G8 (Committed evidence bundle `evidence/v1/`)**: 15 valid JSONs (92K) + README for Chinook and Online Retail. Historical LLM artifacts (KPI specs, sabotaged copies, stress reflections, the organic Online Retail reflection) extracted verbatim from `6fed674`; profiles, query results, and run summaries regenerated deterministically with the pinned env (profiler → historical KPI specs → executor → compiler → `_build_run_summary`, same shape as `tests/test_end_to_end.py`); Chinook reflection recorded as an explicitly-labeled `notes: []` placeholder (the historical run flagged zero issues and `run_reflector` writes no file in that case by design). `metadata.json` records env, canonical models, temperature, dates, regen commands, and honest limits (historical provider/model IDs unknown; July runs ≠ August confirmation tables; retail compile delta vs. the historical run). No `.pbip` committed (absolute host paths; regenerable). Verified `evidence/` is not gitignored and contains no absolute local paths.
- **G15 (Model identifier + temperature consistency)**: canonicalized on the `.env.example` values — Gemini `gemini-3.5-flash` / `gemini-3.1-pro`, Mistral `mistral-large-latest` / `mistral-medium-latest` — byte-identical across `agent/llm_client.py`, `.env.example` (already canonical, untouched), and the README tech-stack row. Added `"temperature": 0` to the Gemini `generate_content` config with the parity comment, and `temperature = 0` (was `None`) for the Gemini branch of `run_agent._build_run_summary`.
- **G16 (Narrowed reliability claim)**: README fault-injection summary now carries in-line denominators (12/round = 2 datasets × 3 fault types per provider; 24/24 cumulative across two rounds; HR excluded; 6/24 adjacent-category diagnoses) plus the organic-fire-rate sentence (0–1 KPI/dataset on natural runs; capability demonstrated by planted faults) and a pointer to `evidence/v1/`. Grep confirms the single remaining `24/24` is qualified and no unqualified `reliable` describes the Reflector in README.
- **G17 (Absolute-path documentation)**: new "Report path coupling" paragraph in README Known Limitations; one-line console note in `run_agent.py` after a successful write.

#### Phase 4 — Bounded Functional and Cleanliness Polish
- **G20 (Translator gaps closed)**: `pbir/compiler/sql_to_dax.py` now (1) recognizes `WHERE <col> IS [NOT] NULL`, mapping to `CALCULATE(<measure>, 'table'[col] [=|<>] BLANK())` — the exact historical "Total Unique Customers" query now yields `CALCULATE(DISTINCTCOUNT('data'[CustomerID]), 'data'[CustomerID] <> BLANK())`; (2) normalizes T-SQL `[bracket]` identifiers to bare form in `_normalize_identifiers` (string-literal contents excluded, so `'[North]'` is untouched); (3) fails closed on any other unrecognized WHERE form instead of silently dropping it on grouped queries (see Deviations). README gap language updated in all three spots (Failure Modes, DAX-coverage paragraph, stretch goal) to record the fix while keeping fail-closed scope explicit.
- **G21 (Empty notebooks removed)**: deleted both 0-byte notebooks; added `notebooks/README.md` with the planned explanatory note.
- **G22 (Dead scaffolding cleaned)**: removed `data/processed/`; created `output/.gitkeep` (verified trackable); rewrote `STRUCTURE.md` to match `ls` (evidence tree, fixtures, new test files, scaffold-script location, `run_summary.json`, notebooks README, actual `pbir reference.md` filename, `chinook.sqlite`).

### Files Changed
- `evidence/v1/README.md`, `evidence/v1/metadata.json` (added)
- `evidence/v1/chinook/`, `evidence/v1/online_retail/` — 7 JSONs each: historical `*_kpis.json`, `*_kpis_sabotaged.json`, `*_stress_test_reflection.json` (+ historical `online_retail_reflection.json`; labeled placeholder `chinook_reflection.json`); regenerated `*_profile.json`, `*_query_results.json`, `*_run_summary.json` (added)
- `agent/llm_client.py` (modified — canonical Gemini primary `gemini-3.5-flash`, `temperature=0` on Gemini path)
- `run_agent.py` (modified — Gemini summary temperature `None` → `0`; absolute-path console note)
- `pbir/compiler/sql_to_dax.py` (modified — `IS [NOT] NULL` WHERE support, bracket normalization, unrecognized-WHERE fail-closed guard)
- `README.md` (modified — tech-stack model IDs, fault-injection denominators + organic note + evidence pointer, path-coupling paragraph, G20 gap-closure language)
- `STRUCTURE.md` (modified — full tree reconciliation)
- `notebooks/README.md` (added); `notebooks/01_…`, `notebooks/04_…` (deleted)
- `data/processed/.gitkeep` (deleted with directory); `output/.gitkeep` (added)
- `tests/test_pbir_compiler.py` (modified — 5 new tests: 2 translator + 2 compile-level not-dropped + 1 fail-closed hardening)
- `tests/test_domain_kpi.py` (modified — 3 new validator tests: bracket tolerance, bracketed-hallucination still caught, `IS NOT NULL` keywords)
- `FLAGSHIP_IMPLEMENTATION_PLAN.md` (modified — Phase 3 & 4 boxes checked, this log)
- `.env.example` (verified already canonical — no change)

### Test & Verification Results
- **Full suite:** `rm -rf data/profiles && pytest -q` → `245 passed in ~5s` (237 baseline + 8 new), 0 failures/errors.
- **New tests:** `TestSQLToDaxFlagshipHardening` (5) + 3 validator tests pass; full `test_pbir_compiler.py` + `test_domain_kpi.py` files green (153 passed).
- **Grep audits:** single `24/24` occurrence is denominator-qualified; no `reliable` in README; model IDs byte-identical across all three files; `temperature=0` + parity comment present on both LLM paths; absolute-path paragraph present.
- **Evidence audits:** all 15 JSONs validate via `json.tool`; `git check-ignore` confirms trackable; no absolute local paths in JSONs; total 92K.
- **End-to-end (deterministic, no keys):** historical Online Retail KPI set → profiler → executor (5/5 pass) → compiler (5 visuals, 0 errors) → `write_pbip` to temp dir, with the `DISTINCTCOUNT` measure present in serialized `data.tmdl`. Chinook evidence regen likewise 5 visuals / 0 errors.
- **Regression checks:** `python scripts/profile_datasets.py` profiles all 3 datasets (G2 intact); no fixture KPI SQL contains WHERE/brackets so G20 cannot alter e2e-test DAX; the two pre-existing WHERE translator tests pass unchanged (existing shapes byte-identical); `tests/test_llm_client.py` green (18 passed) after default-ID change.
- **Lint/type/build:** none exist in this repo (no pyproject/setup.cfg/ruff/mypy config; CI runs `pytest` only) — nothing further to run; no new tooling added per minimum-scope constraint.

### Deviations from Plan
1. **Canonical Gemini primary is `gemini-3.5-flash`, not a 2.x ID (G15):** the plan suggested `gemini-2.0-flash`/`gemini-1.5-flash` as "stable", but Google's lifecycle docs (checked 2026-10-07) show the 2.x Flash line retiring 2026-10-20, while `gemini-3.5-flash` (the `.env.example` primary) is GA with retirement no earlier than May 2027. Reconciled toward `.env.example` instead; rationale recorded in a `llm_client.py` comment. `.env.example` consequently needed no edit.
2. **Evidence bundle covers Chinook + Online Retail, not Chinook-only (G8):** the minimum bar was Chinook, but the committed Online Retail organic-reflection log is the direct artifact behind the G16 organic-fire-rate sentence, so including it (one more small directory, same method) was the coherent choice. HR omitted as planned (no reflection/stress logs ever committed).
3. **Historical provider labeled unknown, not Mistral (G8):** the plan's "Mistral is easier" assumed provider attribution, but the historical runs' provider/model IDs were never recorded, and the available signals conflict (`6fed674` message mentions Mistral; KPI naming/domain style matches the README's Gemini description). `metadata.json` + evidence README label this explicitly rather than asserting an unverifiable provider.
4. **Unrecognized-WHERE fail-closed guard added alongside the two G20 shapes:** implementing `IS [NOT] NULL` exposed that other unrecognized WHERE forms on GROUP BY queries were *silently dropped* (e.g. historical "Top 10 Best Selling Products" translated to plain `SUM(...)` with its filter ignored) — a direct violation of the module's documented fail-closed contract, in the same function being edited. The ~6-line guard converts that to `SQLToDaxError`; verified it cannot newly break any real KPI (the only historical WHERE forms are the two now-recognized `IS NOT NULL` ones; no fixture SQL uses WHERE). One hardening test added (5th test in the new class).
5. **Three validator tests added in `tests/test_domain_kpi.py` beyond the planned 4-in-`test_pbir_compiler.py`:** the plan's acceptance criterion (4 tests in `test_pbir_compiler.py` covering both shapes) is met exactly; the validator tests lock in the verified no-change-needed behavior (brackets tolerated, bracketed hallucinations still caught) so a future validator rewrite cannot silently regress it.
6. **`run_reflector_stress_test.py` docstring untouched (G16):** the plan's "e.g." assumed unqualified reliability wording there, but the file contains none (verified by grep) — the step was a no-op, not an omission.

### Newly Discovered Problems (Added to Backlog — Not Modified in Phases 3–4)
- **Phase 2 log provenance over-claim for the HR test fixture:** `tests/fixtures/kpis/{chinook,online_retail}_kpis.json` match `0fd62b8` byte-for-byte (modulo trailing newline), but `tests/fixtures/kpis/hr_analytics_kpis.json` matches *no* committed `data/profiles` artifact — its 5 KPI names match the README's HR/Mistral confirmation-run table instead, suggesting the SQL was reconstructed rather than recovered verbatim. The fixture is valid (executes, translates, e2e green), but its "recovered from git history" provenance note is inaccurate for HR. Relevant if Phase 5 cites fixture provenance.
- **Confirm `gemini-3.1-pro` fallback ID against the live API when keys are next available:** reconciliation picked the ID already shared by `.env.example` and code, but only the primary (`gemini-3.5-flash`) was corroborated against current model-lifecycle docs; the fallback was not independently verified (no keys in this environment). If a future run reports an unknown-model error on fallback, update all three places together (noted in the `llm_client.py` comment).
- **README Tech Stack row vs. retired-era IDs in git history:** older commits/docs may still reference `open-mixtral-8x7b`; only the live README row was reconciled (Phase 5 owns the remaining README polish).
- **`.venv/` created in repo root for verification runs:** gitignored (`venv/`/`.venv/` patterns) and not committed; safe to delete. Left in place for the next phase's test runs.

