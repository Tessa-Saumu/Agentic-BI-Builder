"""
app.py — "Agentic BI Builder — Deterministic Demo" (Streamlit).

Public, zero-API-key demonstration of the deterministic half of the pipeline:

    profiler  ->  committed KPI specs  ->  SQLite execution  ->  PBIR/TMDL
    compilation  ->  downloadable .pbip folder

What this demo is *not*: it makes no LLM calls. The KPI specs (name, SQL, chart
type, reasoning) are the committed fixtures from a recorded provider run — the
same fixtures the no-network regression tests use — so the demo runs anywhere
with no keys and no network. The LLM nodes (domain/KPI proposal and
self-reflection) live in `agent/` and are covered by the test suite plus the
artifact bundle in `evidence/v1/`.

All pipeline work is in `demo_core.py` (headless, unit-tested); this file is
only presentation.

Run locally:
    pip install -r requirements-demo.txt
    streamlit run app.py
"""
from __future__ import annotations

import contextlib
import io

import pandas as pd
import streamlit as st

import demo_core

REPO_URL = "https://github.com/Tessa-Saumu/Agentic-BI-Builder"
ARCHITECTURE_DIAGRAM = demo_core.REPO_ROOT / "assets" / "architecture_diagram.png"

st.set_page_config(
    page_title="Agentic BI Builder — Deterministic Demo",
    page_icon="📊",
    layout="wide",
)


@st.cache_data(show_spinner="Profiling, executing KPI SQL, and compiling the .pbip…")
def _run_dataset(dataset_key: str) -> tuple[demo_core.DemoRun, str]:
    """Run the deterministic pipeline for one dataset, capturing console output.

    Cached per dataset: the pipeline is deterministic, so a rerun on widget
    interaction would otherwise repeat seconds of pandas/SQLite work for the
    same bytes.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        run = demo_core.run_demo(dataset_key)
    return run, buffer.getvalue()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

datasets = demo_core.list_datasets()
labels = {ds.label: ds.key for ds in datasets}

with st.sidebar:
    st.header("Deterministic demo")
    st.caption(
        "No API keys, no network calls. KPI specs are committed fixtures from a "
        "recorded provider run."
    )
    chosen_label = st.selectbox("Dataset", list(labels), index=0)
    chosen = demo_core.DATASETS[labels[chosen_label]]
    if chosen.note:
        st.caption(chosen.note)
    run_clicked = st.button("Run profiler and compile", type="primary", width="stretch")
    st.divider()
    st.markdown(
        f"**Source:** [{REPO_URL.removeprefix('https://')}]({REPO_URL})  \n"
        f"**Evidence bundle:** [`evidence/v1/`]({REPO_URL}/tree/main/evidence/v1)  \n"
        f"**PBIR format reference:** "
        f"[`docs/pbir_reference.md`]({REPO_URL}/blob/main/docs/pbir_reference.md)"
    )

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("Agentic BI Builder — Deterministic Demo")

st.markdown(
    f"""
This is the **deterministic half** of [Agentic BI Builder]({REPO_URL}): a LangGraph
agent that profiles a CSV, proposes KPIs with SQL through an LLM, executes and
self-reviews those queries, and compiles the validated results into a real
Power BI Project (`.pbip`) folder that opens natively in Power BI Desktop.

