# PBIR Format Reference

Reverse-engineered from `minimal_report` — a 2-page, 3-visual Power BI report
(pivot table, clustered column chart, card) over a single imported table (`in`,
from `Health_Dirty.xlsx`, a healthcare visits dataset) with one auto-generated
local date table.

This document is the spec the PBIR Compiler node codes against. For every file:
what the keys mean, which are required, how deep the nesting goes, and —
critically — which values are **fixed** (same on every run) vs **dynamic**
(must be generated per dataset/KPI by the agent).

---

## 1. Folder structure

```
<name>.pbip                              ← root pointer file
<name>.Report/
  .platform                              ← Fabric metadata, fixed
  definition.pbir                        ← points Report → SemanticModel
  .pbi/localSettings.json                ← machine-local, EXCLUDE
  definition/
    report.json                          ← theme + report-level settings
    version.json                         ← schema version pin
    pages/
      pages.json                         ← page order + active page
      <pageId>/
        page.json                        ← one per page
        visuals/
          <visualId>/
            visual.json                  ← one per visual
  StaticResources/SharedResources/
    BaseThemes/<name>.json                ← MS-shipped, fixed, copy verbatim
    BuiltInThemes/<name>.json             ← MS-shipped, fixed, copy verbatim
<name>.SemanticModel/
  .platform                              ← Fabric metadata, fixed
  definition.pbism                       ← near-empty, fixed
  .pbi/{cache.abf,editorSettings.json,localSettings.json}  ← EXCLUDE all
  diagramLayout.json                     ← model-diagram canvas, EXCLUDE
  definition/
    database.tmdl                        ← 2 lines, fixed
    model.tmdl                           ← table refs, mostly fixed
    relationships.tmdl                   ← one line per date relationship
    cultures/en-US.tmdl                  ← auto-generated Q&A linguistics, EXCLUDE
    tables/
      <YourTable>.tmdl                   ← schema + M query + DAX measures — THE core dynamic file
      LocalDateTable_<guid>.tmdl         ← auto-generated per date column, template-fixed
      DateTableTemplate_<guid>.tmdl      ← auto-generated once per model, template-fixed
```

Two independent "documents" (`.Report` and `.SemanticModel`) linked only by
the relative path in `definition.pbir`. The compiler can build them as two
separate phases.

---

## 2. File-by-file reference

### 2.1 `<name>.pbip` (root)

```json
{
  "version": "1.0",
  "artifacts": [{ "report": { "path": "<name>.Report" } }],
  "settings": { "enableAutoRecovery": true }
}
```

| Field | Required | Fixed/Dynamic | Notes |
|---|---|---|---|
| `version` | yes | fixed | `"1.0"` |
| `artifacts[0].report.path` | yes | **dynamic** | must equal `<name>.Report` folder name |
| `settings.enableAutoRecovery` | no | fixed | `true` |

Nesting depth: 2.

---

### 2.2 `<name>.Report/.platform`

```json
{
  "$schema": "...platformProperties/2.0.0/schema.json",
  "metadata": { "type": "Report", "displayName": "minimal_report" },
  "config": { "version": "2.0", "logicalId": "<guid>" }
}
```

| Field | Required | Fixed/Dynamic |
|---|---|---|
| `$schema` | yes | fixed |
| `metadata.type` | yes | fixed (`"Report"`) |
| `metadata.displayName` | yes | **dynamic** — set to dataset/report name |
| `config.version` | yes | fixed (`"2.0"`) |
| `config.logicalId` | yes | **dynamic** — generate a fresh GUID per report |

Nesting depth: 2. Identical structure (with `type: "SemanticModel"`) appears
in the SemanticModel's `.platform`.

---

### 2.3 `<name>.Report/definition.pbir`

```json
{
  "version": "4.0",
  "datasetReference": { "byPath": { "path": "../<name>.SemanticModel" } }
}
```

| Field | Required | Fixed/Dynamic |
|---|---|---|
| `version` | yes | fixed |
| `datasetReference.byPath.path` | yes | **dynamic** — must match SemanticModel folder, sibling-relative |

This is the load-bearing link between Report and SemanticModel. There's also
a `byConnection` variant (for live/published datasets) we don't need for a
locally-generated import-mode model — `byPath` is correct for this use case.

---

### 2.4 `<name>.Report/definition/report.json`

Top-level keys: `$schema`, `themeCollection`, `objects`, `resourcePackages`, `settings`.

