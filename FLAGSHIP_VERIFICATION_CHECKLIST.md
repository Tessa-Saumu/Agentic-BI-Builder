# Flagship Verification Checklist — Agentic BI Builder

**Purpose:** line-by-line verification of the Flagship Definition of Done from
`FLAGSHIP_GAP_AUDIT.md` (§ "Flagship Definition of Done"), executed as the final
task of Phase 5 in `FLAGSHIP_IMPLEMENTATION_PLAN.md`.

**Verified on:** 2026-10-07, against commit `9b90814` on branch
`arena/6869ede2-agentic-bi-builder` (plus this document's own commit).
Environment: Python 3.11.2, pinned `requirements.txt`
(`langgraph==1.2.14`, `google-genai==2.28.0`, `mistralai==3.1.0`, `pandas~=2.2`,
`pydantic==2.13.5`, `pytest~=9.1`), Linux, **no API keys at any point**.

**Legend:**
- ✅ **verified** — checked today by the method named.
- ⚠️ **verified with caveat** — the property holds; the caveat is stated inline.
- ❌ **blocked on owner / external action** — in-repo work is complete and
  verified; the remaining step needs the repository owner's account (GitHub
  Actions enablement, Streamlit Community Cloud, repo settings) or a human
  recording. Each ❌ carries the exact command/steps to close it and the reason
  it is deferred rather than faked.

The DoD is met when every item is ✅/⚠️ or explicitly deferred here with a
reason and a closure path. Current tally: **29 verified (27 ✅ + 2 ⚠️),
3 ❌ blocked on owner/external action** — items 3 (GitHub Actions enablement),
19 (Streamlit deployment), 20 (repo settings). All three have their in-repo
half verified and a written closure path.

---

## Reproducibility

### 1. `git clone && pip install -r requirements.txt && pytest` green on a fresh virtualenv
**Status: ✅ (with documented skips)**

- **Verified by:** fresh virtualenv created today, installing *only*
  `requirements.txt`, then the full suite.
- **Evidence:**
  `python3 -m venv .venv/ci-venv && .venv/ci-venv/bin/pip install -r requirements.txt && .venv/ci-venv/bin/python -m pytest -q -rs`
  → `261 passed, 3 skipped in 9.39s`, 0 errors, 0 failures,
  `SKIPPED [3] tests/test_demo_app.py:229: streamlit is a demo-only dependency
  (requirements-demo.txt), not installed by requirements.txt / CI`.
  With `requirements-demo.txt` additionally installed: `264 passed in 11.13s`.
  The 3 skips are the Streamlit UI tests of the demo app; they are skipped
  loudly with a reason, not hidden — every demo behaviour they cover is also
  covered key-free by the 16 non-Streamlit tests in the same file, which do run
  in this environment.
- **Date:** 2026-10-07.

### 2. Dependencies pinned, dead deps removed, `pytest` present, Python versions stated
**Status: ✅**

- **Verified by:** inspection + the fresh install above resolving without
  conflicts.
- **Evidence:** `requirements.txt` — `==` pins for `langgraph`, `google-genai`,
  `mistralai`, `pydantic`; `~=` pins for `pandas`/`numpy`/`openpyxl`/
  `python-dotenv`/`pytest`/`jupyter`/`ipykernel`; `pytest~=9.1` present; header
  comment `# Tested on Python 3.10, 3.11, 3.12`; no `langchain-*`/`rich` entries
  (removed in Phase 1; `grep -rn "langchain\|import rich" agent/ pbir/ run_agent.py scripts/` → no imports).
