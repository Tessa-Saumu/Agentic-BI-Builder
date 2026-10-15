"""Archive/serializer contract checks; these do not establish Desktop rendering."""
import base64
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from pbir.compiler.templates import _report_json, _model_tmdl, _definition_pbir_json, _definition_pbism_json, _theme_assets
from pbir.compiler.visual_json import _build_visual_json
from pbir.models.visual import Position, Visual

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def browser_project():
    node = shutil.which("node")
    if not node:
        pytest.skip("Browser export contract requires Node.js")
    script = """import {DEFAULT_CSV,parseCSV,profileCSV,generateOfflineSpec,runSpec} from './web-demo/engine.js';
const d=parseCSV(DEFAULT_CSV),s=generateOfflineSpec(profileCSV(d));s.kpis.push({name:'Country table',operation:'sum',column:'Total',groupBy:'BillingCountry',chart:'table'});const r=runSpec(d,s);console.log(JSON.stringify({files:r.files,spec:r.spec,zip:Buffer.from(r.zipBytes).toString('base64')}));"""
    return json.loads(subprocess.run([node, "--input-type=module", "-e", script], cwd=ROOT, check=True, capture_output=True, text=True).stdout)


def test_zip_roundtrip_preserves_report_model_and_data(browser_project, tmp_path):
    files = browser_project["files"]
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(browser_project["zip"]))) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(files)
        archive.extractall(tmp_path)
        for name, content in files.items():
            assert (tmp_path / name).read_bytes().decode("utf-8") == content
    root = json.loads((tmp_path / "BrowserDemo.pbip").read_text())
    report = tmp_path / root["artifacts"][0]["report"]["path"]
    definition = json.loads((report / "definition.pbir").read_text())
    model = (report / definition["datasetReference"]["byPath"]["path"]).resolve()
    assert (model / "definition.pbism").is_file()
    assert (model / "definition/tables/Data.tmdl").is_file()
    pages = json.loads((report / "definition/pages/pages.json").read_text())
    assert all((report / "definition/pages" / p / "page.json").is_file() for p in pages["pageOrder"])


def test_fixed_assets_match_original_python_serializer(browser_project):
    files = browser_project["files"]
    assert json.loads(files["BrowserDemo.Report/definition.pbir"]) == _definition_pbir_json("BrowserDemo.SemanticModel")
    assert json.loads(files["BrowserDemo.SemanticModel/definition.pbism"]) == _definition_pbism_json()
    assert json.loads(files["BrowserDemo.Report/definition/report.json"]) == _report_json()
    assert files["BrowserDemo.SemanticModel/definition/model.tmdl"] == _model_tmdl("Data")
    for relative, source in _theme_assets().items():
        assert json.loads(files["BrowserDemo.Report/StaticResources/SharedResources/" + relative]) == json.loads(source.read_text())


def test_all_four_visual_types_match_original_serializer(browser_project):
    files = browser_project["files"]
    types = {"card": "card", "bar": "barChart", "line": "lineChart", "table": "table"}
    columns = {"InvoiceDate": "c1", "BillingCountry": "c2", "Total": "c3"}
    covered = set()
    for i, kpi in enumerate(browser_project["spec"]["kpis"]):
        visual_id = f"visual{i + 1}"
        path = next(p for p in files if p.endswith(f"/{visual_id}/visual.json"))
        actual = json.loads(files[path])
        position = actual["position"]
        visual = Visual(visual_id=visual_id, chart_type=types[kpi["chart"]], title=kpi["name"], measure_ref=kpi["name"], category_ref=columns.get(kpi["groupBy"]), entity="Data", position=Position(**{**{k: v for k, v in position.items() if k != "tabOrder"}, "tab_order": position["tabOrder"]}))
        assert actual == _build_visual_json(visual, [kpi["name"]])
        covered.add(kpi["chart"])
    assert covered == set(types)


def test_path_preparation_validates_extraction_and_special_characters(browser_project, tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("Local path preparation requires PowerShell")
    dest = tmp_path / "O'Brien # report"
    dest.mkdir()
    for name, content in browser_project["files"].items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    command = [shell, "-NoProfile", "-File", str(dest / "prepare_report.ps1")]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    model = (dest / "BrowserDemo.SemanticModel/definition/tables/Data.tmdl").read_text()
    assert "C:/AgenticBIDemo/input.csv" not in model
    assert "#(#) report/input.csv" in model
    assert subprocess.run(command, capture_output=True).returncode == 0
    (dest / "BrowserDemo.Report/definition.pbir").unlink()
    failed = subprocess.run(command, capture_output=True, text=True)
    assert failed.returncode != 0
    assert "Extract All" in failed.stderr
