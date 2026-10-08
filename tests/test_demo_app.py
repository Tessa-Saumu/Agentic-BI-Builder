"""
Tests for the public deterministic demo: demo_core.py (headless) and app.py
(Streamlit UI).

Verifies:
  - The demo dataset registry points at committed CSVs, KPI fixtures, and
    screenshots (no gitignored or generated paths).
  - run_demo() drives profiler -> committed KPIs -> executor -> compiler ->
    write_pbip -> zip, and reports pipeline failures in DemoRun.errors instead
    of raising.
  - The compiled bundle is a structurally valid .pbip and the zip keeps the
    folder as its single top-level entry (what the download button ships).
  - The demo never imports the LLM layer (agent.llm_client / agent.domain_kpi /
    agent.reflector / agent.graph / run_agent), which is what makes it runnable
    with zero API keys and no network.
  - The Streamlit app itself renders and compiles a dataset on button press
    (skipped where streamlit is not installed: it is a demo-only dependency in
    requirements-demo.txt, not in requirements.txt).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import demo_core  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
ALL_DATASET_KEYS = ("chinook", "online_retail", "hr_analytics")


@pytest.fixture(scope="module")
def chinook_run(tmp_path_factory):
    """One shared Chinook demo run for the assertions that only read its output."""
    workdir = tmp_path_factory.mktemp("demo") / "chinook_report"
    return demo_core.run_demo("chinook", workdir=workdir)


# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

class TestDemoDatasetRegistry:
    @pytest.mark.parametrize("dataset_key", ALL_DATASET_KEYS)
    def test_registry_entries_point_at_committed_files(self, dataset_key):
        dataset = demo_core.DATASETS[dataset_key]
        assert dataset.csv_path.is_file(), f"missing CSV: {dataset.csv_path}"
        assert dataset.kpi_fixture_path.is_file(), f"missing KPI fixture: {dataset.kpi_fixture_path}"
        # Fixtures are the ones the no-network e2e regression tests use, so the
        # demo and CI exercise identical KPI specs.
        assert dataset.kpi_fixture_path.parent == REPO_ROOT / "tests" / "fixtures" / "kpis"
        assert dataset.screenshot_dir.is_dir(), f"missing screenshot dir: {dataset.screenshot_dir}"
        assert demo_core.dataset_screenshots(dataset), "no screenshots found for dataset"

    def test_list_datasets_covers_every_registered_dataset(self):
        listed = demo_core.list_datasets()
        assert [ds.key for ds in listed] == list(ALL_DATASET_KEYS)
        assert set(demo_core.DATASETS) == set(ALL_DATASET_KEYS)

    def test_every_fixture_holds_five_kpi_specs(self):
        for dataset in demo_core.list_datasets():
            _, kpis = demo_core.load_kpi_fixture(dataset)
            assert len(kpis) == 5, f"{dataset.key}: expected 5 committed KPI specs"
            assert all(kpi.sql_query.strip().upper().startswith("SELECT") for kpi in kpis)


# ---------------------------------------------------------------------------
# The deterministic run itself
# ---------------------------------------------------------------------------

class TestRunDemo:
    def test_chinook_run_produces_valid_pbip_and_downloadable_zip(self, tmp_path):
        run = demo_core.run_demo("chinook", workdir=tmp_path / "chinook_report")

        assert run.succeeded
        assert run.errors == []
        assert run.profile is not None
        assert run.profile.row_count == 412
        assert len(run.kpi_specs) == 5
        assert len(run.query_results) == 5
        assert all(qr.status == "pass" for qr in run.query_results)
        assert run.page_count == 2
        assert run.visual_count == 5

        # Every pipeline step the demo claims to run is timed.
        assert set(run.timings_seconds) == {
            "profiler", "sql_executor", "pbir_compiler", "write_pbip", "zip_pbip",
        }
        assert run.total_seconds > 0

        # .pbip structure spot-check (same shape tests/test_end_to_end.py asserts).
        pbip_dir = run.pbip_dir
        assert (pbip_dir / "chinook.pbip").is_file()
        assert (pbip_dir / "chinook.Report" / "definition" / "pages" / "pages.json").is_file()
        tmdl_file = pbip_dir / "chinook.SemanticModel" / "definition" / "tables" / "data.tmdl"
        assert tmdl_file.is_file()
        tmdl_text = tmdl_file.read_text(encoding="utf-8")
        assert len(re.findall(r"^\tmeasure\s+", tmdl_text, flags=re.MULTILINE)) == 5
        # The M partition must embed an absolute path (Desktop rejects relative ones).
        assert 'File.Contents("' in tmdl_text

        # The zip ships the folder itself as its single top-level entry.
        assert run.zip_path.is_file()
        with zipfile.ZipFile(run.zip_path) as archive:
            names = archive.namelist()
            top_level = {name.split("/", 1)[0] for name in names}
            assert top_level == {pbip_dir.name}
            assert f"{pbip_dir.name}/chinook.pbip" in names

    @pytest.mark.parametrize(
        "dataset_key,expected_pages",
        [("chinook", 2), ("online_retail", 2), ("hr_analytics", 3)],
    )
    def test_every_dataset_compiles_five_visuals_with_no_errors(
        self, dataset_key, expected_pages, tmp_path
    ):
        run = demo_core.run_demo(dataset_key, workdir=tmp_path / f"{dataset_key}_report")

        assert run.succeeded, run.errors
        assert run.errors == []
        assert run.page_count == expected_pages
        assert run.visual_count == 5
        assert run.zip_path.is_file()

    def test_unknown_dataset_key_raises_with_the_valid_options(self):
        with pytest.raises(KeyError, match="chinook"):
            demo_core.run_demo("not_a_dataset")

    def test_missing_input_is_reported_in_errors_not_raised(self, monkeypatch, tmp_path):
        """A dataset whose CSV is absent must fail soft, like the agent nodes do."""
        broken = demo_core.DemoDataset(
            key="broken",
            label="Broken",
            csv_path=tmp_path / "does_not_exist.csv",
            kpi_fixture_path=demo_core.DATASETS["chinook"].kpi_fixture_path,
            screenshot_dir=demo_core.DATASETS["chinook"].screenshot_dir,
            fixture_provenance="test-only",
        )
        monkeypatch.setitem(demo_core.DATASETS, "broken", broken)

        run = demo_core.run_demo("broken", workdir=tmp_path / "out")

        assert not run.succeeded
        assert run.project is None
        assert run.zip_path is None
        assert len(run.errors) == 1
        assert "missing dataset CSV" in run.errors[0]

    def test_default_workdir_lives_outside_the_repository(self):
        """Demo output goes to the platform temp dir, never into the checkout."""
        default = demo_core.demo_workdir("chinook")
        assert not default.is_relative_to(REPO_ROOT)
        assert default.name == "chinook_report"


# ---------------------------------------------------------------------------
# Zero-key guarantee
# ---------------------------------------------------------------------------

class TestDemoNeverTouchesTheLLMLayer:
    def test_llm_modules_are_not_imported_by_a_demo_run(self):
        """Run the demo in a fresh interpreter and assert no LLM layer loaded.

        Subprocess (rather than an in-process sys.modules check) because other
        tests in the same session legitimately import the LLM nodes.
        """
        script = (
            "import sys, demo_core;"
            "demo_core.run_demo('chinook');"
            "banned = [m for m in ("
            "'agent.llm_client','agent.domain_kpi','agent.reflector','agent.graph','run_agent'"
            ") if m in sys.modules];"
            "print('BANNED:' + ','.join(banned) if banned else 'CLEAN')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip().endswith("CLEAN"), proc.stdout


# ---------------------------------------------------------------------------
# View helpers used by app.py
# ---------------------------------------------------------------------------

class TestViewHelpers:
    def test_profile_summary_table_is_null_rate_ordered_and_capped(self, chinook_run):
        rows = demo_core.profile_summary_table(chinook_run.profile)
        assert len(rows) == demo_core.TOP_NULL_COLUMNS
        null_rates = [row["null_rate"] for row in rows]
        assert null_rates == sorted(null_rates, reverse=True)
        assert set(rows[0]) == {"column", "dtype", "null_rate", "distinct_count"}
        # Chinook's only null-heavy column is BillingState (~49%).
        assert rows[0]["column"] == "BillingState"

    def test_query_result_previews_cap_rows_but_keep_full_counts(self, chinook_run):
        previews = demo_core.query_result_previews(chinook_run.query_results)
        assert len(previews) == 5
        grouped = next(p for p in previews if p["kpi_name"] == "Revenue by Country")
        assert grouped["status"] == "pass"
        assert len(grouped["preview_rows"]) == demo_core.PREVIEW_ROWS
        assert grouped["row_count"] > demo_core.PREVIEW_ROWS

    def test_pbip_file_inventory_lists_compiled_files(self, chinook_run):
        inventory = demo_core.pbip_file_inventory(chinook_run.pbip_dir)
        assert "chinook.pbip" in inventory
        assert any(name.endswith("data.tmdl") for name in inventory)
        assert demo_core.pbip_file_inventory(chinook_run.pbip_dir.parent / "nope") == []


# ---------------------------------------------------------------------------
# The Streamlit app (demo-only dependency: skipped when streamlit is absent)
# ---------------------------------------------------------------------------

class TestStreamlitApp:
    def _new_app(self):
        """Fresh AppTest per test: the app holds run results in session_state."""
        pytest.importorskip(
            "streamlit",
            reason="streamlit is a demo-only dependency (requirements-demo.txt), "
                   "not installed by requirements.txt / CI",
        )
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(REPO_ROOT / "app.py"), default_timeout=120)
        app.run()
        assert not app.exception
        return app

    def test_landing_view_offers_all_three_datasets(self):
        app = self._new_app()
        assert app.title[0].value == "Agentic BI Builder — Deterministic Demo"
        assert len(app.sidebar.selectbox[0].options) == 3
        assert app.sidebar.button[0].label == "Run profiler and compile"
        # Nothing is compiled until the button is pressed.
        assert len(app.get("download_button")) == 0

    def test_button_press_compiles_and_offers_the_pbip_download(self):
        app = self._new_app()
        app.sidebar.button[0].click().run()
        assert not app.exception
        metrics = {m.label: m.value for m in app.metric}
        assert metrics["Rows"] == "412"
        assert metrics["KPIs executed"] == "5"
        assert metrics["Pages"] == "2"
        assert metrics["Visuals"] == "5"
        assert not app.error
        assert len(app.get("download_button")) == 1
        # The absolute-path / Windows-Desktop caveat is shown next to the download.
        assert any("absolute" in warning.value for warning in app.warning)

    def test_dataset_selector_switches_the_compiled_report(self):
        app = self._new_app()
        app.sidebar.selectbox[0].set_value("HR Analytics — employee retention").run()
        app.sidebar.button[0].click().run()
        assert not app.exception
        metrics = {m.label: m.value for m in app.metric}
        assert metrics["Rows"] == "1,470"
        assert metrics["Pages"] == "3"
        assert metrics["Visuals"] == "5"
