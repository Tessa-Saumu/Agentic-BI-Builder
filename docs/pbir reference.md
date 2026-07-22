# PBIR Format Reference

Reverse-engineered from `minimal_report` — a Power BI report over a single
imported table (`in`, from `Health_Dirty.xlsx`, a healthcare visits dataset)
with one auto-generated local date table. Covers all 5 visual types the
compiler needs to support: **card** (`cardVisual`), **pivot table**
(`pivotTable`), **clustered column chart** (`clusteredColumnChart`), **table**
(`tableEx`), and **line chart** (`lineChart`). The line chart's date-hierarchy
binding in particular has a strict, non-obvious required shape — see §2.8.2.

This document is the spec the PBIR Compiler node codes against. For every file:
what the keys mean, which are required, how deep the nesting goes, and —
critically — which values are **fixed** (same on every run) vs **dynamic**
(must be generated per dataset/KPI by the agent).

**Provenance note:** beyond the original single-sample reverse-engineering
pass, this document has since been corrected against **confirmed findings
from live report-generation debugging** — real Desktop crashes, real schema
validation errors, and fixes verified against Microsoft's own published JSON
schemas rather than inferred from another sample alone. Where a debugging
finding superseded an earlier reverse-engineered guess (e.g. §2.4's
`report.json` schema-version coupling, §2.8's filter-`type` rule, §2.12's
M-escaping rule), the correction is called out explicitly at that section
rather than silently overwritten, so the reasoning stays visible. One
general lesson from that process, worth keeping in mind reading the rest of
this doc: **field shapes can be coupled to a schema version that a
single sample can't reveal** — treat any "fixed shape" claim below as fixed
*for the schema version this document targets*, and re-verify against
Microsoft's actual schema file if you ever change which `$schema` version
you pin to.

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
| `$schema` | yes | fixed, **but version-coupled — see warning below** | pin to `report/3.3.0/schema.json`, matching a proven real Desktop export |
| `themeCollection.baseTheme.name` | yes | fixed | `"CY26SU05"` (current default MS theme — should be treated as a versioned constant the compiler pins) |
| `themeCollection.customTheme.name` | yes | fixed (or a chosen constant) | `"AccessibleCityPark"` — one of MS's built-in named themes |
| `themeCollection.*.reportVersionAtImport` | yes | fixed, **object shape at 3.3.0 — see warning below** | `{"visual": "X.Y.Z", "report": "X.Y.Z", "page": "X.Y.Z"}`, each a `^[0-9]+\.[0-9]+\.[0-9]+$` string; copy verbatim from a proven reference report rather than inventing values |
| `objects.section[0].properties.verticalAlignment` | no | fixed | cosmetic default |
| `resourcePackages[0].name` / `.type` / `.items[*]` | yes | fixed | **`items` sits directly on the `resourcePackages[0]` element** — there is no extra `resourcePackage` wrapper key nested inside it (see below); `items[*].path` must match the actual file under `StaticResources/SharedResources/...`, and `items[*].type` must be `"BaseTheme"` / `"CustomTheme"` matching whichever theme that item resolves |
| `settings.exportDataMode` | yes | fixed | **const enum, exactly one of** `"AllowSummarized"` \| `"AllowSummarizedAndUnderlying"` \| `"None"` — no other string is valid |
| `settings.*` (remaining keys) | yes (block) | fixed | export/drill/tooltip behavior flags — sane defaults, no need to vary per dataset |
| `settings.useNewFilterPaneExperience` | — | **do not emit** | not a recognized property on the `ExplorationSettings` schema at 3.3.0; `additionalProperties: false` rejects it |
| `layoutOptimization` (root-level) | — | **do not emit** | not a recognized root property at 3.3.0 (`required` is only `["$schema", "themeCollection"]`, `additionalProperties: false`); this key belongs to older 1.0.0-era schemas only |

Nesting depth: 4 (`objects.section[0].properties.X.expr.Literal.Value`).
**Compiler action: treat this file as a static template, copy as-is.** Theme
choice could become a dynamic parameter later (e.g. light/dark by domain) but
isn't required for a working report.

**⚠️ Field shapes in this file are coupled to the declared `$schema` version —
confirmed the hard way during report-generation debugging.** A single
reverse-engineered sample can only tell you what's true *for that sample's
schema version*; several of the fields above are not universal PBIR facts,
they're facts about schema `3.3.0` specifically, and they change shape at
other versions:

- `reportVersionAtImport` is an **object** (`{visual, report, page}`) at
  3.x, but a **bare string** (e.g. `"5.55"`) at older/1.x-era schemas.
- `layoutOptimization` is a **required root property at schema 1.0.0**, but
  is **not a recognized property at all at 3.3.0** (rejected outright by
  `additionalProperties: false`).
- `settings.exportDataMode`'s accepted enum values, and whether
  `useNewFilterPaneExperience` is legal at all, are likewise tied to the
  declared schema version.

