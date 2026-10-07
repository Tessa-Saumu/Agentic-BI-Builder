"""
End-to-end no-network regression tests for the Agentic BI Builder pipeline.

Exercises:
  - Full deterministic pipeline (profiler -> fixed KPI fixtures -> sql_executor
    -> mocked reflector -> sql_executor_retry -> pbir_compiler -> write_pbip)
    across all three reference datasets (chinook, online_retail, hr_analytics)
  - KPI drop semantics (both reflector no-fix drop and retry-failure drop)
  - Minimum-visuals build gate (rejects reports with < 4 translatable visuals)
  - Bounded repair-and-retry path (sabotaged KPI repaired by reflector and
    re-verified by sql_executor_retry)
  - run_agent.py CLI exit-code contract (0 on success, 1 on failure) and
    run_summary.json generation on both paths
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.models import (  # noqa: E402
    DomainHypothesis,
    DomainKPIResponse,
    KPISpec,
    ReflectionNote,
    ReflectionResponse,
)
from agent.profiler import run_profiler  # noqa: E402
from agent.reflector import run_reflector  # noqa: E402
from agent.sql_executor import run_sql_executor, run_sql_executor_retry  # noqa: E402
from agent.state import AgentState  # noqa: E402
from pbir.compiler.builder import run_pbir_compiler  # noqa: E402
from pbir.compiler.serialiser import write_pbip  # noqa: E402
import run_agent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_KPIS_DIR = Path(__file__).resolve().parent / "fixtures" / "kpis"


def _load_kpi_fixture(dataset_name: str) -> tuple[DomainHypothesis, list[KPISpec]]:
    fixture_path = FIXTURES_KPIS_DIR / f"{dataset_name}_kpis.json"
    with open(fixture_path, encoding="utf-8") as f:
        raw = json.load(f)
    domain = DomainHypothesis(**raw["domain_hypothesis"])
    kpis = [KPISpec(**k) for k in raw["kpi_specs"]]
    return domain, kpis


# ---------------------------------------------------------------------------
# Full deterministic pipeline across all three reference datasets
# ---------------------------------------------------------------------------

class TestEndToEndReferenceDatasets:
    @pytest.mark.parametrize(
        "dataset_name,expected_pages,expected_dax_substring",
        [
            ("chinook", 2, "SUM('data'[Total])"),
            ("online_retail", 2, "SUMX('data', 'data'[Quantity] * 'data'[UnitPrice])"),
            ("hr_analytics", 3, "AVERAGE('data'[JobSatisfaction])"),
        ],
    )
    def test_deterministic_pipeline_compiles_valid_pbip(
        self, dataset_name, expected_pages, expected_dax_substring, tmp_path
    ):
        csv_path = str(REPO_ROOT / "data" / "raw" / f"{dataset_name}.csv")
        out_dir = tmp_path / f"{dataset_name}_report"

        state = AgentState(input_path=csv_path, output_path=str(out_dir))
        state = run_profiler(state)
        assert state.errors == []
        assert state.data_profile is not None

        domain, kpis = _load_kpi_fixture(dataset_name)
        state.domain_hypothesis = domain
        state.kpi_specs = kpis

        state = run_sql_executor(state)
        assert state.errors == []
        assert len(state.query_results) == 5
        assert all(qr.status == "pass" for qr in state.query_results)

        with patch(
            "agent.reflector._call_reflection_llm",
            return_value=ReflectionResponse(notes=[]),
        ):
            state = run_reflector(state, dataset_name=dataset_name)
        assert state.errors == []
        assert state.kpis_to_retry == []

        state = run_pbir_compiler(state)
        assert state.errors == []
        assert state.pbir_project is not None

        project = state.pbir_project
        assert len(project.pages) == expected_pages
        total_visuals = sum(len(p.visuals) for p in project.pages)
        assert total_visuals == 5
        assert len(project.data_table.measures) == 5

        write_pbip(project, out_dir)

        pbip_file = out_dir / f"{dataset_name}.pbip"
        report_dir = out_dir / f"{dataset_name}.Report"
        semantic_dir = out_dir / f"{dataset_name}.SemanticModel"
        tmdl_file = semantic_dir / "definition" / "tables" / "data.tmdl"

        assert pbip_file.is_file()
        assert (report_dir / "definition" / "pages" / "pages.json").is_file()
        assert tmdl_file.is_file()

        tmdl_text = tmdl_file.read_text(encoding="utf-8")
        measure_blocks = re.findall(r"^\tmeasure\s+", tmdl_text, flags=re.MULTILINE)
        assert len(measure_blocks) == 5
        assert expected_dax_substring in tmdl_text

        # M partition must embed an absolute path inside File.Contents("...")
        m_file_match = re.search(r'File\.Contents\("([^"]+)"\)', tmdl_text)
        assert m_file_match is not None
        embedded_path = m_file_match.group(1)
        assert os.path.isabs(embedded_path)
        assert embedded_path.endswith(f"{dataset_name}.csv")

    def test_chinook_verified_headline_numbers_match(self):
        csv_path = str(REPO_ROOT / "data" / "raw" / "chinook.csv")
        state = AgentState(input_path=csv_path, output_path="output/chinook_report")
        state = run_profiler(state)
        domain, kpis = _load_kpi_fixture("chinook")
        state.domain_hypothesis = domain
        state.kpi_specs = kpis
        state = run_sql_executor(state)

        results_by_name = {qr.kpi_name: qr for qr in state.query_results}
        total_rev = results_by_name["Total Revenue"].result_rows[0]["total_revenue"]
        avg_tracks = results_by_name["Average Tracks per Invoice"].result_rows[0][
            "avg_tracks_per_invoice"
        ]
        assert total_rev == pytest.approx(2328.60, abs=1e-2)
        assert round(avg_tracks, 2) == pytest.approx(5.44, abs=1e-2)


# ---------------------------------------------------------------------------
# KPI drop, repair-and-retry, and min-visual build gate
# ---------------------------------------------------------------------------

class TestRepairDropAndBuildGate:
    def test_unfixable_kpi_is_dropped_and_excluded_from_report(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        csv_path = str(REPO_ROOT / "data" / "raw" / "chinook.csv")
        out_dir = tmp_path / "chinook_drop_report"

        state = AgentState(input_path=csv_path, output_path=str(out_dir))
        state = run_profiler(state)
        domain, kpis = _load_kpi_fixture("chinook")

        # Sabotage the 5th KPI with a nonexistent column
        kpis[4] = kpis[4].model_copy(
            update={
                "name": "Broken Artist KPI",
                "sql_query": "SELECT NonExistentColumn, SUM(Total) AS rev FROM data GROUP BY NonExistentColumn",
            }
        )
        state.domain_hypothesis = domain
        state.kpi_specs = kpis
        state = run_sql_executor(state)

        # Reflector flags it with fixed_sql_query=None (unfixable)
        unfixable_response = ReflectionResponse(
            notes=[
                ReflectionNote(
                    kpi_name="Broken Artist KPI",
                    issue_type="sql_error",
                    description="Column NonExistentColumn does not exist and cannot be inferred.",
                    fix_instruction="Drop KPI; no valid column mapping.",
                    fixed_sql_query=None,
                )
            ]
        )
        with patch(
            "agent.reflector._call_reflection_llm", return_value=unfixable_response
        ):
            state = run_reflector(state, dataset_name="chinook")

        assert state.kpis_to_retry == []
        assert len(state.kpi_specs) == 4
        assert "Broken Artist KPI" not in {k.name for k in state.kpi_specs}

        state = run_pbir_compiler(state)
        assert state.errors == []
        assert state.pbir_project is not None
        measure_names = {m.name for m in state.pbir_project.data_table.measures}
        assert "Broken Artist KPI" not in measure_names
        assert len(measure_names) == 4

    def test_kpi_still_failing_after_retry_is_dropped_from_report(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        csv_path = str(REPO_ROOT / "data" / "raw" / "chinook.csv")
        out_dir = tmp_path / "chinook_retry_drop"

        state = AgentState(input_path=csv_path, output_path=str(out_dir))
        state = run_profiler(state)
        domain, kpis = _load_kpi_fixture("chinook")

        kpis[4] = kpis[4].model_copy(
            update={
                "name": "Broken Retry KPI",
                "sql_query": "SELECT BadCol1, SUM(Total) AS rev FROM data GROUP BY BadCol1",
            }
        )
        state.domain_hypothesis = domain
        state.kpi_specs = kpis
        state = run_sql_executor(state)

        # Reflector offers a fix that STILL references a nonexistent column
        bad_fix_response = ReflectionResponse(
            notes=[
                ReflectionNote(
                    kpi_name="Broken Retry KPI",
                    issue_type="sql_error",
                    description="BadCol1 does not exist.",
                    fix_instruction="Try BadCol2 instead.",
                    fixed_sql_query="SELECT BadCol2, SUM(Total) AS rev FROM data GROUP BY BadCol2",
                )
            ]
        )
        with patch(
            "agent.reflector._call_reflection_llm", return_value=bad_fix_response
        ):
            state = run_reflector(state, dataset_name="chinook")

        assert state.kpis_to_retry == ["Broken Retry KPI"]
        state = run_sql_executor_retry(state)
        assert state.kpis_to_retry == []
        assert "Broken Retry KPI" not in {k.name for k in state.kpi_specs}

        state = run_pbir_compiler(state)
        assert state.errors == []
        assert state.pbir_project is not None
        measure_names = {m.name for m in state.pbir_project.data_table.measures}
        assert "Broken Retry KPI" not in measure_names
        assert len(measure_names) == 4

    def test_repair_and_retry_recovers_sabotaged_kpi_into_final_report(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        csv_path = str(REPO_ROOT / "data" / "raw" / "chinook.csv")
        out_dir = tmp_path / "chinook_repaired_report"

        state = AgentState(input_path=csv_path, output_path=str(out_dir))
        state = run_profiler(state)
        domain, kpis = _load_kpi_fixture("chinook")

        original_sql = kpis[0].sql_query
        kpis[0] = kpis[0].model_copy(
            update={"sql_query": "SELECT SUM(TotalsTypo) AS total_revenue FROM data"}
        )
        state.domain_hypothesis = domain
        state.kpi_specs = kpis

        state = run_sql_executor(state)
        assert state.query_results[0].status == "fail"

        repair_response = ReflectionResponse(
            notes=[
                ReflectionNote(
                    kpi_name="Total Revenue",
                    issue_type="sql_error",
                    description="Column TotalsTypo does not exist; column is Total.",
                    fix_instruction="Replace TotalsTypo with Total.",
                    fixed_sql_query=original_sql,
                )
            ]
        )
        with patch(
            "agent.reflector._call_reflection_llm", return_value=repair_response
        ):
            state = run_reflector(state, dataset_name="chinook")

        assert state.kpis_to_retry == ["Total Revenue"]
        assert state.kpi_specs[0].sql_query == original_sql

        state = run_sql_executor_retry(state)
        assert state.kpis_to_retry == []
        repaired_qr = next(
            qr for qr in state.query_results if qr.kpi_name == "Total Revenue"
        )
        assert repaired_qr.status == "pass"

        state = run_pbir_compiler(state)
        assert state.errors == []
        assert state.pbir_project is not None
        measure_names = {m.name for m in state.pbir_project.data_table.measures}
        assert "Total Revenue" in measure_names
        assert len(measure_names) == 5

    def test_min_visual_gate_rejects_build_when_only_two_kpis_translatable(self):
        csv_path = str(REPO_ROOT / "data" / "raw" / "chinook.csv")
        state = AgentState(input_path=csv_path, output_path="output/chinook_thin")
        state = run_profiler(state)
        domain, kpis = _load_kpi_fixture("chinook")

        # Keep 2 valid translatable KPIs; replace the other 3 with SQL that
        # executes in SQLite but uses an unsupported DAX translation shape.
        for idx in (2, 3, 4):
            kpis[idx] = kpis[idx].model_copy(
                update={
                    "sql_query": f"SELECT MAX(Total) - MIN(Total) AS spread_{idx} FROM data",
                    "chart_type": "card",
                }
            )
        state.domain_hypothesis = domain
        state.kpi_specs = kpis
        state = run_sql_executor(state)
        assert all(qr.status == "pass" for qr in state.query_results)

        state = run_pbir_compiler(state)
        assert state.pbir_project is None
        assert any("only 2 KPI(s) produced a translatable measure" in e for e in state.errors)


# ---------------------------------------------------------------------------
# run_agent.py CLI exit codes and run_summary.json contract (G7, G18)
# ---------------------------------------------------------------------------

class TestRunAgentCliAndSummary:
    def test_build_run_summary_contains_required_fields_on_chinook(self, tmp_path):
        csv_path = str(REPO_ROOT / "data" / "raw" / "chinook.csv")
        out_dir = tmp_path / "chinook_summary_test"

        state = AgentState(input_path=csv_path, output_path=str(out_dir))
        state = run_profiler(state)
        domain, kpis = _load_kpi_fixture("chinook")
        state.domain_hypothesis = domain
        state.kpi_specs = kpis
        state = run_sql_executor(state)
        state = run_pbir_compiler(state)
        write_pbip(state.pbir_project, out_dir)
        state.node_timings = {
            "profiler": 0.02,
            "domain_kpi": 0.0,
            "sql_executor": 0.01,
            "reflector": 0.0,
            "pbir_compiler": 0.01,
        }

        args = argparse.Namespace(input=csv_path, output=str(out_dir))
        summary = run_agent._build_run_summary(state, args, report_written=True)

        required_keys = {
            "dataset_name",
            "input_path",
            "input_path_sha256",
            "timestamp_utc",
            "python_version",
            "package_versions",
            "provider",
            "model",
            "model_fallback",
            "temperature",
            "kpi_count_initial",
            "kpi_count_final",
            "kpi_names_initial",
            "kpi_names_final",
            "kpis_dropped",
            "reflection_notes_count",
            "reflection_fixes_applied",
            "reflection_dropped_without_fix",
            "node_timings_seconds",
            "total_seconds",
            "errors",
            "report_written",
            "page_count",
            "visual_count",
            "pbip_output_dir",
        }
        assert required_keys.issubset(summary.keys())
        assert summary["dataset_name"] == "chinook"
        assert summary["input_path"] == "chinook.csv"
        assert isinstance(summary["input_path_sha256"], str)
        assert len(summary["input_path_sha256"]) == 12
        assert summary["kpi_count_initial"] == 5
        assert summary["kpi_count_final"] == 5
        assert summary["kpis_dropped"] == []
        assert summary["report_written"] is True
        assert summary["page_count"] == 2
        assert summary["visual_count"] == 5
        assert summary["errors"] == []

    def test_cli_main_exits_zero_and_writes_summary_on_success(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        csv_path = str(REPO_ROOT / "data" / "raw" / "chinook.csv")
        out_dir = tmp_path / "cli_success_out"

        domain, kpis = _load_kpi_fixture("chinook")
        domain_response = DomainKPIResponse(domain_hypothesis=domain, kpi_specs=kpis)
        reflection_response = ReflectionResponse(notes=[])

        monkeypatch.setattr(
            sys, "argv", ["run_agent.py", "--input", csv_path, "--output", str(out_dir)]
        )
        with patch("agent.domain_kpi.call_llm", return_value=domain_response), patch(
            "agent.reflector._call_reflection_llm", return_value=reflection_response
        ):
            with pytest.raises(SystemExit) as exc_info:
                run_agent.main()

        assert exc_info.value.code == 0
        summary_file = out_dir / "run_summary.json"
        assert summary_file.is_file()
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        assert summary["report_written"] is True
        assert summary["errors"] == []
        assert summary["visual_count"] == 5

    def test_cli_main_exits_nonzero_and_writes_summary_on_failure(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        missing_csv = str(tmp_path / "does_not_exist.csv")
        out_dir = tmp_path / "cli_fail_out"

        monkeypatch.setattr(
            sys,
            "argv",
            ["run_agent.py", "--input", missing_csv, "--output", str(out_dir)],
        )
        with pytest.raises(SystemExit) as exc_info:
            run_agent.main()

        assert exc_info.value.code == 1
        summary_file = out_dir / "run_summary.json"
        assert summary_file.is_file()
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        assert summary["report_written"] is False
        assert len(summary["errors"]) > 0
