"""Export a checked fictional-data walkthrough without exposing source or supplied datasets."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from demo_core import DATASETS, DemoDataset, run_demo


def export(destination: Path) -> dict:
    """Compile hand-written KPI specifications over12 fictional invoices; validate totals."""
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / 'sample.csv'
    rows = [dict(InvoiceDate=f'2026-{month:02d}-{5+i:02d}', BillingCountry=country,
                 Total=float(10*month+i+2*c), distinct_tracks_purchased=2+i+c,
                 primary_artist=f'Artist {chr(65+i)}')
            for month in range(1, 4) for c, country in enumerate(['Kenya', 'Ghana'])
            for i in range(2)]
    with csv_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    specs = [
        ('Total Revenue', 'SUM(Total) AS total_revenue', '', 'card'),
        ('Revenue by Country', 'BillingCountry, SUM(Total) AS revenue', ' GROUP BY BillingCountry ORDER BY revenue DESC', 'barChart'),
        ('Monthly Revenue Trend', "strftime('%Y-%m', InvoiceDate) AS month, SUM(Total) AS revenue", ' GROUP BY month ORDER BY month', 'lineChart'),
        ('Average Tracks per Invoice', 'AVG(distinct_tracks_purchased) AS avg_tracks_per_invoice', '', 'card'),
        ('Top Artists by Revenue', 'primary_artist, SUM(Total) AS revenue', ' GROUP BY primary_artist ORDER BY revenue DESC LIMIT10', 'barChart'),
    ]
    # Space in LIMIT is SQL syntax, not a branding/provider prompt.
    fixture = {'domain_hypothesis': {'domain': 'fictional music retail', 'confidence':1.0,
                'reasoning': 'Explicit example label, not an AI prediction.'},
               'kpi_specs': [dict(name=name, description='Illustration metric computed from fictional invoices.',
                sql_query=f'SELECT {expression} FROM data{suffix}'.replace('LIMIT10', 'LIMIT 10'),
                chart_type=chart, reasoning='Hand-written for this public deterministic illustration.')
                for name, expression, suffix, chart in specs]}
    fixture_path = destination / 'example_kpis.json'
    fixture_path.write_text(json.dumps(fixture, indent=2) + '\n', encoding='utf-8')
    DATASETS['public_illustration'] = DemoDataset(
        key='public_illustration', label='Fictional music shop', csv_path=csv_path,
        kpi_fixture_path=fixture_path, screenshot_dir=destination,
        fixture_provenance='Hand-written specifications; fictional data; no live AI call.')
    result = run_demo('public_illustration', workdir=destination / 'example_report')
    if not result.succeeded or result.visual_count !=5:
        raise RuntimeError(f'Fictional-data build failed: {result.errors}')
    queries = [q.model_dump(mode='json') for q in result.query_results]
    revenue = next(q for q in result.query_results if q.kpi_name == 'Total Revenue')
    if revenue.result_rows[0]['total_revenue'] !=258.0:
        raise RuntimeError('Independent invoice-total check failed')
    averages = next(q for q in result.query_results if q.kpi_name == 'Average Tracks per Invoice')
    if averages.result_rows[0]['avg_tracks_per_invoice'] !=3.0:
        raise RuntimeError('Independent average-track check failed')
    # Relocation is explicit and documented: no developer-machine path escapes publicly.
    old_paths = {str(csv_path), csv_path.as_posix()}
    for path in result.pbip_dir.rglob('*'):
        if path.is_file():
            text = path.read_text(encoding='utf-8')
            for old in old_paths:
                text = text.replace(old, 'C:/AgenticBIDemo/sample.csv')
            path.write_text(text, encoding='utf-8')
    public_zip = destination / 'example-project.zip'
    with zipfile.ZipFile(public_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(result.pbip_dir.rglob('*')):
            if path.is_file():
                archive.write(path, 'example_report/' + path.relative_to(result.pbip_dir).as_posix())
        archive.write(csv_path, 'sample.csv')
        archive.writestr('OPEN_IN_POWER_BI.txt',
            'Fictional deterministic illustration. No AI call or business-performance claim.\n'
            'Windows + Power BI Desktop required. Save sample.csv as C:\\AgenticBIDemo\\sample.csv,\n'
            'open the .pbip in example_report and click Refresh. Alternatively edit the CSV\n'
            'File.Contents path in the semantic model TMDL table file to your actual sample.csv.\n'
            'This export was structurally checked; it was not freshly opened in Desktop.\n')
    with zipfile.ZipFile(public_zip) as archive:
        assert archive.testzip() is None
        assert any(name.endswith('.pbip') for name in archive.namelist())
        joined = b'\n'.join(archive.read(name) for name in archive.namelist())
        assert b'C:/AgenticBIDemo/sample.csv' in joined
        assert b'Users/ingex' not in joined and b'Users\\ingex' not in joined
    receipt = {'scope': 'Prebuilt deterministic illustration, not a live AI run or a Desktop verification',
               'data': '12 newly generated fictional invoices; currency units unspecified',
               'rows':12, 'total_revenue':258.0, 'average_tracks':3.0,
               'pages':result.page_count, 'visuals':result.visual_count,
               'kpis':fixture['kpi_specs'], 'query_results':queries,
               'sample_sha256':hashlib.sha256(csv_path.read_bytes()).hexdigest(),
               'zip_sha256':hashlib.sha256(public_zip.read_bytes()).hexdigest()}
    (destination / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    # Source-generated intermediate report/zip is not part of the public static surface.
    assert result.pbip_dir.resolve().parent == destination.resolve()
    assert result.pbip_dir.name == 'example_report'
    shutil.rmtree(result.pbip_dir)
    assert result.zip_path.resolve().parent == destination.resolve()
    if result.zip_path != public_zip:
        result.zip_path.unlink()
    return receipt


def main() -> None:
    """Write public artifacts to the requested output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = export(args.output.resolve())
    print(json.dumps({key:receipt[key] for key in ['rows', 'pages', 'visuals', 'total_revenue', 'average_tracks']}))


if __name__ == '__main__':
    main()
