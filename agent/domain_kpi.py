"""
Domain/KPI node — LLM-powered (Gemini or Mistral, switchable via LLM_PROVIDER).

Takes DataProfile and returns:
  - DomainHypothesis (domain label + confidence + reasoning)
  - Exactly 5 KPISpec objects (name, description, sql_query, chart_type, reasoning)

Structured output is enforced via native provider schema support (Pydantic
models passed directly to each SDK) — no free-form text parsing, no
LangChain. Generated SQL is deterministically validated against the actual
column names in the DataProfile before being accepted; a single repair
pass is attempted if validation fails.
"""
from __future__ import annotations

import json
import os
import re

from agent.models import DataProfile, DomainKPIResponse
from agent.state import AgentState

VALID_CHART_TYPES = ("card", "barChart", "lineChart", "table")

# SQLite-specific constraints the LLM must respect. Kept as a short bounded
# list rather than full dialect documentation — enough to keep generated SQL
# executable against sqlite3 without over-constraining the model's phrasing.
SQLITE_CONSTRAINTS = """\
- Target dialect is SQLite (Python's sqlite3). Only use syntax SQLite supports.
- Use LIMIT, not TOP, for row limiting.
- There is no BOOLEAN type; treat 0/1 or NULL checks as needed.
- Date/time columns are stored as TEXT. Use strftime(), date(), or datetime() \
for any date math, not dialect-specific date functions.
- No stored procedures, no window function fallback assumptions beyond \
SQLite 3.25+ (RANK, ROW_NUMBER, OVER are fine).
- Use double quotes only for identifiers if a column name requires escaping; \
use single quotes for string literals.
- Do not reference any table other than the single table being profiled; \
the table is always loaded into the query engine as "data" — always write \
FROM data (optionally with an alias, e.g. FROM data AS d), never the \
dataset's original source table name, even if source_table in the profile \
names something else (that field describes where the data came from, not \
what to call it in your SQL).
- Do not use INSERT, UPDATE, DELETE, DROP, or any DDL/DML other than SELECT.
- Prefer explicit column lists over SELECT * so results map cleanly to a chart.
- Every query must be a single, valid, standalone SELECT statement.
"""

SYSTEM_PROMPT = f"""You are a senior BI analyst. You will be given a dataset's \
schema profile — column names, inferred types, null rates, and cardinality \
only, with no actual data values. From this metadata alone, you must:

1. Infer the dataset's business domain (e.g. "e-commerce retail", \
"HR/payroll", "financial transactions").
2. Propose exactly 5 KPIs that are analytically meaningful for that domain \
and computable as SQL against the given columns.

Constraints on the SQL you generate:
{SQLITE_CONSTRAINTS}

Each KPI must specify a chart_type, which must be exactly one of:
{", ".join(VALID_CHART_TYPES)}
- "card": a single summary number (e.g. total revenue, average order value)
- "barChart": comparison across a categorical dimension
- "lineChart": a trend over time
- "table": a ranked or multi-column breakdown

Use ONLY the column names given in the profile. Do not invent columns.

Worked example (abbreviated):
Given a profile with table "data" and columns InvoiceNo (string), \
Quantity (integer), UnitPrice (float), InvoiceDate (string, datetime-like), \
Country (string) — a reasonable KPI is:
  name: "Total Revenue by Country"
  description: "Sum of (Quantity * UnitPrice) grouped by Country, \
identifying top revenue markets."
  sql_query: "SELECT Country, SUM(Quantity * UnitPrice) AS revenue FROM data \
GROUP BY Country ORDER BY revenue DESC"
  chart_type: "barChart"
  reasoning: "Revenue by market is a standard retail KPI and Country is a \
low-cardinality categorical column suited to a bar chart."

Respond only via the structured schema provided. Do not include any text \
outside the structured response.
"""


def _profile_to_prompt_context(profile: DataProfile) -> str:
    """
    Serialize a DataProfile into metadata-only prompt text.

    Deliberately excludes sample_values, min_value, and max_value — those are
    actual data values, not metadata, and the issue requires domain/KPI
    inference from schema metadata alone. Iterates profile.columns generically
    so adding/removing ColumnProfile fields elsewhere doesn't silently break
    the prompt.
    """
    lines = [
        f"source_table: {profile.source_table or 'data'}",
        f"row_count: {profile.row_count}",
        f"column_count: {profile.column_count}",
        "columns:",
    ]
    for col_name, col in profile.columns.items():
        lines.append(
            f"  - name: {col_name} | dtype: {col.inferred_dtype} | "
            f"null_rate: {col.null_rate:.4f} | distinct_count: {col.distinct_count} | "
            f"is_all_null: {col.is_all_null}"
        )
    return "\n".join(lines)


def _valid_column_names(profile: DataProfile) -> set[str]:
    return set(profile.columns.keys())