**The failure mode this produces is nasty because it's silent at first and
then very loud:** pinning `$schema` to one version while shaping fields for
a *different* version doesn't fail cleanly — it produces a
`NullReferenceException` deep in Desktop's `ReportViewDocumentProvider
.GetEnhancedReportDocument` renderer with no diagnostic detail (schema
validation apparently isn't even reached), which is far harder to debug than
the itemized schema-validation errors you get once `$schema` and field shapes
actually agree. **Rule for the compiler: always keep `$schema` and every
version-shaped field pinned to the *same* schema version, and verify new
field shapes against Microsoft's actual published schema file for that
version** (`developer.microsoft.com/json-schemas/fabric/item/report/definition/report/<version>/schema.json`)
— not just by copying another sample's shape — since copying a shape without
confirming its paired version is exactly how this class of bug reintroduces
itself.

**`resourcePackages` — confirmed wrong shape, now corrected:** an earlier
compiler draft nested an extra `resourcePackage` key inside the array
element (`resourcePackages: [{ resourcePackage: { name, type, items } }]`).
The correct, Desktop-validated shape has `name`/`type`/`items` directly on
the array element itself, exactly as this table's row states and exactly as
§2.4's field table already implied before this correction — `items` was
always meant to be reachable as `resourcePackages[0].items[*]`, not
`resourcePackages[0].resourcePackage.items[*]`. Getting this wrong means
Desktop can't resolve either theme reference at all, which manifests as the
same `NullReferenceException` described above (theme resolution happens in
the same renderer code path). Relatedly: every theme name referenced by
`themeCollection.baseTheme.name` / `.customTheme.name` needs a **matching
`resourcePackages[0].items[]` entry of the corresponding `type`** — one item
typed `"BaseTheme"`, one typed `"CustomTheme"`. Pointing both `baseTheme` and
`customTheme` at the same self-authored placeholder theme, with only a
single `BaseTheme`-typed item and no `CustomTheme`-typed item, leaves the
`customTheme` reference dangling even after the wrapper-nesting bug is fixed.

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

Confirmed values, all reverse-engineered from real exports: `"cardVisual"`,
`"pivotTable"`, `"clusteredColumnChart"`, `"tableEx"`, `"lineChart"`. This is
effectively the chart-type the KPI/Domain node already outputs — direct
mapping needed from your KPI schema's `chart_type` field to Power BI's visual
type strings. Note `"tableEx"`, not `"table"` — Power BI's plain grid visual
uses this name in PBIR even though the Desktop UI just calls it "Table" (the
"Ex" is a legacy internal naming artifact, not a version marker; don't
special-case it). Other types (`slicer`, `pieChart`, etc.) remain
unconfirmed — don't claim compiler support for a `visualType` string that
hasn't been checked against a real export, since a wrong-but-plausible-looking
string will fail silently or open with the wrong visual in Desktop rather
than raising a clear error.

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

#### `filterConfig` — sibling of `visual`, present on most but not all visuals

Not documented in the original 3-visual pass; confirmed against all 5 samples
in this expanded reference, it's a **top-level key alongside `$schema`,
`name`, `position`, and `visual`** — not nested inside `visual` itself:

```json
{
  "$schema": "...visualContainer/2.10.0/schema.json",
  "name": "<visualId>",
  "position": { ... },
  "visual": { ... },
  "filterConfig": {
    "filters": [
      {
        "name": "<8-char-hex-ish-id>",
        "field": { "Column": { ... } } | { "Measure": { ... } } | { "HierarchyLevel": { ... } },
        "type": "Categorical" | "Advanced"
      }
    ]
  }
}
```

| Field | Required | Fixed/Dynamic | Notes |
|---|---|---|---|
| `filterConfig` (whole block) | **conditional** | — | present on 4 of 5 confirmed samples (card, tableEx, pivotTable, lineChart); **absent entirely** on the clusteredColumnChart sample — see below for the compiler rule |
| `filters[]` | — | **dynamic**, one entry per bound field | every `Column`/`Measure`/`HierarchyLevel` field bound anywhere in that visual's `query.queryState` gets exactly one corresponding filter entry here, in the identical field-shape used in the projection (same `Expression.SourceRef.Entity`/`Property`, or the same `PropertyVariationSource`/`Hierarchy`/`Level` nesting for hierarchy levels) |
| `filters[].name` | yes | **dynamic** | must be **1–50 characters** (Desktop-validated hard constraint — confirmed via schema validation error, not a guess); generated fresh per filter, same general ID class as page/visual folder names (§3), not a `lineageTag` UUID. **Do not build this by concatenating a namespace/visual-id with a field-derived suffix and truncating the whole string to a fixed cap** — if the truncation point falls inside the differentiating suffix, multiple filters on the same visual can collapse onto an identical name (confirmed: a visual whose own id was already ~40 chars produced 4 filters all sharing one truncated name). **Reserve space for the uniqueness-bearing suffix (e.g. a trailing `_<idx>`) first, then truncate only the leading/namespace portion to fit inside 50 chars** — the differentiator must never be what gets cut. Uniqueness only needs to hold within one visual's `filters[]` array, not globally. |
| `filters[].field` | yes | **dynamic** | mirrors the corresponding projection's `field` shape exactly — see §2.8's `Column`/`Measure`/`NativeVisualCalculation` patterns; `NativeVisualCalculation` fields do **not** get a filter entry (only their underlying hidden base `Measure` does — confirmed on tableEx/pivotTable, where `Total Cost_Base` gets a filter but the `Total Cost` visual calc itself doesn't) |
| `filters[].type` | yes | **dynamic**, enum `"Categorical"` \| `"Advanced"` | **rule confirmed during report-generation debugging** (superseding this section's earlier "no causal rule identified" conclusion, which was drawn only from the lineChart hierarchy-level filters below): a plain **`Column`-bound** filter is `"Categorical"`; a **`Measure`-bound** filter is `"Advanced"`. Confirmed with no exceptions across every `filterConfig` in a known-good, real Desktop export. This rule is specifically about plain field kind (`Column` vs `Measure`) — it does **not** extend to `HierarchyLevel` filters, where the split still doesn't cleanly track field kind or `active` (see the lineChart evidence immediately below, which remains unexplained and is kept here as the honest boundary of what's confirmed). **Compiler rule: derive `type` from field kind — `"Categorical"` for `Column`, `"Advanced"` for `Measure` (and, absent further evidence, `HierarchyLevel`)** — rather than defaulting every filter to `"Advanced"` |

**lineChart hierarchy-level filter evidence (unexplained, kept for the record):**
on the lineChart's 4 hierarchy-level filters, Year and Day are `"Advanced"`
while Quarter and Month are `"Categorical"`, and this doesn't cleanly track
`active: true/false` on the matching projection. This sits alongside —
rather than contradicts — the Column/Measure rule above: the rule was
established on plain `Column`/`Measure` filters specifically, and the
hierarchy-level case is a separate, still-open question. Don't let the
absence of an explanation here read as evidence against the Column/Measure
rule; they're separate observations about different field kinds.

**Compiler rule for whether to emit `filterConfig` at all:** the only sample
missing it (clusteredColumnChart) uses a **`Column`** projection for its
`Category` role (`Doctor`) with no `Measure` or hierarchy involved elsewhere
beyond the `Y` role's single measure — yet the card, which also has just one
plain `Measure` binding, *does* get a `filterConfig`. That rules out "it's
about which field types are bound." The more likely explanation, given this
is the visual with `z: 1000` and a non-standard tab order (§3 already flags
this instance as the one manually repositioned in Desktop to test ID
requirements), is that `filterConfig` reflects **whatever filter-pane state
Desktop happened to serialize for that specific visual**, not a structural
requirement tied to visual type or field shape. **Recommended compiler
behavior: always emit `filterConfig` with one entry per bound field** (this
matches 4 of 5 samples and is very likely accepted even where Desktop's own
export omitted it) rather than trying to infer when to omit it — omitting it
risks nothing you can point to, but the reverse isn't verified. This is a
good candidate for a follow-up test: export a report with `filterConfig`
manually stripped from a visual and confirm Desktop still opens it before
locking in "always emit."

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
- **Confirmed decision: template, not generated.** None of this affects
  whether data renders correctly — it's cosmetic. Per visual type
  (`cardVisual`, `clusteredColumnChart`, `pivotTable`, etc.), hardcode one
  `objects`/`visualContainerObjects` block straight from this sample and
  reuse it verbatim for every visual of that type the compiler emits — the
  same approach as the currency `PBI_FormatHint` annotation below. Only the
  `query.queryState` field bindings and `position` need to vary per visual
  instance; the formatting chrome around them doesn't. Revisit as a
  generation target only after the core pipeline renders correctly
  end-to-end.

#### `drillFilterOtherVisuals` — fixed, `true` on all 5 samples.

---

### 2.8.1 `tableEx` visual type — the plain table, in detail

Sample: `visualType: "tableEx"`, one role, `Values`, holding a `Column`, a
`NativeVisualCalculation`, its hidden base `Measure`, and a second plain
`Measure`:

```json
"query": {
  "queryState": {
    "Values": {
      "projections": [
        { "field": { "Column": { "Expression": { "SourceRef": { "Entity": "in" } }, "Property": "Diagnosis" } },
          "queryRef": "in.Diagnosis", "nativeQueryRef": "Diagnosis" },
        { "field": { "NativeVisualCalculation": {
              "Language": "dax",
              "Expression": "EXPANDALL(AVERAGE([Total Cost_Base]), ROWS COLUMNS)",
              "Name": "Total Cost" },
            "Annotations": { "customTotalMetadata": { "baseQueryName": "in.Total Cost" } } },
          "queryRef": "select", "nativeQueryRef": "Total Cost",
          "format": "\\$#,0.###############;(\\$#,0.###############);\\$#,0.###############" },
        { "field": { "Measure": { "Expression": { "SourceRef": { "Entity": "in" } }, "Property": "Total Cost" } },
          "queryRef": "in.Total Cost", "nativeQueryRef": "Total Cost_Base",
          "hidden": true, "displayName": "Total Cost_Base" },
        { "field": { "Measure": { "Expression": { "SourceRef": { "Entity": "in" } }, "Property": "Average Age" } },
          "queryRef": "in.Average Age", "nativeQueryRef": "Average Age" }
      ]
    }
  }
}
```

**The critical structural point, easy to get wrong by analogy with
`pivotTable`:** `tableEx` has **exactly one role, `Values`, and the grouping
column lives inside it as just another projection** — it is *not* split into
a separate `Rows` role the way `pivotTable` splits row-grouping columns out.
All four projections (the `Column`, the visual calc, its hidden base, and the
plain `Measure`) are siblings in the same `Values.projections` array, in the
order they'll appear as columns left-to-right in the rendered table. If your
compiler reuses the `pivotTable` template and just renames `visualType`, it
will silently emit a `Rows` role that `tableEx` doesn't recognize.

Everything else about field binding — the `NativeVisualCalculation` +
hidden-base-measure pattern for wrapping a measure in an `EXPANDALL(...)`
visual calc, the `format` string on that projection, `queryRef: "select"` for
the native calc vs `"<Entity>.<Property>"` for plain refs — is **identical**
to what §2.8 already documents for `pivotTable`'s `Values` role; this isn't
new syntax, just a different role shape wrapping the same field-binding
vocabulary.

`sortDefinition`: **absent** on this sample (unlike the `pivotTable` sample,
which sorts by Average Age descending). Since §2.8 already established
`sortDefinition` is optional and safe to omit, no new rule needed — just
don't assume every table-like visual has one.

`visual.objects`: **absent entirely** — no `objects` key under `visual` at
all for this instance. `visualContainerObjects` has only `title` (`show:
true`, `text: 'Average Age and Cost by Diagnosis'`). This is thinner chrome
than the `pivotTable` sample (which also sets `stylePreset`, `background`,
richer `title` properties, `divider`, `spacing`) — both are valid; the
compiler's fixed per-type template (§2.8's "template, not generated"
decision) should use whichever level of chrome your report needs, but
`tableEx` doesn't strictly require `objects` to be present at all.

**Compiler summary for `tableEx`:** map "table" in your KPI/chart_type schema
to `visualType: "tableEx"`, one `Values` role with the grouping column(s) and
all measures as flat sibling projections (no `Rows` role), reusing the exact
same `Column`/`Measure`/`NativeVisualCalculation` field-binding logic already
built for `pivotTable`.

---

### 2.8.2 `lineChart` visual type — the date-hierarchy quirk

This is the visual type flagged as needing strict adherence, because Power
BI does not let a line chart bind a single date-hierarchy level on its own —
binding "Year" from a date column's hierarchy causes Desktop to project
**all four hierarchy levels** into the `Category` role, whether or not they
all end up rendered.

```json
"query": {
  "queryState": {
    "Category": {
      "projections": [
        {
          "field": { "HierarchyLevel": {
            "Expression": { "Hierarchy": {
              "Expression": { "PropertyVariationSource": {
                "Expression": { "SourceRef": { "Entity": "in" } },
                "Name": "Variation",
                "Property": "VisitDate"
              } },
              "Hierarchy": "Date Hierarchy"
            } },
            "Level": "Year"
          } },
          "queryRef": "in.VisitDate.Variation.Date Hierarchy.Year",
          "nativeQueryRef": "VisitDate Year",
          "active": true
        },
        /* — identical wrapper, "Level": "Quarter", active: true — */
        /* — identical wrapper, "Level": "Month",   active: true — */
        /* — identical wrapper, "Level": "Day",     active: false — */
      ]
    },
    "Y": {
      "projections": [
        { "field": { "Measure": { "Expression": { "SourceRef": { "Entity": "in" } }, "Property": "Total Cost" } },
          "queryRef": "in.Total Cost", "nativeQueryRef": "Total Cost" }
      ]
    }
  }
}
```

(This snippet uses `/* */` comments to abbreviate the repeated 2nd–4th
projections for readability — that's illustrative shorthand, **not valid
JSON**; the actual `visual.json` has all four as complete, independently
valid `HierarchyLevel` objects with no comments. Each is identical to the
`"Year"` block shown in full above except `"Level"`, `queryRef`'s trailing
segment, `nativeQueryRef`'s trailing word, and `active`.)

**Required shape, rule by rule:**

| Rule | Detail |
|---|---|
| Field type | `HierarchyLevel`, not `Column` — a plain `{ "Column": { ..., "Property": "VisitDate" } }` binding is a *different, simpler* shape that does **not** get hierarchy drill-down. Use `HierarchyLevel` whenever the bound field is a date/datetime column carrying a `variation` block (§2.13) |
| Wrapper | `HierarchyLevel.Expression.Hierarchy.Expression.PropertyVariationSource` — this is a 4-level-deep nested `Expression` chain before you reach the actual source table/column reference (`SourceRef.Entity` + `Name: "Variation"` + `Property: "<date column>"`), then a sibling `Hierarchy.Hierarchy: "Date Hierarchy"` names which hierarchy off that variation to walk |
| Projection count | **exactly 4**, one per level of `Date Hierarchy`: `"Year"`, `"Quarter"`, `"Month"`, `"Day"`, in that order, every time — even though the chart visually only needs to show data at one zoom level at a time. Do not emit only the levels you think will be "used"; Desktop's own export always emits all 4 |
| `queryRef` / `nativeQueryRef` per level | `queryRef` follows `"<Entity>.<DateColumn>.Variation.Date Hierarchy.<Level>"`; `nativeQueryRef` follows `"<DateColumn> <Level>"` (e.g. `"VisitDate Year"`) — mechanically derivable from the entity/column/level, not something to hardcode per dataset |
| `active` flag | 3 of 4 are `true` (Year, Quarter, Month in this sample), the last (`Day`) is `false`. This appears to mark how deep the currently-rendered drill state goes, **not** a count you should assume is always "first 3 true, last false" — treat `active` as reflecting whatever zoom level the chart is currently drilled to, and default to the same "all but the deepest level active" pattern observed here unless you have a reason (e.g. a KPI spec requesting day-level granularity) to drill deeper |
| `Y` role | ordinary single `Measure` projection — no special handling, identical to every other chart's `Y`/`Values` role already documented in §2.8 |

**`filterConfig` on this visual** (§2.8's new filter section applies, with
one hierarchy-specific wrinkle): 5 filters total — one ordinary `Measure`
filter for `Total Cost`, plus **one filter per hierarchy level**, each
`field` reusing the identical `HierarchyLevel`/`PropertyVariationSource`
nesting shown above rather than a simplified reference. The `Total Cost`
filter follows the confirmed Column/Measure rule (§2.8) and is
`"Advanced"`, as expected for a `Measure`-bound filter. The `type` value on
the 4 hierarchy-level filters, however, alternates
`Advanced`/`Categorical`/`Categorical`/`Advanced` across Year/Quarter/Month/
Day in this sample and does **not** reduce to the Column/Measure rule — all
4 are `HierarchyLevel` fields, so field kind can't be what's driving the
split here, and it doesn't track `active` either (§2.8's confirmed-rule note
already flags this as the honest open boundary of what's been established).
**This is genuinely unresolved, not just under-tested** — unlike the
Column/Measure case, no second confirming sample exists yet for
`HierarchyLevel` filters specifically. Absent further evidence, default to
`"Advanced"` for all 4 hierarchy-level filters specifically (not for every
filter type generally, per the correction in §2.8) until a second sample
clarifies the pattern.

**Why this matters for the compiler:** any templating approach that
generates the `Category` role by binding a single date column (the same way
you'd bind a plain string/numeric column to a bar chart's category axis) will
produce a `lineChart` that Desktop either rejects or silently flattens to a
single non-hierarchical level, losing the drill-down behavior that's core to
why this visual type is useful for a time series. **Treat "line chart over a
date column" as its own template branch**, structurally distinct from "line
chart over a non-date column" (which would use a plain `Column` projection,
single entry, no hierarchy wrapper) — don't try to unify them into one
generic "Category role" builder function the way `Column`-vs-`Measure` is
otherwise unified elsewhere in §2.8.

`visual.objects`/`visualContainerObjects`: absent in this sample (no
`objects` or `visualContainerObjects` key under `visual` at all — leanest
chrome of any of the 5 samples). Confirms §2.8's "cosmetic, template per
type" decision still holds — just note that `lineChart`'s minimal template
can be an empty/near-empty block if that's what your report design calls
for.

**Compiler summary for `lineChart`:** map "line chart" in your KPI schema to
`visualType: "lineChart"`; if the x-axis field is date-typed, emit the full
4-level `HierarchyLevel` group (Year/Quarter/Month/Day, in order, 3 `active:
true` + deepest `active: false` by default) instead of a single `Column`
projection; if the x-axis field is not date-typed, use a plain `Column`
projection the same way `clusteredColumnChart`'s `Category` role already
works. `Y` role is a standard `Measure` projection, no special handling.

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
| `annotation PBI_FormatHint` | no | **template, not generated** — copy the fixed `{"currencyCulture":"en-US"}` block onto any column the Profiler flags as currency-typed; same logic as `formatString` below, don't build this from scratch per dataset, just attach the existing block when the type matches |

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

**⚠️ M string-escaping — confirmed bug, previously undocumented here:**
whatever gets embedded inside the double-quoted string literals in this
M script (the CSV path, column names inside `TransformColumnTypes`, any
other text literal) must be escaped using **M's actual escape rule, not
another language's.** M's *only* string-escape mechanism is doubling the
quote character (`"` → `""`); **backslash has no special meaning inside an
M text literal at all** — it is always a literal character, unlike
Python/C/JSON where `\\` means "one literal backslash." Treating M like
those languages and doubling backslashes before embedding a path (e.g. an
absolute Windows path from `os.path.abspath()`, which naturally contains
single backslashes) produces a string M does **not** collapse back down —
Desktop then tries to open a path containing literal doubled separators,
which matches nothing on disk. **This is the mechanism behind the "some
tables have incomplete or no data" dialog** when it's caused by a genuine
partition-load failure (see the note on that dialog at the end of §2.15 —
it also appears, harmlessly, on every fresh `.pbip` with no cache yet, so
don't assume every occurrence is this bug). **Compiler rule: for any string
embedded in an M double-quoted literal, only double literal `"` characters;
never touch backslashes.** Confirmed against this very reference's own
`File.Contents(...)` example: note the path above and every real sample
uses single, un-doubled backslashes on Windows paths — that's the actual
working convention, not an accident of formatting in this doc.

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

**Compiler decision (confirmed): keep auto-date tables for v1.** Drill-through
on date hierarchies (Year → Quarter → Month → Day) is core to what makes a
Power BI report feel like Power BI — stripping it to save a couple of files
isn't worth losing that. The added complexity is template substitution, not
new logic:

1. **For every column the Profiler tags as a date/datetime type**, the
   compiler emits one `LocalDateTable_<guid>.tmdl`, using the exact template
   in this section with three substitutions: a fresh `<guid>` for the table
   name and every `lineageTag`, the real table/column name in the
   `partition` source formula
   (`Calendar(Date(Year(MIN('<table>'[<col>])), 1, 1), Date(Year(MAX('<table>'[<col>])), 12, 31))`),
   and nothing else changes — the 6 calculated columns and the hierarchy are
   identical DAX every time.
2. **`DateTableTemplate_<guid>.tmdl` is emitted once per model**, regardless
   of how many date columns exist — same fill-in-the-GUIDs rule, the
   `Calendar(Date(2015,1,1), Date(2015,1,1))` placeholder source never
   changes (Desktop overwrites it at refresh time).
3. The data column itself gets a `variation` block (§2.12) pointing at its
   `LocalDateTable_<guid>` and `'Date Hierarchy'`.
4. `relationships.tmdl` gets one `relationship <guid>` block per date
   column, in the exact `fromColumn`/`toColumn` shape shown in §2.14.
5. `model.tmdl`'s `ref table` list must include every `LocalDateTable_<guid>`
   generated plus the single `DateTableTemplate_<guid>`.

**Practical implication for the compiler's build order:** this is a
template-fill operation, not new generation logic, so it doesn't have to
block the v1 pipeline — build the core table/measures/visuals path first
(per the priority order in §5), then add date-table emission as a
deterministic post-step once a date column is detected. Keep it isolated in
its own function (e.g. `emit_date_table(table, column, model_guid)`) so it's
easy to unit-test against this exact reference file independent of the rest
of the compiler.

---

### 2.14 `relationships.tmdl`

```
relationship <guid>
	joinOnDateBehavior: datePartOnly
	fromColumn: in.VisitDate
	toColumn: LocalDateTable_4beb135a-eee4-4046-9631-0013a4238641.Date
```

One block per relationship. **Required for v1** since auto-date tables are
in scope (§2.13): every date/datetime column gets one relationship block
linking it to its `LocalDateTable_<guid>`. For multi-table datasets later,
this is also where the compiler will need to emit real foreign-key
relationships (`fromColumn`/`toColumn` between two actual data tables) — not
reverse-engineered here since this sample only has one data table.

---

### 2.15 Files to exclude from the compiler entirely

| File | Why |
|---|---|
| `.pbi/localSettings.json` (both copies) | Machine-encrypted (`securityBindingsSignature`), user/device-specific, regenerated by Desktop on open. Never write this. |
| `.pbi/cache.abf` | Binary materialized-data cache. Power BI Desktop builds this itself on first open/refresh — writing it yourself would require replicating Microsoft's internal binary format, which isn't worth attempting. **See the callout below** — its absence has a visible, easily-misread symptom worth knowing about in advance. |
| `.pbi/editorSettings.json` | UI behavior toggles (autodetect relationships, parallel query loading). Safe fixed defaults if you want it present, but Desktop will create it if missing. |
| `diagramLayout.json` | Visual canvas layout for the *model relationship diagram view* (not the report canvas) — purely cosmetic, Desktop regenerates on open. |
| `definition/cultures/en-US.tmdl` | Confirmed via inspection: ~1700 lines of auto-generated Q&A linguistic schema (synonyms/weights for every column and measure name, entirely machine-derived from the names already in your table). Desktop regenerates this automatically the first time the model is opened or Q&A is invoked — there is no reason to author it. |
| `StaticResources/.../*.json` (theme files) | Microsoft-shipped theme definitions, not project-specific. Copy the two files verbatim as static assets bundled with your compiler rather than generating them. |

**⚠️ Expected behavior, not a bug: "some tables have incomplete or no
data" on first open.** Confirmed during report-generation debugging to be a
recurring, easily-misdiagnosed point of confusion, worth stating plainly so
it doesn't burn debugging time again: **every freshly-compiled or
freshly-cloned `.pbip` project shows this banner the first time it's opened
in Desktop**, simply because `.pbi/cache.abf` doesn't exist yet (correctly,
per the row above — the compiler should never write it). The fix is just
clicking **Refresh** once the report opens; the banner won't reappear once
Desktop has cached a successful load. **This is a genuinely separate
situation from the M-escaping partition-load failure described in §2.12**
— that bug produces the *same visible banner text*, which is exactly what
makes it easy to wrongly write off a real bug as "oh, that's just the
first-open thing." If the banner persists after clicking Refresh (rather
than resolving on the first refresh), treat that as a real signal something
in that table's partition is actually broken, not as more of the expected
first-open behavior.

