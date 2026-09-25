# Project Evidence — Agentic BI Builder

Forensic documentation of what this repository actually demonstrates. Compiled 2026-09-25 from a fresh checkout of `Tessa-Saumu/Agentic-BI-Builder` @ `764883a` (main), GitHub PR/issue history via `gh`, and hands-on verification performed in this session (test runs, pipeline execution). No code was modified for this document; verification scripts were run outside the repo tree and gitignored outputs were regenerated locally only.

Evidence tags used below:
- **[VERIFIED]** — confirmed directly in this checkout during this audit.
- **[DOCUMENTED]** — claimed in README/PR/issue text, consistent with code, but not independently reproducible from the tree alone (usually because it needs live API keys or Power BI Desktop).
- **[PARTIAL]** — implemented but incomplete, or verified only in part.
- **[BROKEN]** — demonstrably does not work as claimed on a fresh checkout.
- **[UNDETERMINABLE]** — cannot be established from available evidence.

---

## Context

**When:**
June 3 – August 30, 2026. First commit `c835743` "Initial commit" (2026-06-03); last commit `764883a` "Merge pull request #14 from Tessa-Saumu/final-polish" (2026-08-30); annotated release `v1.0.0` published 2026-08-30 00:58 UTC. Development span across GitHub (commit dates + PR merge dates `gh api`), not the README's claim of "June/July 2026" — the README understates by one month of polish/validation work. 126 commits total on remote main (this local clone was provided shallow, containing only the merge commit; full history retrieved via GitHub API).

