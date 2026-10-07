"""
demo_core.py — headless core of the public deterministic demo (`app.py`).

This module drives the *deterministic half* of the pipeline:

    profiler  ->  committed KPI fixtures  ->  sql_executor  ->  pbir_compiler
              ->  write_pbip  ->  zip of the .pbip folder

It is deliberately split out of `app.py` so that:

1. The demo path is covered by the ordinary test suite
   (`tests/test_demo_app.py`) without Streamlit being installed —
   `streamlit` is a demo-only dependency listed in `requirements-demo.txt`,
   not in `requirements.txt`.
2. It is mechanically obvious that the demo never touches the LLM nodes:
   this module imports `agent.profiler`, `agent.sql_executor`, and the PBIR
   compiler only. It never imports `agent.llm_client`, `agent.domain_kpi`,
   `agent.reflector`, `agent.graph`, or `run_agent` (which pull in the
   provider SDKs). No API key can be required, and no network call is
   possible, because the KPI specs come from committed fixtures instead of
   a provider round-trip.

KPI fixtures are the ones already committed for the no-network end-to-end
regression tests (`tests/fixtures/kpis/<dataset>_kpis.json`) — real LLM
output from a recorded run, per `evidence/v1/README.md`. The demo re-executes
their SQL and recompiles the report; it does not re-generate them.

Nothing here mutates repository state: `.pbip` folders and their zips are
written under the platform temp directory.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent.models import DataProfile, DomainHypothesis, KPISpec, QueryResult
from agent.profiler import run_profiler
from agent.sql_executor import run_sql_executor
from agent.state import AgentState
from pbir.compiler.builder import run_pbir_compiler
from pbir.compiler.serialiser import write_pbip
from pbir.models.project import PBIRProject

REPO_ROOT = Path(__file__).resolve().parent

# Number of result rows shown per KPI in the demo UI (the full set stays in
# QueryResult.result_rows, capped upstream at agent.models.MAX_RESULT_ROWS_STORED).
PREVIEW_ROWS = 5

# Number of columns shown in the profiler's null-rate table in the demo UI.
TOP_NULL_COLUMNS = 5


@dataclass(frozen=True)
class DemoDataset:
    """One selectable dataset in the demo."""

    key: str
    label: str
    csv_path: Path
    kpi_fixture_path: Path
    screenshot_dir: Path
    # Which recorded live-provider run the committed KPI fixture (and therefore
    # the matching Power BI Desktop screenshots) came from. Used for honest
    # labelling in the UI: the demo recompiles these specs deterministically.
    fixture_provenance: str
    note: str = ""


@dataclass
class DemoRun:
    """Result of one deterministic demo run."""

    dataset: DemoDataset
    profile: DataProfile | None = None
    domain_hypothesis: DomainHypothesis | None = None
    kpi_specs: list[KPISpec] = field(default_factory=list)
    query_results: list[QueryResult] = field(default_factory=list)
    project: PBIRProject | None = None
    errors: list[str] = field(default_factory=list)
    timings_seconds: dict[str, float] = field(default_factory=dict)
    total_seconds: float = 0.0
    pbip_dir: Path | None = None
    zip_path: Path | None = None

    @property
    def page_count(self) -> int:
        return len(self.project.pages) if self.project is not None else 0

    @property
    def visual_count(self) -> int:
        if self.project is None:
            return 0
        return sum(len(page.visuals) for page in self.project.pages)

    @property
    def succeeded(self) -> bool:
        return self.project is not None and self.zip_path is not None and not self.errors


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

_MISTRAL_PROVENANCE = (
    "KPI specs are the committed fixture recovered from the recorded Mistral "
    "run (see evidence/v1/README.md); the demo re-executes and recompiles them."
)

DATASETS: dict[str, DemoDataset] = {
    "chinook": DemoDataset(
        key="chinook",
        label="Chinook — music retail",
        csv_path=REPO_ROOT / "data" / "raw" / "chinook.csv",
        kpi_fixture_path=REPO_ROOT / "tests" / "fixtures" / "kpis" / "chinook_kpis.json",
        screenshot_dir=REPO_ROOT / "assets" / "chinook",
        fixture_provenance=_MISTRAL_PROVENANCE,
    ),
    "online_retail": DemoDataset(
        key="online_retail",
        label="Online Retail — e-commerce",
        csv_path=REPO_ROOT / "data" / "raw" / "online_retail.csv",
        kpi_fixture_path=REPO_ROOT / "tests" / "fixtures" / "kpis" / "online_retail_kpis.json",
        screenshot_dir=REPO_ROOT / "assets" / "online_retail",
        fixture_provenance=_MISTRAL_PROVENANCE,
        note=(
            "Largest dataset (541K rows, ~46 MB CSV): profiling and SQL "
            "execution take a few seconds."
        ),
    ),
    "hr_analytics": DemoDataset(
        key="hr_analytics",
        label="HR Analytics — employee retention",
        csv_path=REPO_ROOT / "data" / "raw" / "hr_analytics.csv",
        kpi_fixture_path=REPO_ROOT / "tests" / "fixtures" / "kpis" / "hr_analytics_kpis.json",
        screenshot_dir=REPO_ROOT / "assets" / "hr_analytics",
        fixture_provenance=(
            "KPI specs match the README's recorded Mistral HR confirmation-run "
            "table; see the provenance caveat in FLAGSHIP_IMPLEMENTATION_PLAN.md "
            "(Phase 3–4 backlog)."
        ),
    ),
}


def list_datasets() -> list[DemoDataset]:
    """Datasets in demo display order."""
    return [DATASETS[key] for key in ("chinook", "online_retail", "hr_analytics")]


def demo_workdir(dataset_key: str, root: Path | None = None) -> Path:
    """Directory the demo compiles into (platform temp dir, per dataset)."""
    base = Path(root) if root is not None else Path(tempfile.gettempdir()) / "agentic_bi_demo"
    return base / f"{dataset_key}_report"


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def load_kpi_fixture(dataset: DemoDataset) -> tuple[DomainHypothesis, list[KPISpec]]:
    """Load the committed domain hypothesis + KPI specs for a dataset.

    Same fixture format `tests/test_end_to_end.py` consumes; validation happens
    through the Pydantic models, so a malformed fixture fails loudly here.
    """
    with open(dataset.kpi_fixture_path, encoding="utf-8") as f:
        raw = json.load(f)
    domain = DomainHypothesis(**raw["domain_hypothesis"])
    kpis = [KPISpec(**kpi) for kpi in raw["kpi_specs"]]
    return domain, kpis


def dataset_screenshots(dataset: DemoDataset, provider_prefix: str = "mistral") -> list[Path]:
    """Power BI Desktop screenshots for a dataset, page order.

    Falls back to every screenshot in the dataset's asset folder if no
    `<provider_prefix>_*` file exists, so the demo still shows something if the
    recorded-run naming ever changes.
    """
    if not dataset.screenshot_dir.is_dir():
        return []
    matched = sorted(dataset.screenshot_dir.glob(f"{provider_prefix}_*.png"))
    if matched:
        return matched
    return sorted(dataset.screenshot_dir.glob("*.png"))


# ---------------------------------------------------------------------------
# The deterministic demo run
# ---------------------------------------------------------------------------

def run_demo(dataset_key: str, workdir: Path | None = None) -> DemoRun:
    """Run profiler -> fixtures -> executor -> compiler -> .pbip -> zip.

    Never raises for pipeline failures: errors are collected in `DemoRun.errors`
    (the same fail-soft contract the agent nodes use), so the UI can report a
    rejected build instead of crashing.
    """
    if dataset_key not in DATASETS:
        raise KeyError(f"Unknown demo dataset '{dataset_key}'. Options: {sorted(DATASETS)}")

    dataset = DATASETS[dataset_key]
    out_dir = Path(workdir) if workdir is not None else demo_workdir(dataset_key)
    result = DemoRun(dataset=dataset)

    for path, what in ((dataset.csv_path, "dataset CSV"), (dataset.kpi_fixture_path, "KPI fixture")):
        if not path.is_file():
            result.errors.append(f"demo: missing {what} at {path}")
            return result

    # Fresh output dir every run: write_pbip only writes files it owns, so a
    # stale folder could otherwise leak files from an earlier compile into the
    # downloaded zip.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    state = AgentState(input_path=str(dataset.csv_path), output_path=str(out_dir))

    started = time.perf_counter()
    state = _timed(result, "profiler", run_profiler, state)
    result.profile = state.data_profile

    domain, kpis = load_kpi_fixture(dataset)
    state.domain_hypothesis = domain
    state.kpi_specs = kpis
    result.domain_hypothesis = domain
    result.kpi_specs = kpis

    state = _timed(result, "sql_executor", run_sql_executor, state)
    result.query_results = state.query_results

    state = _timed(result, "pbir_compiler", run_pbir_compiler, state)
    result.project = state.pbir_project

    if state.pbir_project is not None:
        try:
            _timed(result, "write_pbip", write_pbip, state.pbir_project, out_dir)
            result.pbip_dir = out_dir
            result.zip_path = _timed(result, "zip_pbip", _zip_pbip, out_dir)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the UI
            state.errors.append(f"demo: writing the .pbip bundle failed: {exc}")

    result.errors.extend(state.errors)
    result.total_seconds = round(time.perf_counter() - started, 3)
    return result


def _timed(result: DemoRun, step: str, fn, *args):
    """Call `fn(*args)`, recording wall-clock seconds under `step`."""
    started = time.perf_counter()
    try:
        return fn(*args)
    finally:
        result.timings_seconds[step] = round(time.perf_counter() - started, 3)


def _zip_pbip(pbip_dir: Path) -> Path:
    """Zip the compiled .pbip folder for the demo's download button.

    The archive keeps the folder itself as its single top-level entry, so
    extracting produces `<dataset>_report/` rather than loose files.
    """
    archive_base = pbip_dir.parent / pbip_dir.name
    made = shutil.make_archive(
        base_name=str(archive_base),
        format="zip",
        root_dir=str(pbip_dir.parent),
        base_dir=pbip_dir.name,
    )
    return Path(made)


# ---------------------------------------------------------------------------
# Small view helpers (kept here so they are testable without Streamlit)
# ---------------------------------------------------------------------------

def profile_summary_table(profile: DataProfile, limit: int = TOP_NULL_COLUMNS) -> list[dict]:
    """Per-column profiler rows, highest null rate first, capped at `limit`."""
    rows = [
        {
            "column": name,
            "dtype": column.inferred_dtype,
            "null_rate": column.null_rate,
            "distinct_count": column.distinct_count,
        }
        for name, column in profile.columns.items()
    ]
    rows.sort(key=lambda row: (-row["null_rate"], row["column"]))
    return rows[:limit]


def query_result_previews(
    query_results: list[QueryResult], limit: int = PREVIEW_ROWS
) -> list[dict]:
    """Per-KPI execution outcome plus the first `limit` result rows."""
    return [
        {
            "kpi_name": qr.kpi_name,
            "status": qr.status,
            "row_count": qr.row_count,
            "columns": qr.columns,
            "preview_rows": qr.result_rows[:limit],
            "error_message": qr.error_message,
        }
        for qr in query_results
    ]


def pbip_file_inventory(pbip_dir: Path) -> list[str]:
    """Relative paths of the files inside a compiled .pbip folder (sorted)."""
    if not pbip_dir.is_dir():
        return []
    return sorted(str(p.relative_to(pbip_dir)) for p in pbip_dir.rglob("*") if p.is_file())
