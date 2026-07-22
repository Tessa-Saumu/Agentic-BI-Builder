"""
Power Query M partition-source builder.

Extracted from serialiser.py's original "Power Query M partition-source
builder" section (the module docstring's own sectioning). Builds the
Power Query M script for a table's `partition` block
(pbir_reference.md Section 2.12).

CSV only, matching what pbir_reference.md documents and confirms
against a real reverse-engineered export: Csv.Document(...) ->
Table.PromoteHeaders -> Table.TransformColumnTypes. Cleaning steps
(Table.ReplaceValue etc.) are explicitly out of scope per the
reference doc -- only promote-headers + type-casting.

_build_m_partition_source is exercised directly by its own unit tests
in tests/test_pbir_compiler.py (TestTMDLFormatting), in addition to
being used internally by tmdl.py's _build_table_tmdl. serialiser.py
re-exports it so `from pbir.compiler.serialiser import
_build_m_partition_source` continues to work unchanged.
"""
from __future__ import annotations

import ntpath
import posixpath
from pathlib import Path

from pbir.models.column import Column
from pbir.models.dtypes import dax_type_to_m_type


# =====================================================================
# Power Query M partition-source builder
#
# Builds the Power Query M script for a table's `partition` block
# (pbir_reference.md §2.12).
#
# CSV only, matching what pbir_reference.md documents and confirms
# against a real reverse-engineered export: Csv.Document(...) ->
# Table.PromoteHeaders -> Table.TransformColumnTypes. Cleaning steps
# (Table.ReplaceValue etc.) are explicitly out of scope per the
# reference doc -- only promote-headers + type-casting.
# =====================================================================


def _m_escape_text_literal(value: str) -> str:
    r"""
    Escapes a string for embedding inside an M double-quoted text literal.

    BUG FIX (was the cause of "some tables have incomplete or no data"):
    M's *only* string-escape mechanism is doubling the quote character
    ("" -> a literal "). Unlike Python/C/JSON, backslash has NO special
    meaning inside an M text literal -- it is always a literal character.
    Confirmed directly against pbir_reference.md's own reverse-engineered
    File.Contents(...) call, which embeds a raw Windows path with single,
    un-doubled backslashes (e.g. "C:\Users\ingex\...\Health_Dirty.xlsx").

    The previous version of this function did
    `csv_path.replace("\\", "\\\\")`, which doubled every backslash in
    the absolute CSV path before it was embedded in the M script. M does not
    collapse "\\\\" back down to a single backslash the way Python/JSON
    do, so Csv.Document(File.Contents(...)) ended up trying to open a path
    that literally contained doubled separators and therefore didn't match
    any file on disk -- Power BI Desktop then opens the report with that
    table's partition failing to resolve, which is exactly the "some tables
    have incomplete or no data" dialog. The fix is to leave backslashes
    alone and only double literal quote characters.
    """
    return value.replace('"', '""')


def _build_m_partition_source(csv_path: str, columns: list[Column]) -> str:
    """
    Returns the full M `let...in` script as a string, e.g.:

        let
            Source = Csv.Document(File.Contents("data/raw/hr.csv"), [Delimiter=",", Columns=35, Encoding=65001, QuoteStyle=QuoteStyle.None]),
            #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
            #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{"Age", Int64.Type}, ...})
        in
            #"Changed Type"

    csv_path is resolved to an absolute path only if it's relative --
    already-absolute paths (POSIX or Windows) are left untouched, since
    Path.resolve() on a POSIX runner would mangle a Windows-style absolute
    path (e.g. "C:\\Users\\...") rather than recognize it as already
    resolved. A relative path fails to load in Power BI Desktop with
    "supplied file path must be a valid absolute path", since Power Query's
    File.Contents(...) has no notion of "relative to the .pbip file".
    """
    n_cols = len(columns)
    if posixpath.isabs(csv_path) or ntpath.isabs(csv_path):
        abs_csv_path = csv_path
    else:
        abs_csv_path = str(Path(csv_path).resolve())
    m_path = _m_escape_text_literal(abs_csv_path)

    type_pairs = ", ".join(
        f'{{"{_m_escape_text_literal(col.source_column)}", {dax_type_to_m_type(col.data_type)}}}'
        for col in columns
    )

    lines = [
        "let",
        f'    Source = Csv.Document(File.Contents("{m_path}"), '
        f'[Delimiter=",", Columns={n_cols}, Encoding=65001, QuoteStyle=QuoteStyle.None]),',
        '    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
        f'    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers", {{{type_pairs}}})',
        "in",
        '    #"Changed Type"',
    ]
    return "\n".join(lines)