- **Date:** 2026-10-07 (pinning done in Phase 1; re-verified by today's clean install).

### 3. GitHub Actions CI runs the suite on every push; badge green; CI fails on non-zero `run_agent.py` exit
**Status: ❌ blocked on owner action — workflow correct, never allowed to execute**

- **Verified by (in-repo part):** the workflow file exists and is registered and
  active; its triggers cover every push to `main` and `arena/**` plus PRs to
  `main`; the exit-code contract it would enforce is tested
  (`tests/test_end_to_end.py::TestRunAgentCliAndSummary`, plus a manual run
  today: `python run_agent.py --input nonexistent.csv --output /tmp/out_check`
  → errors printed, `run_summary.json` written with `report_written: false`,
  **exit code 1**).
- **Evidence of the blocker:** GitHub API, 2026-10-07:
  `gh api repos/Tessa-Saumu/Agentic-BI-Builder/actions/workflows` →
  `{"id":377744326,"name":"Tests","path":".github/workflows/tests.yml","state":"active"}`;
  `gh api .../actions/workflows/377744326/runs` → `total_count: 0` (the Tests
  workflow has **never executed**); `gh api .../actions/runs?per_page=30` →
  8 runs, all `conclusion: startup_failure` with `path: "BuildFailed"`
  (including pushes to `main` and `arena/*` on 2026-10-07). `startup_failure`
  with no jobs is GitHub's signature for Actions being unavailable to the repo
  (private-repo Actions minutes / billing / enablement), not for a broken
  workflow file.
- **Consequence (deliberate):** the README CI badge is **not** added. The plan
  conditions the badge on a green CI ("Add CI status badge at the top of README
  once CI is green"); shipping a badge for a workflow that cannot run would be
  exactly the credibility defect this phase exists to remove.
- **Closure path (owner, ~5 min):** enable GitHub Actions for the repository
  (Settings → Actions → General → allow actions; for private repos confirm a
  payment method / minutes), then push any branch: the workflow will run the
  suite on 3.10/3.11/3.12. Once green, add
  `![Tests](https://github.com/Tessa-Saumu/Agentic-BI-Builder/actions/workflows/tests.yml/badge.svg)`
  at the top of README (the checklist row updates from ❌ to ✅ at that point).
- **Date:** 2026-10-07.

### 4. `scripts/profile_datasets.py` and all other `scripts/run_*` drivers work on a fresh clone (no silent skips)
**Status: ⚠️ verified for every key-free path; key-requiring drivers verified mechanically instead**

- **Verified by:** running the drivers today on a fresh checkout (no
  `data/profiles/` beforehand).
- **Evidence:**
  - `python scripts/profile_datasets.py` → profiles for all three datasets
    (`chinook`, `online_retail`, `hr_analytics`; no skips, correct filenames).
  - `python -m scripts.run_pbir_compiler_all` (after staging `data/profiles/`
    with the regenerated profiles + committed KPI fixtures) →
    `hr_analytics` and `online_retail` built (3/5/5 and 2/5/5), and chinook is
    announced as `SKIPPED: chinook is excluded by default (pass --chinook to
    include it)` — an explicit announcement, not a silent skip;
    `--chinook` then builds it (2/5/5). `.pbip` folders land in `output/`
    (gitignored).
  - `run_domain_kpi_all.py`, `run_sql_reflector_all.py`,
    `run_reflector_stress_test.py` require provider API keys by design (they
    call the LLM). Their mechanics are covered without keys by
    `tests/test_domain_kpi.py`, `tests/test_reflector.py`, and the evidence
    bundle's stress-test artifacts; a live re-run is the owner's closure step
    (commands in `evidence/v1/README.md`). No keys existed in this environment,
    and fabricating a "verified" run would violate the claims discipline this
    checklist enforces.
- **Date:** 2026-10-07.

### 5. LICENSE present (MIT)
**Status: ✅** — `LICENSE` at repo root, MIT, "Copyright (c) 2026 Theresia (Tessa) Saumu". Verified by inspection 2026-10-07 (added in Phase 1).

### 6. `fix_structure.sh` removed / disabled / prominently labelled
**Status: ✅** — now `scripts/_scaffold_phase1_reference.sh`, mode `-rw-r--r--`
(non-executable, verified `ls -l` today), header begins
"HISTORICAL SCAFFOLD SCRIPT — DO NOT RUN … Running it will overwrite
`agent/state.py` and other implemented modules with stubs." Verified 2026-10-07.

---

## Core system correctness

### 7. Deterministic end-to-end path on all three datasets, verified by a no-network regression test
**Status: ✅**
- **Verified by:** `tests/test_end_to_end.py::TestEndToEndReferenceDatasets`
  (profiler → committed KPI fixtures → executor → mocked reflector → retry node
  → compiler → `write_pbip`, for `chinook`, `online_retail`, `hr_analytics`;
  asserts pages/visuals/measure counts, TMDL measure blocks, absolute-path M
  partition, `.pbip` file layout). Re-run today: green. The Phase 5 demo adds a
  second, independent no-network path over the same three datasets
  (`tests/test_demo_app.py::TestRunDemo`), including a subprocess test proving
  the demo process never imports the LLM layer.
- **Date:** 2026-10-07.

### 8. Graph wiring + one-retry-no-loop topology verified by automated tests
**Status: ✅** — `tests/test_graph.py` (10 tests): routing function, compiled-graph
edge inspection for the no-loop invariant, retry clearing `kpis_to_retry`, and
node-invocation order with all LLM calls mocked. Green today.
- **Date:** 2026-10-07.

### 9. `run_agent.py` exits non-zero when no report is written / errors present; CI catches this
**Status: ⚠️ exit contract verified; "CI catches this" inherits item 3's blocker**
- **Verified by:** manual failure run today (exit code 1, errors listed,
  `run_summary.json` written) and success-path tests
  (`tests/test_end_to_end.py::TestRunAgentCliAndSummary` covers exit 0 and exit 1
  plus summary fields). CI-side enforcement awaits the item 3 blocker.
- **Date:** 2026-10-07.

### 10. Min-visual build gate exercised by an automated test
**Status: ✅** — `tests/test_end_to_end.py::TestRepairDropAndBuildGate::test_min_visual_gate_rejects_build_when_only_two_kpis_translatable`
(2 translatable KPIs → error recorded, no report). Green today; `MIN_VISUALS_REQUIRED = 4`
unchanged in `pbir/compiler/builder.py`.
- **Date:** 2026-10-07.

### 11. Broken-KPI drop semantics exercised by an automated test
**Status: ✅** — `tests/test_end_to_end.py`:
`test_unfixable_kpi_is_dropped_and_excluded_from_report` (reflector flags with no
fix → dropped before retry) and
`test_kpi_still_failing_after_retry_is_dropped_from_report` (fix offered but
still failing → dropped after the single retry). Green today.
- **Date:** 2026-10-07.

---

## Evidence

### 12. Committed evidence bundle with `metadata.json` (date, provider, model IDs, decoding, packages, Python)
**Status: ✅** — `evidence/v1/` (`metadata.json` + `README.md` + `chinook/` and
`online_retail/`, 7 JSONs each: profile, KPI specs, sabotaged KPIs, stress
reflection, reflection, query results, run summary). `metadata.json` records
collection date 2026-10-07, Python 3.11.2, exact package versions, canonical
model IDs per provider, `temperature: 0`, the historical-source commit
`6fed674`, and an honest `historical_provider: "unknown"`. Verified by
`python -m json.tool` on all 15 JSONs (Phase 3) and re-read today.
- **Caveat stated in-bundle:** the bundle's LLM artifacts are July 2026
  development runs, not the August confirmation round (whose raw artifacts were
  never committed). The bundle's own README says so.
- **Date:** 2026-10-07.

### 13. README result tables/timings cite the bundle; historical numbers labelled as historical with date + "artifacts not attached"
**Status: ✅** — new "Provenance of the numbers in this section" paragraph at the
top of `## Per-Dataset Results` (added in Phase 5): names the August 2026
confirmation round and its `v1.0.0` release date, states the raw artifacts were
not retained and are therefore reproducible-but-not-attached, and points to
`evidence/v1/` for the traceable July set plus the one compile-outcome delta.
- **Date:** 2026-10-07.

### 14. Model identifiers consistent across `.env.example`, `llm_client.py`, README; temperature consistent or asymmetry documented
**Status: ✅** — re-grepped today: `gemini-3.5-flash` / `gemini-3.1-pro` /
`mistral-large-latest` / `mistral-medium-latest` byte-identical in all three
files; `temperature=0` on both provider paths with the parity comment
(`agent/llm_client.py`, `run_agent._build_run_summary`). Established in Phase 3.
- **Date:** 2026-10-07.

### 15. Fault-injection results presented with in-line denominators
**Status: ✅** — README fault-injection section: "12/12 planted issues caught this
round (2 datasets × 3 fault types per provider, run under both providers) …
24/24 total across the two stress-test rounds to date (HR was not included …)",
with "6/24 adjacent-category diagnoses" in the same paragraph. Grep today: the
single `24/24` occurrence is inside that denominator-qualified sentence.
- **Date:** 2026-10-07.

### 16. Reflection organic-fire rate reported honestly
**Status: ✅** — README: "the Reflector flagged issues in 0–1 KPI per dataset (one
organic catch on Online Retail/Gemini …). The Reflector's correction capability
is demonstrated primarily by planted-fault evidence, not by a high organic error
rate". Unqualified "reliable" absent from README (grep `reliab` → 0 hits).
- **Date:** 2026-10-07.

---

## Portfolio packaging

### 17. README: correct clone URL, working internal links, Design Decisions, What I built / Credits, limitations section, quickstart that produces a green run
**Status: ✅**
- Clone URL: `https://github.com/Tessa-Saumu/Agentic-BI-Builder` in Quickstart and Setup (grep `your-username` → 0 hits).
- Internal links: scripted audit over README/STRUCTURE/evidence/notebooks/pbir-reference markdown links (file existence + heading anchors) → **0 broken**.
- `## Design Decisions` present with six rationale bullets (topology-enforced retry; provider-native structured output; regex translator + fail-closed; metadata-only vs sampled rows with the real test name `test_excludes_sample_values` and `MAX_ROWS_IN_PROMPT=10`; in-memory SQLite; fail-open per KPI / fail-closed per build).
- `## What I built / Credits` present; names both mentor commits by SHA with what each changed (`cca0106`, `55578ac` — verified against the GitHub API commit diffs today), the mentor's 6 PR merges (#8–#13) and that #14 + the `v1.0.0` tag were the author's; commit split stated as 123/132 as of today (verified via contributors API; the plan's 117/126 figure was pre-consolidation).
- Limitations section intact, plus an up-front "At a glance" box and scope sentence.
- Quickstart: fresh-clone note states the exact expected result (`261 passed, 3 skipped`, all 264 with demo deps) and the correct `.pbip` filename (`chinook.pbip`, not the old `report.pbip`).
- **Date:** 2026-10-07.

### 18. Architecture diagram accurately reflects `graph.py`
**Status: ✅** — diagram unchanged since v1; `agent/graph.py` node/edge set unchanged
since Phase 2, and `tests/test_graph.py` now asserts that exact topology
(profiler → domain_kpi → sql_executor → reflector → [retry →] pbir_compiler), so
drift fails a test rather than the diagram. Verified by reading `graph.py` today.
- **Date:** 2026-10-07.

### 19. Publicly accessible demonstration (Streamlit demo OR demo repo OR static evidence page + narrated video)
**Status: ❌ blocked on owner action — in-repo demonstration complete and verified; deployment needs the owner's Streamlit account**
- **Verified by (in-repo part):** the demo exists and works end-to-end on all
  three datasets with zero keys: `tests/test_demo_app.py` (16 key-free tests
  incl. `.pbip` + zip structure and the no-LLM-import subprocess guarantee; 3
  Streamlit UI tests via `streamlit.testing.v1.AppTest` where streamlit is
  installed), plus a live `streamlit run app.py` session today compiling
  Chinook/Online Retail/HR and producing a downloadable `.pbip` zip.
  `.streamlit/config.toml` committed for Community Cloud.
  README gained a "Try it without an API key" section with the two-command local
  run.
- **Evidence of the blocker:** Streamlit Community Cloud deployment is a
  browser/OAuth flow against the owner's GitHub + Streamlit accounts (app
  creation, repo selection, main file `app.py`); it cannot be performed from
  this sandbox, and the repository is private, so no public URL exists yet.
  Note for the deploy step: Community Cloud installs the repo's root
  `requirements.txt` into an environment that already contains `streamlit`,
  which is exactly what `app.py` needs (verified against Streamlit's
  dependency docs 2026-10-07); `requirements-demo.txt` is for local runs.
- **Closure path (owner, ~10 min):** share.streamlit.io → New app → repo
  `Tessa-Saumu/Agentic-BI-Builder`, branch `main`, main file `app.py`, no
  secrets (the implementation is proposed for merge in PR #43). Then (a) paste the URL into the README "Public URL" line and this
  checklist, (b) set it as the repo Website (item 20). If Cloud refuses the
  46 MB Online Retail CSV at free-tier memory limits, drop that dataset from
  `demo_core.DATASETS` (one-line removal, the other two still demonstrate the
  full path) and note it in the README demo section.
- **Date:** 2026-10-07.

### 20. Repository description, topics, profile link
**Status: ❌ blocked on owner action (settings are account-level)**
- **Current state (API, 2026-10-07):** description set (accurate, predates this
  phase); `topics: []`; `homepage: ""`; `visibility: private`.
- **Closure path (owner):** Settings → add topics `langgraph`, `llm`,
  `agentic-ai`, `power-bi`, `pydantic`, `python`, `text-to-sql`,
  `bounded-agent`, `llm-engineering`; set Website to the demo URL from item 19;
  pin the repo on the profile; decide on publicity (see item 19 — a public demo
  satisfies the DoD even while the source repo stays private, but a public repo
  is required for recruiters to clone).
- **Note:** this was performed through the GitHub UI in the original plan; it
  remains an owner-side action here. The audit's suggested description text is
  already covered by the existing description, so no change is required there.
  Attempted via the authenticated `gh` session on owner approval (2026-10-07):
  `PUT /repos/.../topics` → HTTP 403 "Resource not accessible by integration" —
  the session token has no repository-administration write scope, so topics can
  only be set in the UI.
- **Date:** 2026-10-07.

### 21. Empty notebooks removed or filled; dead scaffolding cleaned
**Status: ✅** — 0-byte notebooks `01`/`04` deleted (Phase 4) with
`notebooks/README.md` explaining why; `data/processed/` gone; `output/.gitkeep`
exists; `STRUCTURE.md` reconciled (again today, for the Phase 5 files). Verified
by `find -type f -empty` (only intentional `output/.gitkeep` and
`tests/__init__.py` package marker) and `ls` 2026-10-07.
- **Date:** 2026-10-07.

### 22. Screenshots linked from README with alt text; GIF/video shows a real end-to-end run
**Status: ✅** — Phase 5 added a "Report screenshots (Power BI Desktop, Windows)"
gallery embedding all 14 dataset screenshots with descriptive alt text
(filenames encode provider+page; two spot-checked visually against their alt
text). `assets/demo.gif` (real terminal run → Desktop) is embedded with alt
text. The narrated walkthrough video (gap G25) is deferred with a
ready-to-run storyboard below; the DoD's "the demo GIF **or** a linked video
shows an actual end-to-end run" clause is satisfied by the GIF in the meantime.
- **Date:** 2026-10-07.

### 23. Absolute-path behaviour + first-open Refresh banner documented and prominent
**Status: ✅** — documented in four places: the up-front "At a glance" box, the
Quickstart, the demo section and app UI warning, and the Known Limitations
"Report path coupling" + first-open banner paragraphs; plus a one-line console
note from `run_agent.py` after every successful write (Phase 3). Verified by
grep 2026-10-07.
- **Date:** 2026-10-07.

---

## Claims discipline

### 24. No claim of production use, users, enterprise deployment, "100% reliability", or time saved
**Status: ✅** — README states the opposite explicitly ("This is **not** a
production system, a product with users … or an autonomous analyst"; "not a
production system or a product with users" in Credits); grep for `reliab` in
README → 0 hits; no time-saved or user-count claims anywhere in README, and
none introduced by this phase.
- **Date:** 2026-10-07.

### 25. Power BI Desktop / Windows stated as a hard dependency up front, not buried
**Status: ✅** — first-screen scope sentence + "At a glance" box + Quickstart
("Then open … in Power BI Desktop (Windows)") + demo warning. Verified 2026-10-07.
- **Date:** 2026-10-07.

### 26. Metadata-only prompting guarantee correctly scoped
**Status: ✅** — Design Decisions bullet states metadata-only at domain/KPI time
and up-to-10 sampled result rows at reflection time, citing the enforcing test;
the "At a glance"/limitations text does not over-generalise it. Matches
`agent/domain_kpi.py` (strips sample values/min/max) and `agent/reflector.py`
(`MAX_ROWS_IN_PROMPT = 10` atop `MAX_RESULT_ROWS_STORED = 20`).
- **Date:** 2026-10-07.

### 27. Single-table scope, SQLite-only dialect, and the supported SQL→DAX shapes stated up front
**Status: ✅** — up-front scope sentence and "At a glance" box name single-table
CSV/SQLite input, SQLite-only dialect, and "a bounded set of measure shapes …
fails closed"; the Design Decisions bullet enumerates the shape families; the
full list lives in Known Limitations. (The DoD's "five shapes" phrasing is
superseded by the enumerated set: five DAX primitives across the shape families
closed in Phases 3–4; the number is not claimed anywhere as a bare count.)
- **Date:** 2026-10-07.

### 28. Provider/model parity claims tied to recorded runs, not general truths
**Status: ✅** — the provider-comparison table is explicitly scoped to "this
round"; the provenance paragraph ties it to the August confirmation round;
`evidence/v1/metadata.json` records that the historical artifacts' provider is
unknown and that decoding parity (`temperature=0` both paths) dates from
2026-10-07, so cross-provider numbers predating that are not presented as
methodologically matched.
- **Date:** 2026-10-07.

### 29. `output/reference_report/` labelled a reverse-engineering artifact, not pipeline output
**Status: ✅** — README "PBIR Output Structure" now states explicitly that
`output/reference_report/` is the trimmed hand-curated export the format was
reverse-engineered *from*, that nothing in `agent/` or `pbir/` reads or writes
it, and that pipeline output goes to `output/<dataset>_report/`; STRUCTURE.md
labels it the same way. (Added in Phase 5; previously only STRUCTURE.md carried
the label and README never mentioned the directory at all.)
- **Date:** 2026-10-07.

---

## Out-of-bounds verification

### 30. None of the "Explicitly Out of Scope" items started
**Status: ✅** — greps today across `*.py`, `*.txt`, `*.toml`, `*.yml`: no
`Dockerfile`, no FastAPI/Starlette app outside Streamlit's own runtime, no
`sqlglot`, no vector-store imports (`faiss`/`chroma`/`pinecone`/`qdrant`/
`weaviate`), no multi-table join code path (compiler scope unchanged: single
`DataTable`), no fine-tuning/training code, no auth/multi-user code. The one
`langchain` hit is a docstring explaining the project does **not** use it.
The Streamlit demo is the audit's explicitly in-scope exception ("a lightweight
deterministic demo Streamlit app … is in scope"), and it never imports the LLM
layer (mechanically asserted).
- **Date:** 2026-10-07.

### 31. V2 issues (#15–#39) remain open; no v2 code merged as "polish"
**Status: ✅** — GitHub API today: 25 open issues, **all 25** titled `V2: …`;
no issue in #15–#39 closed; this phase's only code additions are `app.py`,
`demo_core.py`, and `tests/test_demo_app.py` (plus docs), none of which touch
v2 scope.
- **Date:** 2026-10-07.

### 32. No "end-to-end BI platform / autonomous data analyst / production-grade agent" claims
**Status: ✅** — the README's first screen says the opposite in plain words
("What it is not: a production system, a hosted API, a multi-user tool, or an
'autonomous data analyst'"), and the Credits section repeats the v1-prototype
framing. Verified by grep 2026-10-07.
- **Date:** 2026-10-07.

---

## Phase 5 gap status (G11–G14, G19, G25)

| Gap | Deliverable | Status |
|---|---|---|
| G11 | Zero-key public Streamlit demo | ✅ in-repo (`app.py`, `demo_core.py`, `.streamlit/config.toml`, `requirements-demo.txt`, 19 tests, live local run) · ❌ deployment (owner, item 19) |
| G12 | README link/structural fixes | ✅ clone URL ×2, `docs/pbir_reference.md` rename + links, fresh-clone note, "what you will see", `.pbip` filename fix, screenshot alt text; CI badge intentionally withheld pending green CI (item 3) |
| G13 | "What I built / Credits" | ✅ with API-verified commit/PR facts; counts updated to today's (123/132, 6 mentor merges) |
| G14 | "Design Decisions" | ✅ six bullets, all cross-checked against code and tests |
| G19 | Repo metadata | ❌ owner action (item 20); suggested topics/closure steps recorded |
| G25 | Narrated 2–3 min demo video | Closed as **deferred with reason (permanent)** by owner decision 2026-10-07: a screen recording cannot be produced from this environment and the DoD's "demo GIF or a linked video" clause is satisfied by `assets/demo.gif`; storyboard retained below for an optional future recording |

### G25 recording storyboard (optional; DoD already satisfied by the demo GIF)

1. `git clone … && pip install -r requirements.txt && pytest` → show the green
   count (0:00–0:30).
2. `python run_agent.py --help`, then the deterministic demo:
   `pip install -r requirements-demo.txt && streamlit run app.py` → pick Chinook,
   run, scroll the profiler table / KPI SQL / result previews (0:30–1:30).
3. Download the zip, unzip, show `chinook.pbip` + folder structure; state the
   Windows/Desktop + absolute-path caveat on camera (1:30–2:00).
4. Open `tests/test_pbir_compiler.py` and scroll two or three test functions;
   mention the 50-char visual-ID and M-escaping tests as "real Desktop
   constraints" (2:00–2:30).
5. Close with `evidence/v1/` open in the editor: "this is what I can prove"
   (2:30–3:00). Link from README's Demo section once uploaded (Loom/YouTube
   unlisted).

---

## How to re-run this verification

```bash
pip install -r requirements.txt              # or -r requirements-demo.txt for all 264
pytest -q -rs                                # 261 passed, 3 skipped (streamlit UI)
python scripts/profile_datasets.py           # key-free driver check
python -m scripts.run_pbir_compiler_all --chinook   # after staging data/profiles/
python run_agent.py --input nonexistent.csv --output /tmp/x ; echo $?   # expect 1
streamlit run app.py                         # demo, zero keys
gh api repos/Tessa-Saumu/Agentic-BI-Builder/actions/workflows/377744326/runs --jq .total_count  # CI: 0 until owner enables Actions
```

**Final ship signal check (from the plan):** (a) public demo URL — ❌ pending
owner deployment; (b) demo works in-browser — ✅ locally, incl. `.pbip`
download; (c) link to repo — ✅ README; (d) README answers
problem/approach/contributions/limits in <10 min — ✅; (e) clone → pytest green
+ CI green — ✅ clone/test, ❌ CI (blocked); (f) committed evidence bundle with
provenance — ✅. Two owner actions (enable Actions; deploy demo + repo
settings) plus one human recording (G25) remain; everything else in the DoD is
verified above.