---

## 3. ID conventions

Two different ID schemes appear in this format and they're easy to conflate:

| ID type | Format | Where used | Compiler should... |
|---|---|---|---|
| **Folder/file IDs** (page, visual) | 20-char lowercase hex-looking string, e.g. `3e33d29435230b0ab08c` | page/visual folder names, `pages.json.pageOrder`, `page.json.name`, `visual.json.name` | generate via any unique string (don't need to match Power BI's exact algorithm — Desktop accepted hand-rolled IDs in community tooling); deterministic slugs (e.g. hash of page title) are fine and make debugging easier than random hex |
| **`filterConfig.filters[].name`** | 20-char lowercase hex-looking string in the sample (e.g. `727e3430200492813fb3`), but the *actual* constraint is **1–50 characters, confirmed via Desktop schema validation** — the sample's length is incidental, not a hard requirement | `filterConfig.filters[].name` only (§2.8's new filter section) | treat as its own namespace: unique **within that visual's `filters[]` array** is all that's required (no cross-file consistency to maintain, unlike folder IDs which must match across folder name + `.json.name` + `pages.json`); **if building this ID by concatenating a namespace/visual-id with a per-field suffix, reserve room for the suffix first and truncate only the namespace portion to stay under 50 chars** — truncating the whole concatenated string can cut into the part that makes filters on the same visual distinct from each other, producing silent duplicate names (confirmed cause of a real Desktop crash — see §2.8's filter-type/name notes) |
| **`lineageTag` / relationship / logicalId** | standard UUID v4, e.g. `8ef6fb8b-8202-48dc-a192-74f450445b68` | every TMDL `lineageTag`, `.platform` `logicalId`, `relationship <guid>` | use a real `uuid.uuid4()` — these appear to be genuine GUIDs throughout, unlike the folder IDs |

**Confirmed by manual test (April, this session):** Power BI Desktop does
**not** require Microsoft's exact ID generation algorithm — only internal
consistency. Renaming a visual folder + its `visual.json` `name` field to
`viz11`, and a page folder + its `page.json` `name` field + its entry in
`pages.json.pageOrder`/`activePageName` to `page1`, opened cleanly in
Desktop. The hex-looking strings in the original export are just Microsoft's
own generation convention, not a format requirement.

**Compiler decision: use human-readable deterministic slugs**, not random
hex or UUIDs, for page/visual folder+`name` values. E.g. `page_overview`,
`viz_total_cost_card`, `viz_doctor_patients_bar`. This makes generated
projects far easier to debug — you can `grep` for a visual by what it is
rather than by an opaque ID — and removes one source of bugs (ID mismatch
between folder name and JSON `name` field) since deterministic slugs built
from KPI/page names are naturally less error-prone to template than
generating-then-threading random IDs through multiple files.

Note this only applies to **folder/file IDs** (page, visual). `lineageTag`,
`logicalId`, and `relationship` GUIDs are a different ID class — those are
real UUIDs used by Power BI's internal change-tracking and should still be
generated as genuine `uuid.uuid4()` values, not slugs.

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

### 4.1 Known issue outside this document's scope — investigated, defensively mitigated

Not a PBIR-format fact, and not something the serialiser is responsible for
— tracked here because it took real investigation to place correctly.
During report-generation debugging, a generated visual's title rendered as
**"Average Monthly Income by Department by Department"**. Cosmetic only
(doesn't affect load, data, or structure).

**Correction to an earlier version of this note:** this was first assumed
to be a "title-builder appending `by {category}`" bug living in
`builder.py`. Having since read `builder.py`, `serialiser.py`, and
`domain_kpi.py` end to end, **that's not what's happening — there is no
string concatenation, `.format()`, or f-string anywhere in any of the three
that appends `"by {category}"` (or anything else) onto a title or KPI
name.** Specifically:

- `domain_kpi.py`'s `run_domain_kpi()` never builds `kpi.name` itself — it's
  whatever free-form string the LLM returns for that field, passed through
  (`state.kpi_specs = result.kpi_specs`) with no post-processing. The
  module's own system prompt explicitly *models* `"by <dimension>"` as
  good KPI-name phrasing (its worked example is literally `"Total Revenue
  by Country"`) — so a name ending in `"by Department"` is the LLM doing
  exactly what it was asked to do, not a defect.
- `builder.py`'s `_build_visuals()` (pre-fix) set `title=kpi.name` — a bare
  passthrough, no transformation.
- `serialiser.py`'s `_visual_container_objects()` places whatever
  `title_text` it's given straight into the `text` literal — also a bare
  passthrough.

**This was also checked against all 3 real KPI-generation outputs
available** (`chinook_kpis.json`, `hr_kpis.json`, `online_retail_kpis.json`)
and **none of their 15 KPI names contain this duplication** — the closest
is `hr_kpis.json`'s `"Average Monthly Income by Job Role"`, grouped by Job
Role, not Department, so it isn't the same KPI as the one that showed the
bug. The exact triggering name was generated on a different LLM run than
any sample available for inspection here.

**Most likely explanation, unconfirmed:** the LLM-generated name already
ended in `"by Department"`, and Power BI Desktop's own category-axis title
rendering for grouped visuals appended a second, independently-generated
`"by {category}"` on top of the static title text — a naming collision
between LLM phrasing and a Desktop UI convention, not a pipeline bug. This
remains unconfirmed since it would need a Desktop-rendered screenshot (or
the exact triggering KPI name) to verify against; treat it as the leading
theory, not an established fact.

**What's actually been done, since the true root cause can't be confirmed
from this codebase:** a **defensive guard**, not a root-cause fix, has been
added in `builder.py` — `_dedupe_trailing_by_phrase()`, applied to the
`title` field only in `_build_visuals()`. It collapses an exact trailing
`"...by X by X"` repeat (case-insensitive, loop-collapses 3+ repeats) down
to a single `"...by X"`, and leaves every other name — including one with
two genuinely different trailing `"by"` phrases, e.g. `"Revenue by Country
by Region"` — completely untouched. Verified against all 15 real KPI names
across the 3 uploaded files plus 10 synthetic edge cases (the exact bug
string, a case variation, a triple repeat, trailing whitespace, a
`"Nearby"` word-boundary trap, empty input) before being wired in; deployed
as a single-line change (`title=kpi.name` → `title=_dedupe_trailing_by_phrase(kpi.name)`)
plus one new helper function, with `visual_id`, `measure_ref`, and
`category_ref` left keyed off the original, untouched `kpi.name` exactly as
before. **If the true mechanism is confirmed to be Desktop's own title
auto-generation** (rather than the LLM ever producing a literally duplicated
name), this guard would still help in the case where an LLM name coincides
with Desktop's convention, but the more complete fix at that point would be
in how the compiler requests/sets the title, not just cleaning up its text
after the fact — worth revisiting if this resurfaces.

---

## 5. Fixed vs Dynamic — summary table

| Category | Files / fields | Compiler action |
|---|---|---|
| **Fully fixed, copy verbatim** | `database.tmdl`, `version.json`, `definition.pbism`, theme JSONs, `DateTableTemplate`/`LocalDateTable` DAX bodies (except GUIDs and the one M formula substitution), trailing TMDL annotations, all visual `objects`/`visualContainerObjects` cosmetic blocks (note: `tableEx` and `lineChart` samples both ship with little-to-no `objects`/`visualContainerObjects` at all — an empty/near-empty template is a valid fixed template for those types, not a sign something's missing), currency `PBI_FormatHint` blocks | Bundle as static templates |
| **Fixed shell, dynamic IDs only** | `.platform` (×2), `definition.pbir`, page/visual slugs (confirmed: human-readable, not hex — see §3), `lineageTag`/`logicalId`/relationship UUIDs everywhere | Template + ID injection |
| **Fixed structure, dynamic content** | `report.json` (theme name could vary), `page.json` (displayName, name), TMDL `column`/`measure` blocks | Template + field substitution from Profiler/KPI output |
| **Fully dynamic, generated per run** | `pages.json.pageOrder`, every `visual.json.query.queryState` field binding, `filterConfig.filters[]` (§2.8, one entry per bound field), the M `partition.source` script, `model.tmdl`'s `ref table` list, `LocalDateTable_<guid>.tmdl`'s min/max M formula per date column | Core compiler logic — this is where your Domain/KPI + Profiler outputs actually become Power BI artifacts |
| **Exclude entirely** | `localSettings.json` (×2), `cache.abf`, `editorSettings.json`, `diagramLayout.json`, `cultures/en-US.tmdl` | Never write these; Desktop regenerates on open |

**Visual-type-specific role shapes** (the thing most likely to bite you if
you template across types too aggressively — see §2.8, §2.8.1, §2.8.2 for
full detail):

| `visualType` | Role(s) | Grouping field location | Notes |
|---|---|---|---|
| `cardVisual` | `Data` | n/a (single measure) | simplest — build/test this first |
| `clusteredColumnChart` | `Category`, `Y` | plain `Column` in `Category` | `Category` is a flat single projection unless the bound column is date-typed (then treat it like `lineChart`'s hierarchy case) |
| `pivotTable` | `Rows`, `Values` | separate `Rows` role | grouping column(s) NOT inside `Values` |
| `tableEx` | `Values` only | inside `Values`, sibling to measures | **no `Rows` role** — the #1 way to accidentally break this by copying the `pivotTable` template |
| `lineChart` | `Category`, `Y` | plain `Column` in `Category`, UNLESS date-typed | date-typed `Category` requires the full 4-level `HierarchyLevel` group (§2.8.2) — never a single-level binding |

**Practical priority order for the compiler build-out:**
1. `report.json` + `version.json` + `.platform` ×2 + `definition.pbir` + `definition.pbism` + `database.tmdl` — static skeleton, do once.
2. `<table>.tmdl` partition's M query (CSV ingestion + type casting) — without this nothing loads.
3. `<table>.tmdl` columns + measures — schema + your KPIs as DAX.
4. `model.tmdl`'s `ref table` list — must match what you wrote in (2)/(3).
5. `pages.json` + `page.json` × N — page scaffolding, using deterministic slugs (§3).
6. `visual.json` × N — the query/field-binding logic, by far the most complex piece; build and test one visual type (e.g. `cardVisual`, simplest) end-to-end before generalizing. Suggested build order given the role-shape table above: `cardVisual` → `clusteredColumnChart` (introduces `Category`/`Y` split) → `pivotTable` (introduces the separate `Rows` role) → `tableEx` (same field-binding vocabulary as `pivotTable` but flattened back into one role — good regression check that your `Column`/`Measure` binding logic doesn't assume a `Rows` role exists) → `lineChart` (introduces the date-hierarchy branch, the most complex single piece — build the non-date-column case first, matching `clusteredColumnChart`'s `Category`, then add the `HierarchyLevel` branch). Attach the fixed `objects`/`visualContainerObjects` template per visual type (§2.8) and the `PBI_FormatHint` template on currency columns (§2.12) at this stage — they're copy-paste, not new logic. Emit `filterConfig` with one filter per bound field (§2.8) for every visual, setting `type` per field kind — `"Categorical"` for `Column`, `"Advanced"` for `Measure` — per the confirmed rule there.
7. Auto-date tables: `LocalDateTable_<guid>.tmdl` per date column + one `DateTableTemplate_<guid>.tmdl` + `relationships.tmdl` + the `variation` block on each date column — confirmed in-scope for v1 (§2.13), built as an isolated, independently-testable post-step once a date column is detected, not blocking steps 1–6.