_IDENTIFIER_RE = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"|\b([A-Za-z_][A-Za-z0-9_]*)\b')
_STRING_LITERAL_RE = re.compile(r"'[^']*'")
# Matches `qualifier.column` (e.g. Invoice.Total, data.Country) so the
# qualifier can be treated as a table alias rather than a column reference.
_QUALIFIED_REF_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b')
# Matches `FROM x AS alias` / `FROM x alias` / `JOIN x AS alias` so declared
# table aliases are recognized and never flagged as unknown columns.
_TABLE_ALIAS_RE = re.compile(
    r'\b(?:FROM|JOIN)\s+[A-Za-z_][A-Za-z0-9_]*\s+(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b',
    re.IGNORECASE,
)

# SQL keywords/functions that will otherwise look like "unknown columns" to
# the naive identifier scan below.
_SQL_STOPWORDS = {
    "select", "from", "where", "group", "by", "order", "as", "and", "or",
    "not", "null", "is", "in", "on", "join", "left", "right", "inner",
    "outer", "sum", "avg", "count", "min", "max", "distinct", "case",
    "when", "then", "else", "end", "asc", "desc", "limit", "having",
    "between", "like", "strftime", "date", "datetime", "cast", "round",
    "data", "over", "partition", "rank", "row_number", "coalesce",
    "abs", "total", "with",
}


def _validate_sql_columns(kpi_specs: list, profile: DataProfile) -> list[str]:
    """
    Return a list of human-readable violation messages, one per KPI whose
    sql_query references an identifier that isn't a real column name (and
    isn't a SQL keyword/function). Best-effort lexical check, not a full SQL
    parser — sufficient to catch hallucinated column names, which is the
    acceptance criterion.
    """
    valid_cols = _valid_column_names(profile)
    valid_cols_lower = {c.lower() for c in valid_cols}
    violations = []

    for kpi in kpi_specs:
        # Remove string literal contents first — SQL string literals (e.g. the
        # '%Y-%m' format code inside strftime(...)) are not column references
        # and must not be tokenized as identifiers.
        sql_without_literals = _STRING_LITERAL_RE.sub("''", kpi.sql_query)

        # Table aliases declared via `FROM x AS alias` / `JOIN x alias` — these
        # are never column references and must be excluded from the check.
        declared_aliases = {m.lower() for m in _TABLE_ALIAS_RE.findall(sql_without_literals)}

        # Qualified references like `Invoice.Total`: the qualifier (`Invoice`)
        # is a table/alias reference, not a column, so it must never be
        # checked against the profile's columns. The part after the dot
        # (`Total`) IS a real column reference and must still be validated
        # normally — qualification doesn't exempt a hallucinated column name.
        qualified_pairs = _QUALIFIED_REF_RE.findall(sql_without_literals)
        qualifiers = {q.lower() for q, _ in qualified_pairs}

        # Strip qualifier.column pairs down to just the column part before the
        # general tokenizer runs, so the qualifier itself never becomes a
        # standalone token subject to the unknown-identifier check. The
        # unqualified column name flows into the normal token pool below and
        # is validated exactly like any other bare column reference.
        sql_for_tokenizing = _QUALIFIED_REF_RE.sub(lambda m: m.group(2), sql_without_literals)

        tokens = set()
        for quoted, bare in _IDENTIFIER_RE.findall(sql_for_tokenizing):
            tok = quoted or bare
            tokens.add(tok)

        unknown = []
        for tok in tokens:
            tok_lower = tok.lower()
            if tok_lower in _SQL_STOPWORDS:
                continue
            if tok in valid_cols or tok_lower in valid_cols_lower:
                continue
            if tok_lower in declared_aliases or tok_lower in qualifiers:
                continue
            if tok.isdigit():
                continue
            # Likely an alias (e.g. "revenue" defined by `AS revenue`) rather
            # than a source column — aliases are permitted since they don't
            # reference the underlying table.
            alias_pattern = rf"\bAS\s+{re.escape(tok)}\b"
            if re.search(alias_pattern, kpi.sql_query, flags=re.IGNORECASE):
                continue
            unknown.append(tok)

        if unknown:
            violations.append(
                f"KPI '{kpi.name}': sql_query references unrecognized identifier(s) "
                f"{sorted(set(unknown))} not present in DataProfile columns {sorted(valid_cols)}."
            )

    return violations


def _call_gemini(system_prompt: str, user_content: str, response_model: type = None):
    from google import genai

    if response_model is None:
        response_model = DomainKPIResponse

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Set it in your environment or .env file "
            "(e.g. `$env:GEMINI_API_KEY = \"...\"` in PowerShell, or `export "
            "GEMINI_API_KEY=...` in bash) before calling run_domain_kpi with "
            "LLM_PROVIDER=gemini. Get a key at https://aistudio.google.com/apikey."
        )

    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash")

    response = client.models.generate_content(
        model=model_name,
        contents=user_content,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_schema": response_model,
        },
    )
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return parsed
    return response_model.model_validate_json(response.text)


