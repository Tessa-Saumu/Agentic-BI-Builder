"""
scripts/prepare_chinook_csv.py

Reads the 4 tables specified (Invoice, InvoiceLine, Track, Artist)
from the Chinook SQLite database, joins them into one analysis-ready
dataframe, and exports the result to data/raw/chinook.csv -- the CSV path
this project's CSV-only PBIR compiler expects (chinook.sqlite itself is
never read by the compiler; this script is the one-time bridge between the
SQLite source and the CSV the rest of the pipeline uses).

Only these 4 named tables are joined, plus Album -- see "WHY ALBUM IS READ"
below for why that 5th table is unavoidable, not a choice. No other table
(e.g. Genre) is read. 

WHY ALBUM IS READ (referentially required, not a choice): Track does not
join directly to Artist in the real schema (confirmed against the actual
chinook.sqlite schema) -- the only path is:
    InvoiceLine.TrackId -> Track.TrackId
    Track.AlbumId       -> Album.AlbumId
    Album.ArtistId      -> Artist.ArtistId
There is no way to join Track to Artist -- which the spec explicitly
requires, naming both tables -- without Album as an intermediate table.
This is a hard schema fact, not a judgment call about scope.

GRAIN DECISION: the output has ONE ROW PER INVOICE, not
one row per invoice line. This matters because:

  - Invoice.Total, Invoice.InvoiceDate, Invoice.BillingCountry, etc. are
    already correct at invoice grain -- every existing chinook_kpis.json
    KPI (Total Revenue, Monthly Revenue Trend, Revenue by Billing Country,
    Top Customers by Total Spend, Average Order Value) uses ONLY these
    Invoice-level columns.
  - InvoiceLine/Track/Artist are naturally at invoice-LINE grain (one row
    per line item, ~5.4 lines per invoice on average). Joining them in at
    that grain would repeat each invoice's Total once per line item --
    SUM(Total) over such a join would silently overcount revenue by a
    factor of however many lines that invoice had, breaking every existing
    KPI without any error or warning. A raw line-grain join is therefore
    NOT "analysis-ready" by itself -- getting to something that actually
    deserves that name is what requires the aggregation step below.
  - So: InvoiceLine/Track/Album/Artist are joined and then AGGREGATED back
    down to one row per InvoiceId (track_count, distinct_artists_purchased,
    distinct_tracks_purchased, primary_artist) BEFORE being merged onto
    Invoice. This keeps every existing Invoice-level column and KPI
    exactly as-is, while adding music-catalog context columns derivable
    from exactly the 4 named tables plus the join-path-required Album --
    nothing beyond that.

Usage:
    python -m scripts.prepare_chinook_csv
    python -m scripts.prepare_chinook_csv --sqlite-path path/to/chinook.sqlite --output path/to/output.csv
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DEFAULT_SQLITE_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "raw", "chinook.sqlite")
)
DEFAULT_OUTPUT_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "raw", "chinook.csv")
)

# The 9 original Invoice columns, unchanged, plus 4 new aggregated
# music-catalog columns derived from InvoiceLine/Track/Album/Artist. Used
# by validate_output() to confirm nothing is silently missing from the
# exported CSV.
EXPECTED_COLUMNS = [
    "InvoiceId",
    "CustomerId",
    "InvoiceDate",
    "BillingAddress",
    "BillingCity",
    "BillingState",
    "BillingCountry",
    "BillingPostalCode",
    "Total",
    "track_count",
    "distinct_artists_purchased",
    "distinct_tracks_purchased",
    "primary_artist",
]


def _read_tables(sqlite_path: str) -> dict[str, pd.DataFrame]:
    """
    Reads exactly Invoice, InvoiceLine, Track, Artist -- the 4 tables
    specified -- plus Album, which is read solely because it is
    the only path from Track to Artist in the real schema (see module
    docstring's "WHY ALBUM IS READ"). No other table is read.
    """
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"Chinook SQLite database not found at: {sqlite_path}")

    conn = sqlite3.connect(sqlite_path)
    try:
        tables = {
            "Invoice": pd.read_sql_query("SELECT * FROM Invoice", conn),
            "InvoiceLine": pd.read_sql_query("SELECT * FROM InvoiceLine", conn),
            "Track": pd.read_sql_query("SELECT * FROM Track", conn),
            "Artist": pd.read_sql_query("SELECT * FROM Artist", conn),
            "Album": pd.read_sql_query("SELECT * FROM Album", conn),
        }
    finally:
        conn.close()
    return tables


def _build_line_item_join(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Joins InvoiceLine -> Track -> Album -> Artist at invoice-LINE grain
    (one row per InvoiceLine, matching InvoiceLine's own row count --
    every Track has exactly one Album, and every Album has exactly one
    Artist, so neither join fans out). This is an intermediate result,
    aggregated back to invoice grain by _aggregate_to_invoice_grain()
    below -- never exported or merged onto Invoice at this grain.
    """
    line_items = tables["InvoiceLine"].merge(
        tables["Track"][["TrackId", "AlbumId"]], on="TrackId", how="left"
    )
    line_items = line_items.merge(
        tables["Album"][["AlbumId", "ArtistId"]], on="AlbumId", how="left"
    )
    line_items = line_items.merge(
        tables["Artist"][["ArtistId", "Name"]].rename(columns={"Name": "ArtistName"}),
        on="ArtistId",
        how="left",
    )
    return line_items


def _mode_with_alphabetical_tiebreak(series: pd.Series) -> object:
    """
    Returns the most frequent value in `series` (e.g. the artist with the
    most line items on a given invoice). Ties are broken alphabetically by
    value, not by insertion/row order, so the result is deterministic
    across repeated runs regardless of the original row order in the
    SQLite tables -- pandas' own Series.mode() already returns ties in
    sorted order, so sorting again here is redundant but kept explicit
    rather than relying on that implementation detail silently continuing
    to hold in a future pandas version.
    """
    counts = series.value_counts()
    top_count = counts.iloc[0]
    tied = sorted(counts[counts == top_count].index)
    return tied[0]


def _aggregate_to_invoice_grain(line_items: pd.DataFrame) -> pd.DataFrame:
    """
    Collapses the invoice-line-grain join back to one row per InvoiceId --
    see module docstring's GRAIN DECISION for why this step is required
    rather than optional.
    """
    grouped = line_items.groupby("InvoiceId")
    summary = grouped.agg(
        track_count=("TrackId", "count"),
        distinct_artists_purchased=("ArtistId", "nunique"),
        distinct_tracks_purchased=("TrackId", "nunique"),
    )
    summary["primary_artist"] = grouped["ArtistName"].apply(_mode_with_alphabetical_tiebreak)
    return summary.reset_index()


def build_chinook_dataframe(sqlite_path: str = DEFAULT_SQLITE_PATH) -> pd.DataFrame:
    """
    Full pipeline: read tables -> join at line grain -> aggregate to
    invoice grain -> left-merge onto Invoice (preserving every Invoice row
    and column exactly as-is; an invoice with zero matching line items,
    if one existed, would get NaN aggregate columns rather than being
    dropped -- LEFT join, not INNER).
    """
    tables = _read_tables(sqlite_path)
    line_items = _build_line_item_join(tables)
    invoice_summary = _aggregate_to_invoice_grain(line_items)

    merged = tables["Invoice"].merge(invoice_summary, on="InvoiceId", how="left")
    return merged


def validate_output(df: pd.DataFrame) -> list[str]:
    """
    Returns a list of validation problems (empty list = all good). Checked:
      - the dataframe is non-empty
      - every expected column is present
      - InvoiceId is unique (confirms the aggregation truly collapsed back
        to one row per invoice, not a silent fan-out from a join bug)
    """
    problems = []

    if df.empty:
        problems.append("Output dataframe is empty (0 rows).")

    missing_cols = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing_cols:
        problems.append(f"Missing expected column(s): {missing_cols}")

    if "InvoiceId" in df.columns and df["InvoiceId"].duplicated().any():
        n_dupes = df["InvoiceId"].duplicated().sum()
        problems.append(
            f"InvoiceId is not unique ({n_dupes} duplicate row(s)) -- the "
            f"aggregation step did not correctly collapse to invoice grain."
        )

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", type=str, default=DEFAULT_SQLITE_PATH)
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    print(f"Reading Chinook tables from: {args.sqlite_path}")
    df = build_chinook_dataframe(args.sqlite_path)

    problems = validate_output(df)
    if problems:
        print("VALIDATION FAILED:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False)

    print(f"Wrote {len(df)} rows, {len(df.columns)} columns to {args.output}")
    print(f"Columns: {list(df.columns)}")


if __name__ == "__main__":
    main()