| Field | Required | Fixed/Dynamic | Notes |
|---|---|---|---|
| `themeCollection.baseTheme.name` | yes | fixed | `"CY26SU05"` (current default MS theme — should be treated as a versioned constant the compiler pins) |
| `themeCollection.customTheme.name` | yes | fixed (or a chosen constant) | `"AccessibleCityPark"` — one of MS's built-in named themes |
| `themeCollection.*.reportVersionAtImport` | yes | fixed | tool-version stamps, copy verbatim |
| `objects.section[0].properties.verticalAlignment` | no | fixed | cosmetic default |
| `resourcePackages[0].items[*].path` | yes | fixed | must match the actual file under `StaticResources/SharedResources/...` |
| `settings.*` | yes (block) | fixed | export/drill/tooltip behavior flags — sane defaults, no need to vary per dataset |

Nesting depth: 4 (`objects.section[0].properties.X.expr.Literal.Value`).
**Compiler action: treat this file as a static template, copy as-is.** Theme
choice could become a dynamic parameter later (e.g. light/dark by domain) but
isn't required for a working report.

---

### 2.5 `<name>.Report/definition/version.json`

```json
{ "$schema": "...versionMetadata/1.0.0/schema.json", "version": "2.0.0" }
```

Fully fixed. Depth 1.

---

### 2.6 `<name>.Report/definition/pages/pages.json`

```json
{
  "$schema": "...pagesMetadata/1.1.0/schema.json",
  "pageOrder": ["3e33d29435230b0ab08c", "e064e67524ee9420eb6e"],
  "activePageName": "3e33d29435230b0ab08c"
}
```

| Field | Required | Fixed/Dynamic |
|---|---|---|
| `pageOrder` | yes | **dynamic** — array of page folder names, one entry per page the compiler creates |
| `activePageName` | yes | **dynamic** — must be one of `pageOrder`; default to first page |

This is the **only file that knows how many pages exist and in what order.**
The compiler must regenerate this every run.

---

### 2.7 `<pageId>/page.json` (one per page)

```json
{
  "$schema": "...page/2.1.0/schema.json",
  "name": "3e33d29435230b0ab08c",
  "displayName": "Visuals",
  "displayOption": "FitToPage",
  "height": 720,
  "width": 1280,
  "objects": { "background": [ ... ThemeDataColor + transparency ... ] }
}
```

| Field | Required | Fixed/Dynamic |
|---|---|---|
| `name` | yes | **dynamic** — must equal the containing folder name exactly (16–20 char hex-ish ID, see §3) |
| `displayName` | yes | **dynamic** — human label shown as the page tab (e.g. KPI category name) |
| `displayOption` | yes | fixed (`"FitToPage"`) |
| `height` / `width` | yes | fixed (`720` / `1280` — standard 16:9 canvas) |
| `objects.background` | no | fixed cosmetic default; safe to omit entirely (Power BI falls back to theme default) |

Nesting depth: 3 (`objects.background[0].properties.color.expr.ThemeDataColor`).
**One folder per page, named identically to `page.json`'s `name` field.**

---

### 2.8 `<visualId>/visual.json` (one per visual) — the core dynamic artifact

This is the file your KPI → chart mapping actually compiles into. Structure
common to all three visual types observed:

```json
{
  "$schema": "...visualContainer/2.10.0/schema.json",
  "name": "<visualId>",
  "position": { "x": .., "y": .., "z": .., "height": .., "width": .., "tabOrder": .. },
  "visual": {
    "visualType": "<pivotTable|clusteredColumnChart|cardVisual|...>",
    "query": { "queryState": { ... }, "sortDefinition": { ... } },
    "objects": { ... visual-specific formatting ... },
    "visualContainerObjects": { ... container chrome: title/border/background ... },
    "drillFilterOtherVisuals": true
  }
}
```

#### `position` block — required, fully dynamic

| Field | Type | Notes |
|---|---|---|
| `x`, `y` | float | top-left corner in canvas px |
| `z` | float | stacking order; `0` for first visual on a page, increments (we saw `1000`) for later ones |
| `height`, `width` | float | visual box size |
| `tabOrder` | int | keyboard nav order; tracks `z` in our sample |

Compiler must lay these out (grid/auto-layout logic — not reverse-engineered
here, but values are unconstrained floats so any non-overlapping layout works).