def _call_mistral(system_prompt: str, user_content: str, response_model: type = None):
    # mistralai v2.0.0 (2026-03) moved the Mistral client class's import path.
    # v1.x: `from mistralai import Mistral`
    # v2.x: `from mistralai.client import Mistral`
    # Support both so this doesn't break on whichever version is installed.
    try:
        from mistralai import Mistral  # v1.x
    except ImportError:
        from mistralai.client import Mistral  # v2.x

    if response_model is None:
        response_model = DomainKPIResponse

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MISTRAL_API_KEY is not set. Set it in your environment or .env file "
            "(e.g. `$env:MISTRAL_API_KEY = \"...\"` in PowerShell, or `export "
            "MISTRAL_API_KEY=...` in bash) before calling run_domain_kpi with "
            "LLM_PROVIDER=mistral. Get a key at https://console.mistral.ai/api-keys."
        )

    client = Mistral(api_key=api_key)
    model_name = os.environ.get("MISTRAL_MODEL", "mistral-large-latest")

    chat_response = client.chat.parse(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format=response_model,
        temperature=0,
    )
    parsed = chat_response.choices[0].message.parsed
    if parsed is not None:
        return parsed
    return response_model.model_validate_json(chat_response.choices[0].message.content)


def _call_llm(system_prompt: str, user_content: str, provider: str, response_model: type = None):
    """
    Dispatch a structured-output LLM call to the configured provider.

    response_model defaults to DomainKPIResponse (this module's own response
    type) when not given, so existing call sites in this file are unaffected.
    Other nodes (e.g. agent/reflector.py) pass their own Pydantic response
    model to reuse this same provider-dispatch logic instead of duplicating
    the Gemini/Mistral call plumbing.
    """
    if response_model is None:
        response_model = DomainKPIResponse

    if provider == "gemini":
        return _call_gemini(system_prompt, user_content, response_model=response_model)
    elif provider == "mistral":
        return _call_mistral(system_prompt, user_content, response_model=response_model)
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Expected 'gemini' or 'mistral'."
        )


def run_domain_kpi(state: AgentState) -> AgentState:
    """
    LangGraph node: infer domain + propose 5 KPIs from state.data_profile.

    Populates state.domain_hypothesis and state.kpi_specs on success.
    On failure (missing profile, LLM error, unrecoverable SQL-column
    violations after one repair attempt), appends a message to state.errors
    and leaves domain_hypothesis / kpi_specs unset.
    """
    if state.data_profile is None:
        state.errors.append("run_domain_kpi: state.data_profile is None; run the Profiler node first.")
        return state

    provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()
    profile = state.data_profile
    context = _profile_to_prompt_context(profile)
    user_content = f"Dataset profile:\n\n{context}\n\nPropose the domain hypothesis and 5 KPIs now."

    try:
        result = _call_llm(SYSTEM_PROMPT, user_content, provider)
    except Exception as exc:
        state.errors.append(f"run_domain_kpi: LLM call failed for provider '{provider}': {exc}")
        return state

    violations = _validate_sql_columns(result.kpi_specs, profile)

    if violations:
        first_attempt_sql_dump = "\n".join(
            f"  [{kpi.name}] {kpi.sql_query}" for kpi in result.kpi_specs
        )
        # One repair attempt: feed the violations back and ask for a fix.
        repair_content = (
            f"{user_content}\n\n"
            "Your previous response referenced columns that do not exist in the "
            "profile. Fix the following issues and return a corrected, complete "
            "structured response:\n" + "\n".join(f"- {v}" for v in violations)
        )
        try:
            result = _call_llm(SYSTEM_PROMPT, repair_content, provider)
        except Exception as exc:
            state.errors.append(f"run_domain_kpi: repair LLM call failed for provider '{provider}': {exc}")
            return state

        violations = _validate_sql_columns(result.kpi_specs, profile)
        if violations:
            # Include the raw SQL from both attempts so a failure is
            # diagnosable directly from the error message, without needing
            # to reproduce it separately.
            second_attempt_sql_dump = "\n".join(
                f"  [{kpi.name}] {kpi.sql_query}" for kpi in result.kpi_specs
            )
            state.errors.append(
                "run_domain_kpi: unresolved SQL column violations after repair attempt: "
                + "; ".join(violations)
                + "\nFirst-attempt SQL:\n" + first_attempt_sql_dump
                + "\nSecond-attempt (post-repair) SQL:\n" + second_attempt_sql_dump
            )
            return state

    state.domain_hypothesis = result.domain_hypothesis
    state.kpi_specs = result.kpi_specs
    return state


def save_kpi_output(state: AgentState, dataset_name: str, output_dir: str = "data/profiles") -> str:
    """
    Persist domain_hypothesis + kpi_specs to data/profiles/<dataset>_kpis.json.
    Returns the path written. Raises if run_domain_kpi hasn't populated state.
    """
    if state.domain_hypothesis is None or not state.kpi_specs:
        raise ValueError(
            f"save_kpi_output: state has no populated domain_hypothesis/kpi_specs "
            f"for dataset '{dataset_name}'. Run run_domain_kpi first."
        )

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{dataset_name}_kpis.json")

    payload = {
        "domain_hypothesis": state.domain_hypothesis.model_dump(),
        "kpi_specs": [k.model_dump() for k in state.kpi_specs],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return out_path