The LLM steps are **not** called here. This demo runs the profiling, SQL
execution, and PBIR/TMDL compilation that the agent's output goes through, using
KPI specs that a provider produced in a recorded run and that are committed to
the repo (`tests/fixtures/kpis/`). That keeps the public demo key-free and
fully reproducible — the same fixtures drive the no-network regression tests.
"""
)

st.info(
    "**Scope (v1):** single-table CSV input · SQLite execution · regex SQL→DAX "
    "translation over a bounded shape set (fails closed otherwise) · four visual "
    "types · minimum 4 visuals per report · **Power BI Desktop on Windows** is "
    "required to open the compiled output."
)

if ARCHITECTURE_DIAGRAM.is_file():
    with st.expander("Architecture (agent pipeline — the LLM nodes are the two this demo skips)"):
        st.image(str(ARCHITECTURE_DIAGRAM), width="stretch")

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if run_clicked:
    st.session_state["demo_run"], st.session_state["demo_console"] = _run_dataset(chosen.key)
    st.session_state["demo_run_key"] = chosen.key

run: demo_core.DemoRun | None = st.session_state.get("demo_run")
console_text: str = st.session_state.get("demo_console", "")

if run is None:
    st.stop()

if st.session_state.get("demo_run_key") != chosen.key:
    st.caption(
        f"Showing the last run (**{run.dataset.label}**) — press "
        f"“Run profiler and compile” to run {chosen.label}."
    )

st.subheader(f"Run: {run.dataset.label}")

if run.errors:
    st.error("This run did not produce a report:")
    for error in run.errors:
        st.markdown(f"- `{error}`")

st.markdown(f"*{run.dataset.fixture_provenance}*")

col1, col2, col3, col4, col5, col6 = st.columns(6)
profile = run.profile
col1.metric("Rows", f"{profile.row_count:,}" if profile else "—")
col2.metric("Columns", profile.column_count if profile else "—")
col3.metric("KPIs executed", len(run.query_results))
col4.metric("Pages", run.page_count)
col5.metric("Visuals", run.visual_count)
col6.metric("Total time", f"{run.total_seconds:.2f}s")

if console_text:
    with st.expander("Console output from the pipeline nodes"):
        st.code(console_text, language="text")

with st.expander("Per-step timings"):
    st.dataframe(
        pd.DataFrame(
            [{"step": step, "seconds": seconds} for step, seconds in run.timings_seconds.items()]
        ),
        hide_index=True,
        width="stretch",
    )

# --- Profiler output -------------------------------------------------------

st.subheader("1 · Profiler output (deterministic, pandas)")

if profile is not None:
    st.caption(
        f"Domain hypothesis from the recorded run: **{run.domain_hypothesis.domain}** "
        f"(confidence {run.domain_hypothesis.confidence:.2f})"
        if run.domain_hypothesis
        else ""
    )
    st.markdown(
        f"**Top {demo_core.TOP_NULL_COLUMNS} columns by null rate** "
        "(the KPI-proposal prompt sees this metadata only — sample values, min, "
        "and max are stripped from it):"
    )
    st.dataframe(
        pd.DataFrame(demo_core.profile_summary_table(profile)),
        hide_index=True,
        width="stretch",
    )
    with st.expander(f"All {profile.column_count} profiled columns"):
        st.dataframe(
            pd.DataFrame(demo_core.profile_summary_table(profile, limit=profile.column_count)),
            hide_index=True,
            width="stretch",
        )

# --- KPI specs -------------------------------------------------------------

st.subheader("2 · Committed KPI specs (what the LLM proposed in the recorded run)")

for kpi in run.kpi_specs:
    with st.expander(f"{kpi.name} — `{kpi.chart_type}`"):
        st.markdown(kpi.description)
        st.code(kpi.sql_query, language="sql")
        st.caption(f"**Reasoning:** {kpi.reasoning}")

# --- Execution results -----------------------------------------------------

st.subheader("3 · SQL execution against in-memory SQLite")

for preview in demo_core.query_result_previews(run.query_results):
    label = f"{preview['kpi_name']} — {preview['status'].upper()} · {preview['row_count']} row(s)"
    with st.expander(label, expanded=preview["status"] == "fail"):
        if preview["error_message"]:
            st.error(preview["error_message"])
        if preview["preview_rows"]:
            st.dataframe(
                pd.DataFrame(preview["preview_rows"], columns=preview["columns"]),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                f"First {len(preview['preview_rows'])} of {preview['row_count']} row(s)."
            )
        else:
            st.caption("No rows returned.")

# --- Compiled report -------------------------------------------------------

st.subheader("4 · Compiled Power BI Project (.pbip)")

if run.succeeded and run.zip_path is not None:
    st.success(
        f"Compiled {run.page_count} page(s) / {run.visual_count} visual(s) with "
        f"{len(run.kpi_specs)} DAX measure group(s) in {run.total_seconds:.2f}s."
    )
    st.download_button(
        label=f"Download {run.zip_path.name} ({run.zip_path.stat().st_size // 1024} KB)",
        data=run.zip_path.read_bytes(),
        file_name=run.zip_path.name,
        mime="application/zip",
        type="primary",
    )
    st.warning(
        "**Before you open it:** the Power Query M partition embeds the "
        "*absolute* CSV path of the machine that compiled it — here, this demo "
        "server — because `File.Contents(...)` does not accept repo-relative "
        "paths. To get a report that loads against your own copy of the data, "
        "run the pipeline locally (`python run_agent.py --input <your csv> "
        "--output <dir>`) or re-point the CSV to the same absolute path. See "
        "**Report path coupling** in the README's Known Limitations. Power BI "
        "Desktop (Windows) is required to open a `.pbip`, and every freshly "
        "compiled project shows an “incomplete or no data” banner until you "
        "click **Refresh** once."
    )
    with st.expander("Files written into the .pbip folder"):
        st.code("\n".join(demo_core.pbip_file_inventory(run.pbip_dir)), language="text")
    tmdl_path = (
        run.pbip_dir / f"{run.project.report_name}.SemanticModel" / "definition" / "tables"
        / f"{run.project.data_table.name}.tmdl"
    )
    if tmdl_path.is_file():
        with st.expander(f"Generated `{tmdl_path.name}` (schema + M partition + DAX measures)"):
            st.code(tmdl_path.read_text(encoding="utf-8"), language="text")
else:
    st.error("No downloadable report — see the errors above.")

# --- Recorded Desktop screenshots -----------------------------------------

screenshots = demo_core.dataset_screenshots(run.dataset)
if screenshots:
    st.subheader("5 · What it looks like in Power BI Desktop")
    st.caption(
        "Windows-only screenshots from the recorded provider run whose KPI specs "
        "this demo recompiles. Opening the downloaded `.pbip` in Power BI Desktop "
        "for Windows produces a report with this page and visual structure."
    )
    for shot in screenshots:
        st.image(str(shot), caption=shot.stem.replace("_", " "), width="stretch")

st.divider()
st.caption(
    f"Full agent source, tests, and the committed evidence bundle: [{REPO_URL}]({REPO_URL}). "
    "This demo is a bounded v1 prototype, not a production system."
)