#### `visual.visualType` — required, dynamic (enum-like)

Observed values: `"pivotTable"`, `"clusteredColumnChart"`, `"cardVisual"`.
This is effectively the chart-type the KPI/Domain node already outputs —
direct mapping needed from your KPI schema's `chart_type` field to Power BI's
visual type strings. (Not exhaustively catalogued here — only the 3 types
present in this sample are confirmed; others like `lineChart`, `table`,
`slicer` will need confirming against a real export before the compiler
claims to support them.)

#### `visual.query.queryState` — required, fully dynamic

This is **where field bindings live** — the actual connection between a
visual and your semantic model's columns/measures. Structure varies by
visual type but follows one pattern:

- Each "role" (`Category`, `Rows`, `Values`, `Y`, `Data`, etc. — role names
  are visual-type-specific, e.g. column charts use `Category`/`Y`, cards use
  `Data`, pivot tables use `Rows`/`Values`) holds a `projections` array.
- Each projection has a `field` that is **either**:
  - `{ "Column": { "Expression": { "SourceRef": { "Entity": "<table>" } }, "Property": "<column>" } }` — binds a raw column, or
  - `{ "Measure": { "Expression": { "SourceRef": { "Entity": "<table>" } }, "Property": "<measure name>" } }` — binds a DAX measure, or
  - `{ "NativeVisualCalculation": { "Language": "dax", "Expression": "<DAX>", "Name": "<label>" } }` — an inline visual-level calc (seen in the pivot table, wrapping a base measure in `EXPANDALL(...)`)
- `queryRef`: a string ID, conventionally `"<Entity>.<Property>"` for column/measure refs, or a synthetic name (`"select"`) for native calcs.
- `nativeQueryRef`: display label for the field, usually just `<Property>`.
- `active: true` marks the "driving" field in a role with multiple projections.
- `hidden: true` + `displayName` appears when a measure is pulled in only as
  a dependency for a `NativeVisualCalculation` (the pivot table's
  `Total Cost_Base` is a hidden helper feeding the visible `Total Cost`
  calc) — **this pattern only appears when wrapping a measure in a visual
  calc; simple bindings don't need it.**

`sortDefinition.sort[]` — required for predictable output, references a
field the same way (`Measure`/`Column` + `Expression.SourceRef.Entity` +
`Property`) plus `direction: "Ascending"|"Descending"`. `isDefaultSort: true`
appeared on 2 of 3 visuals (column chart, card) but not the pivot table —
likely tied to whether the user manually re-sorted in the Desktop UI; **safe
to always include it**, since `false`/absent is the same as not present.

Nesting depth here reaches **6–7 levels**
(`visual.query.queryState.<Role>.projections[0].field.Measure.Expression.SourceRef.Entity`).
This is the deepest nesting in the whole format and the part most worth
unit-testing in isolation.

#### `visual.objects` and `visual.visualContainerObjects` — optional, fixed-with-overrides

Both follow the same recurring shape throughout the entire format (see §4 —
this pattern repeats in `page.json` and `report.json` too):

```json
"<propertyGroup>": [
  {
    "properties": {
      "<propName>": { "expr": { "Literal": { "Value": "<stringified-literal>" } } }
      // or: { "solid": { "color": { "expr": { "ThemeDataColor": { "ColorId": N, "Percent": P } } } } }
    },
    "selector": { "id": "default" }   // optional — present when targeting a specific visual state
  }
]
```

- `objects` = visual-internal formatting (subtotals, data point colors, axis
  gridlines, card layout/value/label toggles). Keys vary entirely by
  `visualType` — a card's `objects` (`value`, `label`, `accentBar`,
  `cardCalloutArea`...) share nothing with a column chart's (`dataPoint`,
  `zoom`, `valueAxis`, `labels`).
- `visualContainerObjects` = chrome shared across all visual types
  (`title`, `border`, `background`, `dropShadow`, `divider`, `spacing`,
  `stylePreset`).
- **Literal values are always strings**, even for numbers/booleans:
  `"true"`, `"15D"` (the `D` suffix marks a double), `"'left'"` (single
  quotes inside the string mark a DAX string literal).
- **Fixed for v1 of the compiler.** None of this affects whether data
  renders correctly — it's cosmetic. Recommend hardcoding one sane
  formatting block per visual type and not exposing it as a generation
  target until the core pipeline works end-to-end.

#### `drillFilterOtherVisuals` — fixed, `true` on all 3 samples.

