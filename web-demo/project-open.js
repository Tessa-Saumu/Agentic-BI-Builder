// Runs locally only after the complete ZIP has been extracted.
export const PREPARE_REPORT_PS1 = String.raw`param([switch]$Open)
$ErrorActionPreference = 'Stop'
$report = Join-Path $PSScriptRoot 'BrowserDemo.pbip'
$definition = Join-Path $PSScriptRoot 'BrowserDemo.Report/definition.pbir'
$model = Join-Path $PSScriptRoot 'BrowserDemo.SemanticModel/definition/tables/Data.tmdl'
$csv = Join-Path $PSScriptRoot 'input.csv'
foreach ($path in @($report, $definition, $model, $csv)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw 'The complete project is missing. Right-click the downloaded ZIP, choose Extract All, and run this script from the extracted folder. Do not open the PBIP inside the ZIP.'
    }
}
$csvPath = [IO.Path]::GetFullPath($csv).Replace('\', '/').Replace('#', '#(#)').Replace('"', '""')
$text = [IO.File]::ReadAllText($model)
$placeholder = 'C:/AgenticBIDemo/input.csv'
if ($text.Contains($placeholder)) {
    $text = $text.Replace($placeholder, $csvPath)
    [IO.File]::WriteAllText($model, $text, [Text.UTF8Encoding]::new($false))
    Write-Output "CSV path prepared: $csv"
} elseif ($text.Contains($csvPath)) {
    Write-Output 'CSV path already prepared.'
} else {
    throw 'The CSV path was edited manually. Check File.Contents in the model before opening; this script will not overwrite that edit.'
}
Write-Output "Open the extracted project in Power BI Desktop, then refresh: $report"
if ($Open) { Invoke-Item -LiteralPath $report }
`;
