# Browser demo

I built this static demo so someone can upload a CSV, inspect calculated metrics and download editable Power BI project files without installing the Python application.

[Open the hosted demo](https://tessa-agentic-bi-evidence.purple-tick-2127.chatgpt.site).

## Try a report

1. Keep the default 12 fictional invoices or choose a CSV smaller than 5 MB. The sample is my fictional data, not the Chinook dataset.
2. Leave the API key empty for local simulation, or enter a Google AI Studio Gemini key to ask Google to propose a report plan. The planner infers descriptive metrics from the column profile; there is no free-text request step in the original application.
3. Build the report, inspect the metric results and plan, then download the project ZIP, input CSV and run receipt.
4. Right-click the downloaded ZIP and choose **Extract All**. Opening the `.pbip` inside the compressed folder extracts only that pointer file; the report and model folders must be beside it. Run `prepare_report.ps1` from the extracted folder to update the CSV path automatically, or save `input.csv` as `C:\AgenticBIDemo\input.csv`, creating the folder, or change `File.Contents` in `BrowserDemo.SemanticModel/definition/tables/Data.tmdl` to your CSV path.
5. Open `BrowserDemo.pbip` in Windows Power BI Desktop and refresh. Follow the included `OPEN_IN_POWER_BI.txt` instructions if your Desktop version requires project preview settings.

The download is a Power BI Project (`.pbip`): editable source files for the report and data model. It is not a `.pbix` binary. Power BI recalculates the measures when you refresh the CSV. On 15 October 2026, the repaired fictional sample was opened and refreshed in Power BI Desktop: 12 rows, total 258, average 21.5 and a rendered country chart. Its published ZIP matched the native-checked project. This verifies that sample, not arbitrary reports.

## How the two modes work

**Local simulation:** JavaScript inspects the columns, chooses a deterministic plan, calculates the metrics and builds a new ZIP from the selected CSV. No AI or provider call occurs. No natural-language request is accepted.

**Online:** the browser sends the disclosed column profile directly to Gemini. It requests a structured plan, checks that its fields and calculations are supported, and allows one repair request if the plan fails those checks. The same local calculation and export code then executes the accepted plan. Provider failures remain visible errors; no simulated result is presented as a successful AI run.

Both modes support four to eight metrics, using sum, average, count, minimum, maximum or distinct count. Charts can be cards, bars, lines or tables. Groupings are limited to 500 distinct values. The browser preview shows grouped values as bars or tables; the downloaded report uses the declared chart type. This is a constrained single-table adapter, not the full Python/LangGraph workflow: it does not run arbitrary SQL, join tables or ask AI to review sampled result rows.

## What leaves the browser

The CSV rows remain local. Online mode sends Google:

- Row count and column names/types.
- Missing-value and distinct-value counts for each column.

It sends no CSV row samples or minimum/maximum values. The page lets you inspect that payload before running. Names and counts can still disclose information, so choose data you are comfortable describing to Google.

The API key is held in page memory, sent directly to Google in the `x-goog-api-key` request header, and cleared after each run. It is not saved in browser storage or sent to this site's host. Google's normal account limits and billing apply to the visitor's key. No app-owned key or backend proxy is needed for this demo.

## Run and test locally

From the repository root:

```bash
python -m http.server 8000 --directory web-demo
```

Open `http://localhost:8000`. Serve the files over HTTP rather than opening `index.html` as a local file, because JavaScript modules require a suitable origin.

With Node.js installed, run the engine and provider tests:

```bash
node --test web-demo/engine.test.mjs web-demo/provider.test.mjs
```

Tests use controlled provider responses. A browser-to-Google connection preflight was checked; a successful generation using a valid visitor API key has not been verified. Tests establish software behavior rather than AI metric quality or Power BI Desktop rendering.

## Deployment and scope

The directory is a static site: its files can be hosted without a Python backend. The complete Python application still needs a Python host to run its existing profiler, SQLite executor, LangGraph review and compiler. The browser demo demonstrates the narrower upload → plan → calculate → export flow.

The run receipt records the selected mode, input profile, metric plan, results and limitations. Inspect the plan for useful business meaning; a valid calculation alone does not establish that a metric answers your question.

## Report opening regression check (2026-10-15)

The exact ZIP cited in the error (`AgenticBI-project (2).zip`) contains `BrowserDemo.Report/definition.pbir`, and every entry passes its CRC check. The error points to a temporary `*.zip.aad` path, consistent with opening the pointer inside the compressed folder instead of extracting all files. This is a diagnosis from the error path and archive contents, not a Power BI Desktop rendering verification. The download now includes a local path preparation script and more explicit extraction instructions.

The Python serializer, fixed templates and visual JSON renderer have not changed since the pre-portfolio audit baseline. The browser exporter is a separate JavaScript implementation and does not invoke those Python modules. Its output is checked against the original serializer templates and the complete archive is independently extracted in regression tests.