---

### 2.9 `<name>.SemanticModel/definition.pbism`

```json
{ "version": "4.2", "settings": {} }
```

Fully fixed.

---

### 2.10 `<name>.SemanticModel/definition/database.tmdl`

```
database
	compatibilityLevel: 1600
```

Fully fixed (2 lines + trailing blank). TMDL uses **tabs for indentation**,
not spaces — worth a lint check in the compiler's TMDL writer.

---

### 2.11 `<name>.SemanticModel/definition/model.tmdl`

```
model Model
	culture: en-US
	defaultPowerBIDataSourceVersion: powerBI_V3
	sourceQueryCulture: en-US
	dataAccessOptions
		legacyRedirects
		returnErrorValuesAsNull

annotation __PBI_TimeIntelligenceEnabled = 1
annotation PBI_QueryOrder = ["in"]
annotation PBI_ProTooling = ["DevMode"]

ref table in
ref table DateTableTemplate_3a844fbe-4e95-4575-b080-2954903d27ae
ref table LocalDateTable_4beb135a-eee4-4046-9631-0013a4238641

ref cultureInfo en-US
```

| Element | Fixed/Dynamic | Notes |
|---|---|---|
| header block (`culture`, `defaultPowerBIDataSourceVersion`, `dataAccessOptions`) | fixed | boilerplate |
| `PBI_QueryOrder` | **dynamic** | array of table names in load order — for a single-table model this is just `["in"]`; multi-table datasets need real dependency ordering |
| `ref table <name>` | **dynamic**, one line per table | must include your data table **and** one line per auto-generated date table (see §2.13) |
| `ref table DateTableTemplate_<guid>` | **dynamic but template-pattern** | appears once per model IF any date/datetime column exists — guid is fresh per model, content is template (§2.13) |
| `ref table LocalDateTable_<guid>` | **dynamic but template-pattern** | one per date *column* that gets auto-date-table behavior — guid fresh, content templated from column's min/max |
| `ref cultureInfo en-US` | fixed | unless localizing |

**Important for the compiler:** Power BI Desktop auto-creates a hidden date
table for every `dateTime`-typed column by default (unless autodate is
disabled). Your compiler needs to replicate this behavior deliberately — see
§2.13 — or every date column in every generated dataset will silently expect
one of these and Power BI will complain on open if `model.tmdl`'s `ref
table` lines don't match what's actually under `tables/`.

---

### 2.12 `<name>.SemanticModel/definition/tables/<table>.tmdl` — the core dynamic file

This is the single highest-value file to get right; it's where your
Profiler + KPI nodes' output actually becomes Power BI schema. Structure,
top to bottom:

```
table <table_name>
	lineageTag: <guid>

	measure '<Measure Name>' = <DAX expression>
		formatString: <format>
		lineageTag: <guid>
		[annotation PBI_FormatHint = {"currencyCulture":"en-US"}]

	column <ColumnName>
		dataType: <dax_type>
		[formatString: <format>]
		lineageTag: <guid>
		summarizeBy: <none|sum|average|count|...>
		sourceColumn: <original_column_name>

		[variation <Name>           ← ONLY on the date column used for time intelligence
			isDefault
			relationship: <relationship_guid>
			defaultHierarchy: <LocalDateTable_guid>.'Date Hierarchy']

		annotation SummarizationSetBy = Automatic

	partition <table_name> = m
		mode: import
		source =
				let
				    ... Power Query M steps ...
				in
				    <last step name>

	annotation PBI_NavigationStepName = Navigation
	annotation PBI_ResultType = Table
```

#### `table` header

| Field | Required | Fixed/Dynamic |
|---|---|---|
| `table <name>` | yes | **dynamic** — must match `model.tmdl`'s `ref table` and the filename |
| `lineageTag` | yes | **dynamic** — fresh GUID, used by Power BI internally for change tracking; the compiler should just generate a UUID4 and never reuse it |

#### `measure` blocks — required, one per KPI, fully dynamic

| Field | Required | Notes |
|---|---|---|
| `'<Measure Name>'` | yes | quote with single-quotes if it contains a space; this is your KPI's display name |
| `= <DAX>` | yes | the actual aggregation, e.g. `SUM('in'[Cost])`, `AVERAGE('in'[Age])`, `COUNT('in'[PatientID])` — **this is exactly the SQL→DAX translation your SQL Executor / KPI node needs to produce** |
| `formatString` | no but recommended | number format mask; currency uses the long `\$#,0...` pattern seen above, plain counts use `0` |
| `lineageTag` | yes | fresh GUID per measure |
| `annotation PBI_FormatHint` | no | only needed for currency columns, tells Desktop's UI what currency-formatting affordances to show |