**Why it existed:**
Evidence points to a mentored portfolio/skill-building project, not a product with users. Supporting evidence:
- `docs/Project Description.md` reads as a scoped brief (Objectives, Deliverables 1–8, Technical Constraints, Out of Scope) written before implementation (commit `ec1b8b2`, 2026-06-03, "Add project description").
- GitHub milestones structure the work as "Phase 1 — Foundation" through "Phase 5 — Polish" (issues #1–#7).
- PR #10: provider choice (Mistral instead of Anthropic/OpenAI) made "per prior discussion with @Mikehade … to stay on free tiers"; README repeats "confirmed with the mentor before implementation".
- PR #14: "the merge itself is done by the mentor rather than by me" and a reference to "the process on a prior project" for tagging — implies an ongoing mentorship program with a prior project existing (the referenced `tests/test_risk_metrics.py` precedent in PR #10 confirms a prior "FRM" project; it is not in this repo).
**No external sponsorship, client, employer, or user is referenced anywhere in the repository. [VERIFIED by absence]**

**Solo / team:**
Solo implementation with one reviewer/meritor contributor. GitHub contributors API: `Tessa-Saumu` 117 commits, `Mikehade` (Adeyeri Michael) 9. Of Michael's 9: 7 are PR merges, 2 are substantive ("update" `55578ac` and `cca0106` — see *What I personally built* for what those touched). No other accounts appear in commits, issues, or comments. [VERIFIED via gh api]

**My role:**
All implementation commits, all issue bodies, all PR bodies, and review-response comments are authored by `Tessa-Saumu` / "Theresia (Tessa) Saumu" (GitHub account `Tessa-Saumu`, commit author email `theresia.saumu@gmail.com`). Design, implementation, testing, validation runs, documentation, and stress-test tooling: all attributable to that account. Review, merging, release tagging, and two small hardening/scaffold commits are attributable to `Mikehade`. **What I personally did** can be proven only to the GitHub-account level, not to a natural person — the repository cannot prove the account operator's identity; if you are Tessa Saumu, authorship maps to you consistently. [PARTIAL — account-level attribution is airtight, human-level is not something a repo can prove]

---

## Problem

**What problem was actually being solved?**

The repetitive setup phase of starting a Power BI dashboard from a raw dataset: schema inspection, deciding which metrics matter, writing aggregation SQL, and manually wiring results into a report layout. The implemented system automates exactly this: CSV/SQLite in → deterministic profiling → LLM domain inference + 5 KPI proposals with SQL → real SQL execution → LLM self-review with bounded repair → compiled `.pbip` Power BI Project out, generated programmatically from reverse-engineered PBIR/TMDL formats.

**Real implemented problem vs. aspirational README language:**
This README is unusually well-aligned with the code — the claims in `README.md` map 1:1 to modules (`agent/profiler.py`, `agent/domain_kpi.py`, `agent/sql_executor.py`, `agent/reflector.py`, `pbir/compiler/*`, `run_agent.py`). The aspirational framing is confined to the opening ("explores whether a LangGraph-based agentic system can automate that entire setup phase") and it is honestly hedged. The originally-scoped-but-descoped items are explicitly labeled as such: auto-date tables (promised in PR #8's design decisions, descoped per PR #12 "intentional descoping of relationships, hierarchies, and multi-table support"), multi-table joins, Streamlit UI, Power BI Service publishing (all in `docs/Project Description.md` "Out of Scope" and README "Known Limitations"). No file, metric, or integration is referenced in the README that does not exist.
The one gap between claim and current tree: README result tables cite `data/profiles/*` artifacts (profiles, KPIs, reflection logs, stress-test outputs) that **were committed during development but deliberately removed and gitignored** in commit `356670c` (2026-07-23) — so those results are no longer inspectable in the checkout (see *Current repository status*).

---

## What I personally built

All ownership attribution below is by commit authorship (`git`/`gh api` evidence). [VERIFIED unless noted]

**Confirmed ownership — authored by Tessa-Saumu (implementation):**

| Component | Files | Notes |
|---|---|---|
| LangGraph pipeline graph | `agent/graph.py` | 6 nodes, conditional retry edge, `time_node()` timing wrapper (commit `12aeb94`) |
| Typed agent state | `agent/state.py`, `agent/models.py` | `AgentState`, `DataProfile`, `ColumnProfile`, `DomainHypothesis`, `KPISpec`, `DomainKPIResponse`, `QueryResult`, `ReflectionNote` (5 issue types), `ReflectionResponse` |
| Profiler node | `agent/profiler.py` | CSV + SQLite loading, per-column dtype/null/distinct/min-max/samples, edge cases |
| Domain/KPI node | `agent/domain_kpi.py` | Metadata-only prompt builder, SQLite dialect constraints, regex lexical SQL-column validator with one-shot LLM repair pass (commit `67838a2`…) |
| SQL Executor + retry node | `agent/sql_executor.py` | In-memory SQLite exec, per-KPI error capture, `rerun_single_kpi`, `run_sql_executor_retry` with drop semantics (commits `71bd977`, `38772f0`) |
| Reflector node | `agent/reflector.py` | Reflection prompt, single-call review, fix application + `kpis_to_retry` handoff to graph-level routing, audit JSON logging |
| Shared LLM client | `agent/llm_client.py` | Gemini/Mistral provider dispatch, native structured output, primary+fallback model chain, retry-with-backoff, mistralai v1/v2 import compat (extracted from domain_kpi in PR #11) |
| PBIR format reverse-engineering | `docs/pbir reference.md` (1,129 lines), `output/reference_report/*` (hand-authored minimal .pbip), `assets/` | PR #8; the reference `.pbip` was created in Power BI Desktop and inspected, not generated |
| PBIR models | `pbir/models/` (9 files) | Typed Pydantic models for the PBIR layout |
| PBIR compiler | `pbir/compiler/builder.py`, `sql_to_dax.py` (1,041 lines), `layout.py`, `m_query.py`, `templates.py`, `tmdl.py`, `visual_json.py`, `serialiser.py` | SQL→DAX shape matching, page grouping/canvas layout, Power Query M partition builder, TMDL writer, `.pbip` folder serialisation; module split per PR #12 (commits `88ad04a`, `ca3227b`) |
| CLI entry point | `run_agent.py` | argparse, dotenv loading (fix `f8c1979`), state rehydration, artifact writing, timing/reflection summary |
| Validation scripts | `scripts/profile_datasets.py`, `run_domain_kpi_all.py`, `run_sql_reflector_all.py`, `run_pbir_compiler_all.py`, `run_reflector_stress_test.py` (fault injection), `prepare_chinook.py` (grain-correct SQLite→CSV join) | PRs #9–#13 |
| Test suite | `tests/` (7 files, 216 tests) | Profiler 7, domain_kpi 26, llm_client 18, reflector 17, sql_executor 12, pbir_compiler 119, prepare_chinook 17 |
| Notebooks | `notebooks/02_kpi_proposal_review.ipynb`, `03_sql_validation_and_reflection.ipynb` | Real executed outputs; notebooks 01 and 04 are **empty placeholders** [VERIFIED: 0 bytes] |
| Documentation/polish | `README.md` (318 lines), `STRUCTURE.md`, `assets/architecture_diagram.png`, `assets/demo.gif` (~5 MB), 10 Power BI Desktop screenshots | PR #14 (commits `ec27b7a`, `3afcc4c`, `764883a` era) |
| Project brief & issue/PR authoring | `docs/Project Description.md`, issues #1–#7, PRs #8–#14 bodies | All PR bodies authored by Tessa-Saumu; review-response comments on issues #1–#2 by Tessa-Saumu |

**Unclear / shared ownership:**
- **Mentor code commits:** `cca0106` ("update", Michael Adeyeri, 2026-07-13) is a *substantive* hardening patch present in current code: adds KPI-name uniqueness validation to `DomainKPIResponse` and `run_reflector`, adds the unknown-KPI-note filtering in `run_reflector`, fixes the "no issues found across 0 KPIs" logging bug (new `reviewed_kpi_count` param — visible as the `33930d4` follow-up by Tessa), and updates tests. `55578ac` (2026-06-15) touched environment/scaffold setup files. **Do not claim these specific hardening functions as personally authored** if challenged; the surrounding modules, their tests, and their evolution are Tessa's. [VERIFIED via commit patches]
- Whether issue/PR *review feedback* was given by Mikehade elsewhere (offline, or via GitHub review UI) is **[UNDETERMINABLE]** — the PR `reviews` and PR `comments` APIs return empty; only issue comments (by Tessa herself, some responding to "review") exist. Issue #2 comment "Addressed all three points from review" proves reviews happened; their venue is not in GitHub-visible data.
- The identity of the mentor relationship (professional program vs. personal arrangement) is **[UNDETERMINABLE]** from the repo.

---

## Architecture

The actual implemented system (all [VERIFIED] by reading code and running it, except the Power BI Desktop end, see below):

**Frontend:**
None. CLI only (`run_agent.py`, argparse `--input` / `--output`). Streamlit UI was scoped as a stretch goal and not implemented (documented as such in README and Project Description — an honest descope, not a gap between claim and code).

**Backend:**
Python process, no server. Orchestration is a LangGraph `StateGraph` over the typed `AgentState` (`agent/graph.py`): `profiler → domain_kpi → sql_executor → reflector → (conditional: sql_executor_retry | skip) → pbir_compiler`. Every node is wrapped by `time_node()` writing `state.node_timings`. The key architectural decision — the "one retry per flagged KPI" policy — is enforced **topologically** (the retry node has a single outgoing edge to the compiler; no path back to the reflector), not by a state counter; this is implemented exactly as documented and is genuinely visible in `graph.py` lines 59–72.
LLM access is isolated in `agent/llm_client.py`: provider dispatch via `LLM_PROVIDER` env var (`gemini`/`mistral`), per-provider primary + fallback model chain, transient-error retry with exponential backoff (2s/4s/8s, markers `503/429/unavailable/overloaded/rate limit/resource_exhausted`), non-transient errors raised immediately. Structured output is provider-native (Gemini `response_schema`, Mistral `chat.parse(response_format=…)`) — **no LangChain runtime dependency is used by the code** even though `langchain-core`, `langchain-google-genai`, and `langchain-mistralai` sit in `requirements.txt` (grep confirms zero imports of them; dead dependencies).

**Data:**
Static CSV/SQLite inputs in `data/raw/` (3 datasets, committed). LLM sees **metadata only** at KPI-generation time: `_profile_to_prompt_context()` deliberately strips `sample_values`/`min`/`max` so inference runs on schema, not data values (`agent/domain_kpi.py`, and enforced by `test_domain_kpi.py::TestPromptContext::test_excludes_sample_values`). The Reflector prompt does include up to 10 sampled result rows per KPI (`MAX_ROWS_IN_PROMPT`, `agent/reflector.py`) — by design; the "metadata-only" guarantee applies to Domain/KPI, not to reflection. Query results are stored capped (`MAX_RESULT_ROWS_STORED = 20`). No database persists anything: SQL executes against a fresh in-memory SQLite DB loaded via `DataFrame.to_sql` (`agent/sql_executor.py::_build_in_memory_db`, table name `data`).

**ML/AI:**
No trained models. This is an agentic LLM pipeline: two LLM touchpoints (domain/KPI proposal, reflection review), each a single structured-output call with deterministic pre/post validation:
1. `run_domain_kpi`: one call returns `DomainKPIResponse` (domain hypothesis + exactly-5 `KPISpec`); a **regex/lexical column validator** (`_validate_sql_columns`) rejects hallucinated columns against the real profile, with one bounded repair re-prompt; unresolved violations land in `state.errors`.
2. `run_sql_executor`: real execution; empty result = pass, execution error = captured per-KPI "fail", never a crash.
3. `run_reflector`: one call reviews all KPIs+results, emits `ReflectionNote`s (5-category taxonomy incl. deliberate `other` catch-all); fixes are applied to `KPISpec.sql_query`, flagged KPIs routed to the retry executor via graph edge; unfixable/failed-retry KPIs are **dropped**, not shipped broken.
4. `run_pbir_compiler` → `write_pbip`: validated KPIs become DAX measures via a deliberately narrow **regex-based SQL→DAX translator** (`pbir/compiler/sql_to_dax.py`, 5 supported SQL shapes; anything else raises `SQLToDaxError` and the KPI is skipped with an error entry rather than guessed); a build gate rejects the report below 4 translatable visuals (`MIN_VISUALS_REQUIRED`, `builder.py`) so thin dashboards don't ship silently.

**Database:**
None persistent. SQLite is used twice as an execution tool only: reading `chinook.sqlite` input, and the transient in-memory DB for KPI execution.

**Infrastructure:**
None. No CI/CD (`.github/` absent — [VERIFIED]), no Dockerfile, no deployment config, no package build (no `pyproject.toml`/`setup.py`), no cloud services. Runs as a local script; the output artifact is a `.pbip` folder meant to be opened on the same machine in Power BI Desktop (Windows). Note the compiler embeds the **absolute** path of the source CSV into the Power Query M partition (`File.Contents("/…/chinook.csv")`, verified in a generated `.tmdl` during this audit) — reports are machine-local by construction; documented in README as the Power BI Service refresh limitation context, though the path-coupling consequence for moving reports to another machine is not spelled out.

**Major control flow (end-to-end, verified in this session except the two LLM calls):**
`run_agent.py` builds graph → Profiler loads CSV, emits `DataProfile` → Domain/KPI LLM call returns domain + 5 SQL KPIs, validated for column existence → SQL Executor runs all 5 against in-memory SQLite → Reflector LLM call reviews everything, applies fixes to flagged KPIs → conditional edge: retry executor re-runs only flagged KPIs once, drops still-failing ones → PBIR Compiler translates SQL→DAX, buckets visuals onto pages (3 cards/page, 2 charts/page), builds `PBIRProject` → `write_pbip` emits `<name>.Report/` (JSON: report/pages/visuals + copied theme assets) and `<name>.SemanticModel/` (TMDL: database/model/table files containing columns, DAX measures, and the M partition script).

---

## ML / AI work

This is an LLM-engineering/agent project, not a modelling project. Framing it as "ML" would overstate; the honest formulation and evidence:

**Problem formulation:**
*implemented and verified* — conditional structured generation: given a deterministic schema profile, generate constrained structured JSON (domain + 5 KPI specs) validated post-hoc against ground-truth schema; then self-critique executed results with bounded repair. The formulation is cleanly implemented (deterministic validation of stochastic output is the core pattern, present in `domain_kpi.py` and `sql_executor.py`/`reflector.py`).

**Target:**
*not applicable in the supervised sense* — no labels were defined. The implicit targets: (a) KPI SQL references real columns (hard, checkable), (b) SQL executes (hard, checkable), (c) results are semantically sensible (soft, LLM-judged by the Reflector). There is no ground-truth KPI set, no human-rated quality rubric, no task metric defined anywhere in code or docs. [VERIFIED by absence]

**Features:**
*implemented and verified* — `DataProfile`: per-column inferred dtype, null count/rate, distinct count, min/max, sample values; metadata-only projection for the LLM prompt. Covered by `test_profiler.py` (7 tests) and the prompt-context tests. No feature *learning* — this is schema description.

**Baseline:**
*absent* — no comparison against a simpler non-agentic approach (e.g., fixed template + auto-stats, or text-to-SQL without the reflection loop). The README's own "organic runs found nothing to flag" finding is honest but there is no ablation showing what the Reflector adds on natural input (it demonstrably adds capability on injected faults; whether it ever *fires* in normal use on the 3 datasets was 0/6 organic runs + 1 organic fix in an earlier round, per README).

**Models:**
*implemented but under-specified* — provider dispatch (Gemini + Mistral) is real and tested (`test_llm_client.py`, 18 tests, mocked SDK). Which exact model versions produced the documented results is **[UNDETERMINABLE]**: three mutually inconsistent model strings exist in the tree — `.env.example` says `GEMINI_MODEL="gemini-3.5-flash"` (fallback `gemini-3.1-pro`), `llm_client.py` defaults are `gemini-3.1-flash`/`gemini-3.1-pro`, README tech-stack table says `gemini-3.1-flash`/`gemini-3.1-pro` and `open-mixtral-8x7b`/`mistral-large` while the code default is `mistral-large-latest`. Also: `temperature=0` is set for Mistral calls but **not** for Gemini calls (grep of `llm_client.py`: one occurrence, line 225) — so the "identical values across providers" comparison is not backed by matched decoding config.

**Validation methodology:**
*mixed — this is the section to read carefully before claiming anything:*
- Deterministic layers: unit-tested and sound (SQL column validator hardened against string literals, qualified refs, aliases; Pydantic constraint tests; execution semantics; compiler shape tests ×119). [VERIFIED passing]
- End-to-end live validation: 3 datasets × 2 providers, results recorded in README tables with per-node timings; acceptance criteria of issues #2–#6 explicitly checked off with evidence references. [DOCUMENTED — plausible, internally consistent with code and screenshots, but the underlying artifacts (profile/KPI/reflection JSONs, run logs) were removed from the tree and there are no committed raw logs, so it cannot be independently re-audited from this checkout]
- Fault injection: `scripts/run_reflector_stress_test.py` plants realistic errors (`sql_error`, `wrong_aggregation`, `null_heavy`) into a copy of real KPI files, runs the real executor+reflector, reports catches. This is a genuinely good methodological instinct — separating "does the capability exist" from "did it happen organically" — and it is clearly fenced (never read by the real pipeline; documented in script docstring and PR #13). Limitation: small scale (3 planted issues per run; README claims 24/24 across two rounds, both providers, two datasets — HR was never stress-tested per README), and "caught" includes 6/24 cases where the issue category differed (`null_heavy` → `wrong_aggregation`), which the README defends transparently. [DOCUMENTED, methodology [VERIFIED] in code; results not reproducible from tree (needs keys + deleted inputs)]
- Power BI Desktop open/parity: claimed for all datasets, both providers; supported by 10 real Desktop screenshots + 5 MB demo GIF + issue #6 checklist. **[DOCUMENTED only — cannot be verified on Linux; no generated `.pbip` output is committed for comparison]**
- n=1 timing comparison across providers is a single observation per dataset per provider, with no repeated runs and no statistical treatment. Do not present the timing table as benchmark evidence.

**Metrics:**
*modest and mostly qualitative* — "5/5 KPIs generated, 0 dropped" per dataset/provider; "12/12 (24/24) planted issues caught"; "0 wrong domain inferences observed"; per-node seconds. No accuracy/precision/recall against a labeled gold set exists or could exist without one. No hallucination-rate estimate beyond "validator rejected none in documented runs".

**Final result:**
*verified technical output, unquantified quality* — the pipeline compiles working `.pbip` projects from arbitrary CSVs with LLM-chosen KPIs; the self-correction loop is real code with real (small-scale) evidence it works when given something to correct; value parity between providers on Chinook (same `$2.33K` / `5.44` card values) is a credible and honestly-argued verification (README explains why simple aggregates must agree — single correct value regardless of phrasing) [DOCUMENTED, screenshot-consistent]. No product outcome, user, or external validation exists.

---

## Engineering evidence

**Tests:**
7 test files, **216 tests collected; 216 passed in 0.66 s** on this checkout (Python 3.11.2, latest pytest/pandas/pydantic from a fresh venv) — **[VERIFIED in this session]**, with one caveat that is itself a finding: on a *pure* fresh clone the suite runs **198 passed, 18 errors** because `tests/test_domain_kpi.py`'s `retail_profile` fixture reads `data/profiles/online_retail_profile.json`, which is gitignored and no longer committed (removed in `356670c`); running `python scripts/profile_datasets.py` regenerates it and the suite then fully passes. **[BROKEN on fresh clone — verified]**.
Composition:
- `test_profiler.py` (7): CSV/SQLite loading, all-null column, single-row file, spaces in names, mixed types, missing file.
- `test_domain_kpi.py` (26): prompt metadata-only guarantee, SQL column validator (hallucinations, aliases, keywords, string literals, qualified refs), Pydantic constraints (chart literal, confidence bounds, SELECT-only, exactly-5, unique names), `run_domain_kpi` orchestration with mocked LLM incl. repair pass.
- `test_llm_client.py` (18): retry/backoff on transient errors, immediate raise on non-transient, fallback-model chain, provider dispatch, key-absent errors.
- `test_sql_executor.py` (12): pass/fail capture, empty-result-is-pass semantics, row cap, source-table routing (decoy-table test), pipeline-level error capture, `rerun_single_kpi` isolation.
- `test_reflector.py` (17): note taxonomy validation, prompt construction incl. failure context, prerequisite guards, fix-application + retry flagging, drop-without-fix, unknown-note audit behavior, duplicate-name rejection, log write/skip.
- `test_pbir_compiler.py` (119): the deep core — every SQL→DAX shape, error paths (`SQLToDaxError`), page grouping/layout geometry, M-query construction incl. escaping regression tests, TMDL/JSON emission, visual-id truncation at Desktop's 50-char limit, filter-id uniqueness, theme-asset handling; includes integration-style tests building projects from dataset-shaped fixtures (added across `49cb9b3`, `d2ec638`, `4cd5651`).
- `test_prepare_chinook.py` (17): the SQLite→CSV grain-correct join (no double-counting of invoice totals across line grain — real correctness property, tested).
**Not tested:** `agent/graph.py` wiring/conditional edge, `run_agent.py` CLI, `run_sql_executor_retry` as a node (its primitive is tested, the drop-and-clear orchestration is not), all `scripts/run_*` drivers, anything touching real LLM SDK responses (correctly mocked). Evidence tests passed historically: PR descriptions carry pass counts ("7 passed in 0.86s", "119 automated tests passing", "70 tests total across the project"); no CI ever existed, so "tests pass" is only verifiable locally — which it does, today. [VERIFIED]

**APIs:**
No HTTP/API surface exists or is claimed. The interface is the CLI contract (`--input`, `--output`) plus typed module APIs (`run_*` node functions, `write_pbip(project, output_dir)`). Verified functional: `run_agent.py --help` runs on a fresh env [VERIFIED].

**CI/CD:**
**Absent.** No `.github/`, no workflows, no pre-commit, no lint/typecheck config, no coverage tooling. [VERIFIED by absence — and by `gh api .github` 404]

**Containers:**
Absent. No Dockerfile, no docker-compose, no image references. [VERIFIED by absence]

**Architecture patterns:**
Genuinely present and load-bearing (each [VERIFIED] in code): typed-Pydantic state as the sole inter-node contract; deterministic/LLM node separation with the LLM confined to 2 modules and infra isolated in `llm_client.py`; graph-topology-enforced retry budget (one retry, no loops); bounded one-shot repair before failure; fail-open-per-item, fail-closed-per-build semantics (a bad KPI is dropped, a thin report is rejected); post-hoc validation of untrusted model output against ground truth; re-export shims preserving import compatibility across the builder/serialiser module split (PR #12) so 119 tests needed no import changes — a clean refactor discipline evidenced in `builder.py`/`serialiser.py` docstrings and `88ad04a`; audit-trail artifacts (reflection JSON logs with timestamps); fault-injection harness deliberately isolated from the production path.

**Data validation:**
Layered: Pydantic literal/range/length constraints → regex lexical SQL identifier check against the profile (with deliberate, documented limits — no syntax validation, no grammar; the module docstring lists exactly what it does not do) → real SQLite execution as ground truth → LLM semantic review. Dtype mapping handles pandas 2/3 string-dtype variance (`_DTYPE_MAP` includes `str`/`string`). Honest engineering; the limits are self-documented rather than oversold. [VERIFIED]

**Error handling:**
Consistent non-crashing style: node-level precondition failures and per-KPI failures are appended to `state.errors`/captured in `QueryResult`, never raised into the caller mid-pipeline; LLM failures fall back provider-chain → error entry; `write_pbip` failure is caught by the CLI; retry node clears its flag list so state can't go stale. This is verifiably deliberate (guard tests exist for each). [VERIFIED] Gap: `run_agent.py` prints errors at the end but still exits 0 in failure states (no exit-code contract) [VERIFIED by reading code].

**Monitoring:**
Console logging per stage ("every stage announces itself before it runs"), per-node wall-clock timings, reflection logs. No structured logging, no metrics sink, no run-artifact persistence of raw API payloads. Appropriate for a CLI MVP; not production monitoring. [VERIFIED scope]

**Security:**
API keys from env/`.env`, never in code; `.env` gitignored; a scan of tracked text files for `AIza…`/`sk-…` patterns is clean [VERIFIED]. LLM SQL executes only against a throwaway in-memory SQLite DB with the SELECT-only validator in the prompt layer and Pydantic validator in the model layer — low blast radius by design, though the SELECT-only check is lexical (a sufficiently adversarial LLM output isn't the threat model here). Prompt injection isn't discussed (single-user local tool; acceptable, but don't claim "secure by design" beyond the sandboxing fact).

---

## Scale

All numbers below are repository-verifiable unless tagged.
- **Code:** ~4,900 lines Python in `agent/` + `pbir/` + `run_agent.py`; ~2,900 lines of tests; ~1,200 lines of scripts [VERIFIED via wc].
- **Tests:** 216 unit/integration tests in 7 files [VERIFIED collected & passing].
- **Datasets processed:** Online Retail **541,909 rows × 8 cols** (verified live: profiler output during this audit); Chinook prepared CSV **412 rows × 13 cols** (verified live); HR Analytics **1,470 rows × 35 cols** (541,910/413/1,471 lines including headers — VERIFIED via wc; the 541,910-line CSV read in ~0.85 s per README timings, consistent with a 2.5 s executor run on it).
- **Pipeline:** 6 nodes; 2 LLM providers × 2 model tiers each (primary+fallback); 5 KPIs per dataset run → 15 KPIs per provider round (documented 0/15 dropped); 2–3 pages and 4–5 visuals per compiled report.
- **LLM calls per full run:** 2 minimum (domain/KPI + reflector) up to ~4 with repair/retry passes — deliberately few.
- **SQL→DAX support surface:** 5 documented input shapes (the translator's own module docstring enumerates them) [VERIFIED]; chart types: 4.
- **Project history:** 126 commits (main), 7 merged PRs, 7 closed phase issues, 25 open V2 planning issues, 1 release tag (`v1.0.0` → `764883a`).
- **Format spec:** 1,129-line reverse-engineered PBIR/TMDL reference doc [VERIFIED line count].
- **No evidence of:** users, downloads, issues from third parties, external stars-based traction, deployment traffic — none of these exist in or outside the repo (no hosted deployment to measure). [VERIFIED by absence]
- **Stress-test scale:** 24 planted-fault evaluations claimed cumulative (12/12 × 2 rounds, per README); each round = 3 issues × 2 datasets × … structure visible in `run_reflector_stress_test.py`. [DOCUMENTED]

---

## Outcome

**What actually worked?**
- The full deterministic+compiler pipeline compiles a real, structurally valid Power BI Project from arbitrary CSVs — [VERIFIED in this session on a fresh checkout: profiler → hand-supplied KPIs → executor → compiler → `write_pbip` produced the complete `.pbip` tree with DAX measures in TMDL, per-KPI visual JSON, theme assets, and a correctly built Power Query M partition; invalid KPI was dropped and the min-visual gate behaved as designed].
- The self-correcting loop: exists, is wired at graph level, is unit-tested, and demonstrated catching 12/12 planted faults (×2 rounds) with fixes verified by real re-execution [DOCUMENTED artifacts; harness [VERIFIED] in code].
- Provider portability: one env var switches Gemini↔Mistral with code unchanged; a real Gemini 503 and a real Mistral 429 were survived by the retry/fallback machinery during the documented validation runs (an authentic outage, not a mock) [DOCUMENTED — PR #11/#13].
- Cross-provider numeric parity on Chinook aggregates ($2.33K / 5.44) — a genuinely smart, cheap equivalence check [DOCUMENTED, screenshot-consistent].
- 3 real Power BI format bugs found and fixed during validation (DAX translation gap for `CAST`/`COUNT(CASE WHEN…)`, relative→absolute M path, >50-char visual names rejected by Desktop) — each has a fix commit and a regression test [VERIFIED in code history: `bf1f42b`, `872684d`, `d5490eb` + `d2ec638`].

**What measurable result exists?**
Engineering outputs only: 3 reference datasets → 6 end-to-end runs (2 providers × 3 datasets) in the documented confirmation round, each producing a 2–3-page, 4–5-visual report; 216/216 tests green; full-run latency 12.5–32 s per dataset [DOCUMENTED timings]. There is **no** product impact, no external user, no before/after time-saving measurement against manual BI work, no third-party validation. Any "saves X hours" claim is unsupported by this repo.

---

## Limitations

**What does NOT work:**
- **[BROKEN, VERIFIED] Fresh-clone test suite:** 18 of 216 tests error out until you run the profiler script, because committed tests depend on the gitignored `data/profiles/online_retail_profile.json` fixture. A hiring-manager checkout that runs `pip install -r requirements.txt && pytest` sees red.
- **[BROKEN, VERIFIED] `scripts/profile_datasets.py` vs. HR dataset:** the script references `data/raw/hr.csv`; the committed file is `hr_analytics.csv` → HR profiling silently skips. Same stale filename appears in `notebooks/03` (`../data/raw/hr.csv`). Related naming drift: PR #9-era files were `hr.csv`/`hr_profile.json`; the repo now says `hr_analytics` — the rename wasn't propagated everywhere.
- **[PARTIAL/BROKEN by design drift] The evidence JSONs the README cites** (per-dataset profiles, `*_kpis.json`, reflection logs, stress-test outputs) **are no longer in the tree** (removed in `356670c`, then gitignored). The `run_reflector_stress_test.py` and `run_pbir_compiler_all.py` paths therefore cannot be run as documented from a fresh clone without first regenerating intermediate artifacts through live LLM calls (keys required). The claimed validation results are currently un-auditable from the repository itself.
- **Documented unfixed translation gap:** `COUNT(DISTINCT col) … WHERE col IS NOT NULL` fails SQL→DAX (README "Known remaining gap"). Additionally observed *in this audit*: the translator rejects T-SQL-style bracket quoting (`SUM([Total])`) and `CAST(x AS REAL)`-style ratios — i.e., the narrow-shape brittleness is real and slightly broader than the README's one cited example.
- **`fix_structure.sh` is a live footgun [VERIFIED]:** running it as the project's own issue #1 instructions once told you to, would overwrite the implemented `agent/state.py` (and other modules) with Phase-1 stubs. Dead scaffolding kept at repo root.

**What is unfinished:**
- Notebooks `01_dataset_profiling_exploration.ipynb` and `04_pbir_output_inspection.ipynb` are **0-byte placeholders** [VERIFIED]; `STRUCTURE.md` lists `data/profiles/` artifacts and `hr.csv`-era names that don't match the tree; `output/.gitkeep` referenced by `.gitignore` doesn't exist; `data/processed/` is empty dead scaffolding.
- README quickstart clone URL is the placeholder `github.com/your-username/agentic-bi-builder`; README links to `docs/pbir_reference.md` but the file is `docs/pbir reference.md` (space, different name).
- `requirements.txt` is unpinned and contains four dependencies the code never imports (`langchain-core`, `langchain-google-genai`, `langchain-mistralai`, plus `rich`, `openpyxl`, `jupyter`/`ipykernel` as unused-by-source extras) [VERIFIED via import grep]. No `pytest` in requirements despite a test suite. No license file of any kind exists [VERIFIED by absence].
- V2: 25 detailed planning issues (#15–#39, opened 2026-09-17) define a stateful explorer rework; **zero** branches/PRs/code exist for it (only `main`; #15's own checklist unchecked). Current and accurate: "planned, not started".
- The originally promised auto-date tables (PR #8 design decision: "included in v1") and 2-table join were descoped later; the README's limitations state this honestly, but the historical inconsistency is visible in PR #8.

**Reproducibility problems:**
Unpinned dependencies; no Python version floor stated (code needs 3.10+ for `X | None` syntax; pandas-3-`str`-dtype tolerance suggests the dev environment was bleeding-edge — not documented); LLM results are inherently non-reproducible (no saved run logs, no `temperature` parity across providers, no fixtures captured — exactly the gap issue #15 targets); everything Desktop-side requires Windows + Power BI Desktop, an unreplicable verifier for the flagship "opens in Power BI" claim; the compiled reports hardcode the generating machine's absolute CSV path.

**Deployment issues:**
Nothing to deploy — and that is documented as scope, not hidden. No Power BI Service publishing, no gateway, no hosting; "Power BI Desktop only" is stated in both README and Project Description. The only "deployment" is opening a folder locally; the first-open "incomplete or no data" cache-banner behavior is thoroughly documented (README + `docs/pbir reference.md` §2.12) including why it is benign — this is unusually good failure-mode documentation, but the *reliance on a manual click in Desktop to finish loading* remains a UX weakness.

**Technical debt:**
Regex SQL handling everywhere (`_validate_sql_columns`, `sql_to_dax`) — self-aware, documented, and regression-tested for known false-positive classes, but a fragile ceiling; mentor-authored hardening patch lives inside "my" modules (see ownership note); `state.errors` as a free-text string list rather than typed error objects; dataset-name keying via `Path.stem` convention coupling across scripts; console `print`-based observability.

**Unsupported / risky-to-claim items:**
"Reliably correct KPIs" (n=6 dataset-runs, no rubric); "the Reflector catches errors in practice" (it caught *planted* errors; organically it almost never fired — the README itself says so; don't launder the stress-test rate into a general reliability rate); timing/parity tables (no raw logs in-tree); "open in Power BI Desktop without errors" (screenshots are genuine artifacts but not generated-from-traceable-input proofs); model identities (three conflicting name sets in tree); anything implying production use, users, or a team.

---

## Current repository status

Everything below checked 2026-09-25 in a Linux sandbox, Python 3.11.2, fresh venv with unpinned latest `pytest pandas pydantic langgraph` (note: this is *not* the developer's environment; see reproducibility).

**Runs locally:**
Partially verified. `run_agent.py --help` — works [VERIFIED]. Deterministic half of the pipeline (profiler → executor → compiler → `write_pbip`) — runs and produces a valid `.pbip` tree on `data/raw/chinook.csv` with zero configuration beyond `pip install` [VERIFIED in this audit]. Full `run_agent.py` pipeline — cannot be verified here: requires a live `GEMINI_API_KEY`/`MISTRAL_API_KEY` (code paths for key-absent failure are clean: clear `RuntimeError`s, per module docstrings, and `state.errors` fallbacks exist) [PARTIAL: LLM-dependent segments UNDETERMINABLE without keys]. Opening output in Power BI Desktop — impossible on Linux; documented-only [DOCUMENTED].

**Tests pass:**
Yes, with a caveat that matters: fresh clone → **198 passed, 18 errored** [VERIFIED]; after `python scripts/profile_datasets.py` regenerates the missing gitignored fixture → **216 passed in 0.66 s** [VERIFIED]. No CI badge, no CI at all, so "they pass" is true only as demonstrated locally.

**Deployment:**
None exists or is claimed. Repo has no runtime service; the `v1.0.0` GitHub release is a source tag only (auto-generated changelog from PRs #8–#14, published 2026-08-30) [VERIFIED via gh].

**README quality:**
High and, unusually, honest: architecture description matches code; limitations section admits real gaps (COUNT(DISTINCT) DAX hole, regex validator limits, single-table scope, provider model substitution rationale); failure-mode writeups are concrete with commit-level fixes. Deductions: stale clone URL, broken `docs/pbir_reference.md` filename reference, results tables cite artifacts that are no longer committed, "June/July 2026" understates the August close, README claims "119 passing in test_pbir_compiler.py alone; 70+ across agent/" — both verified accurate today. [VERIFIED claims vs code]

**Demo available:**
Assets exist and look authentic: `assets/demo.gif` (~5 MB, terminal→Desktop walkthrough, under the 10 MB GitHub ceiling), hand-built architecture PNG that matches `graph.py`'s actual topology including the dashed conditional-retry edge [VERIFIED side-by-side], and 10 per-dataset Power BI Desktop screenshots (spot-verified two: genuine Desktop chrome, page names `Overview 1/2` consistent with `layout.py` conventions, and even the "by Revenue by BillingCountry" title artifact that `builder.py`'s defensive guard documents). These are demos-as-images, not a runnable demo — no hosted app, no recorded terminal logs, no reproducible trace from screenshot back to a specific commit.

---

## Evidence

**Relevant files (exact):**
- Pipeline: `agent/graph.py`; nodes `agent/profiler.py`, `agent/domain_kpi.py`, `agent/sql_executor.py`, `agent/reflector.py`, `agent/llm_client.py`; contracts `agent/state.py`, `agent/models.py`; CLI `run_agent.py`.
- Compiler: `pbir/models/` (9 model files), `pbir/compiler/builder.py` (min-visual gate, defensive title guard), `sql_to_dax.py` (1,041 lines, 5 documented shapes), `serialiser.py`, `m_query.py` (M-escape bug writeup in docstring), `tmdl.py`, `templates.py`, `visual_json.py`, `layout.py`; theme assets `pbir/compiler/theme_assets/…`.
- Tests: `tests/test_profiler.py` (7), `test_domain_kpi.py` (26), `test_llm_client.py` (18), `test_sql_executor.py` (12), `test_reflector.py` (17), `test_pbir_compiler.py` (119), `test_prepare_chinook.py` (17).
- Tooling: `scripts/prepare_chinook.py` (grain-correct join, rationale in docstring), `scripts/run_reflector_stress_test.py` (fault injection), `scripts/run_domain_kpi_all.py`, `run_sql_reflector_all.py`, `run_pbir_compiler_all.py`, `profile_datasets.py` (contains the `hr.csv` bug).
- Docs: `README.md`, `STRUCTURE.md`, `docs/Project Description.md`, `docs/pbir reference.md` (1,129 lines; §2.12 M-escaping, §2.4 schema-version coupling notes), `assets/` (diagram, GIF, 10 PNGs), `output/reference_report/…` (hand-authored reference `.pbip` from issue #1 — NOT compiler output; do not present as such).
- Notebooks: `notebooks/02_kpi_proposal_review.ipynb`, `03_sql_validation_and_reflection.ipynb` contain real executed outputs incl. a mistral-run reflection ("0 issue(s) found", sabotaged-KPI catch "Executor result for sabotaged KPI: fail no such column: ThisColumnDoesNotExist"); `01` and `04` are empty.

**Commits (key, from remote main):** `c835743` initial (2026-06-03) → `daf1b0f` provider switch to free-tier Gemini/Mistral → `29eaa47` "completed pbir reference" → `f730593…562420d` profiler (PR #9 era) → `5fa5347…f0cbfe4` domain/KPI + tests (PR #10 era) → `cca0106` mentor hardening → `ec71ae3…d3f11b2` compiler build-out + CASE-WHEN/DISTINCTCOUNT extensions → `88ad04a`/`ca3227b` module split → `71bd977` retry node, `12aeb94` node timing, `23453d2` stress-test harness, `f8c1979` dotenv fix → `bf1f42b`/`872684d`/`d5490eb` the three Phase-4 bug fixes → `356670c` evidence-artifact removal + gitignore → `3afcc4c`/`ec27b7a` polish → `764883a` final merge (2026-08-30, = `v1.0.0`).

**PRs:** #8 PBIR reverse-engineering (merged 2026-06-22, +4,571), #9 Profiler (2026-06-30, includes post-review changes list + "7 passed in 0.86s"), #10 Domain/KPI (2026-07-04, 26 tests, provider-substitution rationale), #11 SQL+Reflector (2026-07-13, 70 tests cited, sabotage methodology, real 503 recovery noted), #12 PBIR Compiler (2026-07-22, +8,206, 119 tests, descopes flagged), #13 Full pipeline (2026-07-22, validation tables, dotenv fix, three bug-fix notes), #14 Final polish (2026-08-30, diagram/GIF/README, honest "one acceptance criterion outstanding: the tag"). All authored by Tessa-Saumu; all merged by Tessa-Saumu except #8–#13 merged by/with Adeyeri Michael.

**Issues:** #1–#7 (phase briefs with acceptance criteria, all ticked; #2 comment trail documents review→fix cycle including the relative-path contract mismatch and Chinook table-selection), #15–#39 open V2 plan (2026-09-17; #15 explicitly treats the README evidence as "a useful baseline" to be re-verified and adds a regression-test task — an unusually candid self-audit in one's own issue tracker).

**Screenshots:** `assets/{chinook,online_retail,hr_analytics}/{gemini,mistral}_page*.png` — 10 files, spot-verified as genuine Power BI Desktop captures.

**Demo:** `assets/demo.gif` (~5 MB). No hosted/interactive demo. No presentation/slide deck in-repo [absent].

**Missing evidence to be aware of:** no raw run logs, no committed generated `.pbip` from the compiler, no committed profile/KPI/reflection JSONs (all gitignored), no benchmark scripts, no CI history. Release notes are GitHub auto-generated.

---

## Candidate CV bullets

*(left blank per instructions — to be drafted later from this evidence.)*

---

## Work required

### Critical — problems that prevent the repository from being credible professional evidence

1. **Make a fresh clone green.** Fix the 18 fresh-clone test errors: commit a small `tests/fixtures/online_retail_profile.json` (or generate it in a session fixture), removing the dependency on a gitignored path. Right now `pytest` on the public repo fails out of the box.
2. **Fix `scripts/profile_datasets.py` dataset filename drift** (`data/raw/hr.csv` → `data/raw/hr_analytics.csv`) and audit other stale `hr`-era references (`notebooks/03`, script docstrings).
3. **Restore or relocate the evidence chain the README cites.** Re-commit the small validation artifacts (profiles, `*_kpis.json`, reflection/stress-test JSONs) under something like `evidence/v1/`, or downgrade README result tables to link a gist/attachment with the raw logs. As-is, the flagship validation numbers are unverifiable from the checkout — and issue #15 already prescribes exactly this fix.
4. **Add a LICENSE.** The repo has none; legally that's "all rights reserved" and it blocks portfolio/conference reuse credibility.
5. **Pin dependencies and trim them.** Pin to versions that actually ran (`pandas`, `pydantic`, `langgraph`, `mistralai` major), delete unused `langchain-*`/`rich`/`openpyxl` entries, add `pytest`. State the supported Python version.
6. **Remove or neuter `fix_structure.sh`** (or rename + loud warning): it can destroy the implemented `agent/state.py` and siblings if a reader follows issue #1's historical instructions.
7. **Correct the README quickstart** (real clone URL) and the `docs/pbir_reference.md` vs `docs/pbir reference.md` filename mismatch; delete `data/processed/` and empty notebooks `01`/`04` or fill them; reconcile `STRUCTURE.md` with the actual tree.

### High value — materially stronger engineering evidence

1. **CI that runs the 216 tests on every push** (GitHub Actions, no secrets needed since LLM calls are mocked), plus `ruff`/`mypy` baseline. Converts "tests pass locally" into durable proof.
2. **LLM-free end-to-end regression test** per issue #15's own spec: capture validated KPI fixtures, run executor → compiler → serialiser, assert `.pbip` structure, TMDL measures, and bindings — including a deliberately broken binding that the test must catch. This makes the compiler's acceptance story auditable and permanent.
3. **Graph-level tests** for `agent/graph.py`: conditional-edge routing with/without flags, the one-retry-no-loop topology property, and `run_sql_executor_retry` drop/clear semantics (currently the node orchestration itself is untested).
4. **Close the known SQL→DAX gaps or formalize them:** implement `COUNT(DISTINCT …) WHERE … IS NOT NULL`, accept `[bracket]` identifier quoting (my verification hit this), and keep raising hard for anything else — each with shape tests. Alternatively adopt `sqlglot` parsing to widen the supported surface deterministically.
5. **Quantitative validation harness:** a small gold-standard KPI/expectation set per dataset (expected aggregate values), so end-to-end runs get scored (domain-inference correctness, KPI executability %, value correctness) instead of the current n=1 qualitative pass. Include repeated runs (n≥5) before ever citing timings; set `temperature=0` on the Gemini path for parity with Mistral.
6. **Broaden the fault-injection evidence:** add HR as a third stress-test dataset, more injections per category, and persist the results JSON in-repo; currently 24/24 is small and excludes `implausible_result`/`other` categories from the README's documented rounds.
7. **Portability of generated reports:** document (or fix) the absolute-path embedding in M partitions — e.g., emit a warning and a README "moving a report between machines" note; consider a relative-path attempt with fallback.
8. **`exit code` + `--json-summary` on `run_agent.py`** so pipeline failures are machine-detectable and runs are loggable/auditable.

### Optional — useful polish, not necessary

1. Fill notebooks 01/04 (profiling walkthrough, output inspection) to match 02/03's quality.
2. Package layout (`pyproject.toml`, `pip install -e .`) instead of `sys.path` insertions in scripts.
3. Structured logging (one `logging` config) replacing per-node `print`s.
4. A 60–90 s narrated Loom/YouTube demo alongside the GIF; a short write-up of the reverse-engineering methodology (the PBIR reference doc is genuinely interesting and buried).
5. GitHub Pages/markdown export of `docs/pbir reference.md` provenance notes; tidy issue #7's stale unchecked-box state with a comment linking the tag.
6. Em-dash sweep and "sqllite" typo in `profile_datasets.py` docstring; consistent dataset naming (`hr` vs `hr_analytics`) across scripts.

---

## Professional Evidence Assessment

**1. What engineering capability does this project prove best?**
System-building discipline around untrustworthy components: typed state contracts, deterministic validation of LLM output, topology-enforced repair budgets, graceful degradation (drop a KPI, never crash the run), 216 mocked-unit-plus-integration tests with zero network, and a reverse-engineered file-format compiler backed by a 1,129-line reference spec and regression tests for every discovered Desktop constraint. In plain terms: this proves the ability to make a flaky stochastic component safe inside real software — and to do it with an auditable PR/issue trail (7 phases, acceptance criteria, review cycles).

**2. What ML/AI capability does it prove best?**
Applied LLM engineering, not ML research: structured-output enforcement via provider-native schemas, metadata-only prompt construction with an enforced no-data-values contract, bounded self-repair (one LLM retry, then mechanical fallback), fault-injection testing of an agentic self-review loop, provider fallback with backoff demonstrated under real 503/429s. It also proves the judgment to *not* over-use the LLM (profiler, validator, executor, and compiler are all deterministic by design). It does **not** prove training, evaluation-science, or inference-optimization capability.

**3. What is the strongest verifiable achievement?**
The PBIR/TMDL compiler with its test suite: 119 tests passing locally today, plus this audit's independently produced `.pbip` from a fresh checkout — real DAX measures in generated TMDL, correct folder/ID conventions, Power-Query M partition, and Desktop-constraint handling that was discovered by finding and fixing three separate real bugs. Second-strongest (verifiable in-tree): the 216-test suite overall and the graph topology that structurally enforces the one-retry policy. The "it opens in Power BI Desktop and renders correct values" claim is stronger *as a story* but weaker *as evidence*, because the Desktop leg is documented-only from a Linux audit standpoint.

**4. What is the biggest credibility weakness?**
The verification chain the README's results rest on was deleted from the repository: profiles, KPIs, reflection logs, and stress-test outputs are gitignored, no CI ever ran, and no raw logs exist — so the headline numbers (24/24 catches, timings, provider parity) currently cannot be audited by anyone who clones the repo; they must trust the author's tables. Compounded by: fresh-clone test failures (198/216), unpinned/unused dependencies, no license, and the unverifiable Windows-only end. The work is strong; the *evidence of the work* was thrown away in cleanup and must be rebuilt.

**5. Is there enough here to justify investing additional time in this project?**
Yes — the cost-to-credibility ratio is unusually favorable. The hard substance (compiler, pipeline, tests, mentor-reviewed process) already exists; what's missing is mostly evidence hygiene: CI, fixtures-in-repo, pinned deps, restored validation artifacts, and one LLM-free end-to-end regression test — a few focused days (largely issue #15's checklist) turns "trust me" into "run it yourself." Only after that would the larger V2 plan (#15–#39) be worth pursuing for portfolio purposes, and even a partial V2 is unnecessary for CV purposes; a completed, verifiable v1 is enough.

**6. What type of professional role would this project support as evidence?**
Strongest fit: **Applied AI / LLM Engineer** (agent pipelines, structured output, validation loops, provider integration) and **AI-focused Backend/Data Platform Engineer** (format compiler, tooling, testing rigor). Decent supporting evidence for **Data Engineering roles touching BI** (profiling, SQL execution, Power BI/TMDL/DAX fluency is rare and demonstrable here). Weak for: ML research, model training/fine-tuning, MLOps/deployment (nothing runs anywhere), front-end, or "big data" scale claims. It is credible as a solo mentored project; it is *not* evidence of production system ownership.

**7. What claims should I NOT make publicly based on the current repository?**
- "Reflector achieves 100% error detection/correction" — it's 24 planted faults across 2 datasets, with 6 category mismatches the README itself discloses; organic catch rate was ~0 because the upstream SQL was mostly correct.
- Any production/enterprise framing: no users, no deployment, no SLA, no data volumes beyond three sample CSVs; "automates BI for teams" is unsupported.
- "Saves X hours vs. manual BI work" — no time-saving study exists.
- "All KPIs/SQL were validated as correct" — validation was syntactic + schema-existence + one LLM review; semantic correctness has no ground-truth metric here.
- "Reliable/consistent end-to-end" as tested behavior — it's 6 documented runs on 3 datasets, single attempt each; LLM non-determinism and deleted logs mean it isn't reproducible on demand.
- "Runs anywhere" — full runs need live provider keys, the final step needs Windows + Power BI Desktop, reports hardcode the compiling machine's paths, and fresh-clone tests currently fail.
- "I built the entire codebase solo" without qualification: ~99% is true by commit count, but two mentor commits live inside `agent/reflector.py`/`agent/models.py` and the mentor defined phase criteria, did merges/tagging — "solo implementation under structured mentorship" is the claim the git history will survive.
- Do not present `output/reference_report/` as pipeline output (it's the hand-built reverse-engineering artifact) and do not cite model versions precisely (three inconsistent name sets in the tree) or benchmark-style timings.