This is the most directly KPI-node-driven part of the whole file. **A clean
mapping: each KPI in your Domain/KPI node's output → one `measure` block.**
SQL aggregations (`SUM`, `AVG`, `COUNT`) map near 1:1 to DAX (`SUM`,
`AVERAGE`, `COUNT`) — translation table worth building explicitly rather
than ad hoc per KPI.

#### `column` blocks — required, one per source column, fully dynamic except boilerplate

| Field | Required | Fixed/Dynamic | Notes |
|---|---|---|---|
| `column <Name>` | yes | **dynamic** | from Profiler's schema output |
| `dataType` | yes | **dynamic**, but from a fixed enum | observed: `dateTime`, `string`, `int64`, `decimal`. This is your Profiler's pandas dtype → DAX dtype mapping (`object`→`string`, `int64`→`int64`, `float64`→`decimal`, `datetime64`→`dateTime`) |
| `formatString` | no | dynamic | currency mask for money columns, `Long Date` for the date column, `0` for plain ints; omit for plain strings |
| `lineageTag` | yes | **dynamic** | fresh GUID per column |
| `summarizeBy` | yes | **dynamic**, fixed enum | `none` for IDs/strings/dates, `sum` for numeric measures-by-default (Cost), `sum` even on Age here (worth checking — Power BI defaults numeric columns to `sum` unless told otherwise, regardless of whether `sum` is semantically meaningful) |
| `sourceColumn` | yes | **dynamic** | must exactly match the column name as it exists after the M partition's transforms |
| `variation` block | only on the date column | **dynamic but template-pattern** | only appears on whichever column got auto-date-table treatment; binds it to the `LocalDateTable_<guid>` and its hierarchy |
| `annotation SummarizationSetBy = Automatic` | yes | fixed | always this literal value in our sample |

#### `partition` block — required, the data-loading mechanism

```
partition in = m
	mode: import
	source =
			let
			    Source = Excel.Workbook(File.Contents("<path>"), null, true),
			    in_Sheet = Source{[Item="in",Kind="Sheet"]}[Data],
			    #"Promoted Headers" = Table.PromoteHeaders(in_Sheet, [PromoteAllScalars=true]),
			    ... arbitrary M transform steps ...
			in
			    #"<last step name>"
```

| Field | Required | Fixed/Dynamic |
|---|---|---|
| `partition <name> = m` | yes | **dynamic** name, fixed `= m` (marks Power Query/M source vs `= calculated`) |
| `mode: import` | yes | fixed for this architecture (vs `directQuery`/`dual`) |
| `source` | yes | **fully dynamic** — this is the M script |

This is the single most important thing to get right, and it's **the answer
to your "how does data actually get in" question**: this M script is what
Power BI Desktop executes at open/refresh time to pull and shape data. **For
your compiler, this should target CSV, not Excel** — the sample uses
`Excel.Workbook(File.Contents(...))` because the source file was an .xlsx,
but your pipeline reads CSVs, so the equivalent M is:

```
Source = Csv.Document(File.Contents("<absolute_path_to.csv>"), [Delimiter=",", Columns=<N>, Encoding=65001, QuoteStyle=QuoteStyle.None]),
#"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
#"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{"<Col1>", type text}, {"<Col2>", Int64.Type}, ...})
```

The compiler's job per dataset:
1. Build the `Csv.Document(...)` call with the CSV's absolute path (or a
   relative path if you want the .pbip to be portable — worth testing
   whether Power BI resolves relative paths from the .pbip's folder).
2. Emit one `Table.TransformColumnTypes` step mapping every column to its
   inferred M type (`Int64.Type`, `type text`, `type date`, `Currency.Type`,
   etc.) — this is the same dtype map driving `dataType` in the `column`
   blocks above, so write it once and use it for both.
3. Optionally chain cleaning steps (the sample shows
   `Table.ReplaceValue(...)` filling nulls with `"Unknown"`) — these aren't
   required for a minimal working report; skip for v1 unless your
   Reflector node specifically flags null-heavy columns it wants cleaned.
4. The `let...in` block's final `in <stepname>` must reference whatever the
   *last* step in your generated chain is named — easy to get wrong with
   string templating, worth a dedicated test.

#### Trailing annotations — fixed

`PBI_NavigationStepName = Navigation` and `PBI_ResultType = Table` appear
unchanged; copy verbatim.

---

### 2.13 Auto-generated date tables — template-pattern, conditionally dynamic

Two distinct table types appear whenever a `dateTime` column exists:

**`DateTableTemplate_<guid>.tmdl`** — one per *model*, regardless of how many
date columns exist. Fully templated: 6 hidden calculated columns (`Year`,
`MonthNo`, `Month`, `QuarterNo`, `Quarter`, `Day`) all computed via fixed DAX
expressions off a single `Date` column, plus a `'Date Hierarchy'` with 4
levels. The only varying content is the `lineageTag` GUIDs (one per
column/hierarchy/level — generate fresh per table) and the table's own
`<guid>` suffix. The `partition`'s `source = Calendar(Date(2015,1,1),
Date(2015,1,1))` is a degenerate 1-day placeholder — Power BI Desktop
substitutes the real range at refresh time based on what's bound to it.
**Treat this whole file as a fill-in-the-GUIDs template — the DAX never
changes.**

**`LocalDateTable_<guid>.tmdl`** — one per *date column* that uses
auto-date-table behavior (here, just `VisitDate`). Identical column/hierarchy
structure to the template table above, but:
- `showAsVariationsOnly` flag present (hides it from the general field list — it's only reachable via the variation drill-down)
- `partition` source is **not** a placeholder: `Calendar(Date(Year(MIN('in'[VisitDate])), 1, 1), Date(Year(MAX('in'[VisitDate])), 12, 31))` — dynamically spans the actual data's year range, computed by formula at refresh time, **not something the compiler needs to pre-calculate**, just emit this exact formula pattern with the real table/column name substituted in.

**Compiler decision point:** you can either (a) replicate this auto-date
behavior per date column found by the Profiler — more faithful to what
Power BI Desktop does by default, more files to generate — or (b) disable
autodate (`legacyRedirects`/model-level setting) and skip these tables
entirely, giving up the built-in Date Hierarchy drill but simplifying
generation substantially. **Recommend (b) for v1**: zero extra files, the
date column still works fine as a plain date axis, and you can add (a) later
as a "polish" pass once the core pipeline is proven.

---

### 2.14 `relationships.tmdl`

```
relationship <guid>
	joinOnDateBehavior: datePartOnly
	fromColumn: in.VisitDate
	toColumn: LocalDateTable_4beb135a-eee4-4046-9631-0013a4238641.Date
```

One block per relationship. **Only needed if you keep auto-date tables**
(§2.13 option a). If you go with option (b) — disable autodate — this file
is just the 1-line `database`-style header with no relationship blocks, or
omitted entirely for a single-table model with no explicit joins. For
multi-table datasets later, this is also where your compiler will need to
emit real foreign-key relationships (`fromColumn`/`toColumn` between two
actual data tables) — not reverse-engineered here since this sample only has
one data table.

---

### 2.15 Files to exclude from the compiler entirely

| File | Why |
|---|---|
| `.pbi/localSettings.json` (both copies) | Machine-encrypted (`securityBindingsSignature`), user/device-specific, regenerated by Desktop on open. Never write this. |
| `.pbi/cache.abf` | Binary materialized-data cache. Power BI Desktop builds this itself on first open/refresh — writing it yourself would require replicating Microsoft's internal binary format, which isn't worth attempting. |
| `.pbi/editorSettings.json` | UI behavior toggles (autodetect relationships, parallel query loading). Safe fixed defaults if you want it present, but Desktop will create it if missing. |
| `diagramLayout.json` | Visual canvas layout for the *model relationship diagram view* (not the report canvas) — purely cosmetic, Desktop regenerates on open. |
| `definition/cultures/en-US.tmdl` | Confirmed via inspection: ~1700 lines of auto-generated Q&A linguistic schema (synonyms/weights for every column and measure name, entirely machine-derived from the names already in your table). Desktop regenerates this automatically the first time the model is opened or Q&A is invoked — there is no reason to author it. |
| `StaticResources/.../*.json` (theme files) | Microsoft-shipped theme definitions, not project-specific. Copy the two files verbatim as static assets bundled with your compiler rather than generating them. |

---

## 3. ID conventions

Two different ID schemes appear in this format and they're easy to conflate:

| ID type | Format | Where used | Compiler should... |
|---|---|---|---|
| **Folder/file IDs** (page, visual) | 20-char lowercase hex-looking string, e.g. `3e33d29435230b0ab08c` | page/visual folder names, `pages.json.pageOrder`, `page.json.name`, `visual.json.name` | generate via any unique string (don't need to match Power BI's exact algorithm — Desktop accepted hand-rolled IDs in community tooling); deterministic slugs (e.g. hash of page title) are fine and make debugging easier than random hex |
| **`lineageTag` / relationship / logicalId** | standard UUID v4, e.g. `8ef6fb8b-8202-48dc-a192-74f450445b68` | every TMDL `lineageTag`, `.platform` `logicalId`, `relationship <guid>` | use a real `uuid.uuid4()` — these appear to be genuine GUIDs throughout, unlike the folder IDs |

**Open question to verify before relying on it:** whether Power BI Desktop
*requires* folder/visual `name` values to follow Microsoft's exact ID
generation algorithm, or merely requires them to be unique strings matching
between the folder name and the `name` field inside its JSON. Test by
opening a `.pbip` with a deliberately simple ID (e.g. `"page1"`) — if it
opens cleanly, your compiler can use human-readable deterministic slugs
instead of hex strings, which will make debugging much easier.

---

## 4. Recurring structural pattern: the "expr/Literal" formatting wrapper

This exact shape recurs in `report.json`, every `page.json`, and every
`visual.json`'s `objects`/`visualContainerObjects`:

```json
"<PropertyGroupName>": [
  {
    "properties": {
      "<propName>": {
        "expr": { "Literal": { "Value": "<value-as-string>" } }
      }
    },
    "selector": { "id": "default" }
  }
]
```

or, for colors:

```json
"<propName>": {
  "solid": { "color": { "expr": { "ThemeDataColor": { "ColorId": N, "Percent": P } } } }
}
```

Worth implementing **once** as a small Pydantic model / builder function
(`literal_prop(value)`, `theme_color_prop(color_id, percent)`) and reusing it
everywhere, rather than hand-writing this nesting per call site. `ColorId`
indexes into the active theme's palette (0 = background/neutral in this
theme); `Percent` is a tint/shade adjustment (negative = darker).

---

## 5. Fixed vs Dynamic — summary table

| Category | Files / fields | Compiler action |
|---|---|---|
| **Fully fixed, copy verbatim** | `database.tmdl`, `version.json`, `definition.pbism`, theme JSONs, `DateTableTemplate` DAX body (except GUIDs), trailing TMDL annotations | Bundle as static templates |
| **Fixed shell, dynamic IDs only** | `.platform` (×2), `definition.pbir`, page/visual GUIDs, `lineageTag`s everywhere | Template + GUID injection |
| **Fixed structure, dynamic content** | `report.json` (theme name could vary), `page.json` (displayName, name), TMDL `column`/`measure` blocks | Template + field substitution from Profiler/KPI output |
| **Fully dynamic, generated per run** | `pages.json.pageOrder`, every `visual.json.query.queryState` field binding, the M `partition.source` script, `model.tmdl`'s `ref table` list | Core compiler logic — this is where your Domain/KPI + Profiler outputs actually become Power BI artifacts |
| **Exclude entirely** | `localSettings.json` (×2), `cache.abf`, `editorSettings.json`, `diagramLayout.json`, `cultures/en-US.tmdl` | Never write these; Desktop regenerates on open |

**Practical priority order for the compiler build-out:**
1. `report.json` + `version.json` + `.platform` ×2 + `definition.pbir` + `definition.pbism` + `database.tmdl` — static skeleton, do once.
2. `<table>.tmdl` partition's M query (CSV ingestion + type casting) — without this nothing loads.
3. `<table>.tmdl` columns + measures — schema + your KPIs as DAX.
4. `model.tmdl`'s `ref table` list — must match what you wrote in (2)/(3).
5. `pages.json` + `page.json` × N — page scaffolding.
6. `visual.json` × N — the query/field-binding logic, by far the most complex piece; build and test one visual type (e.g. `cardVisual`, simplest) end-to-end before generalizing to chart types with `Category`/`Y` roles.
7. (Optional, v2) Auto-date tables + relationships, currency format hints, cosmetic formatting blocks.