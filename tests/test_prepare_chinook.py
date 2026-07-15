"""
tests/test_prepare_chinook.py — unit tests for the Chinook CSV
preparation script's aggregation and validation logic.

Does not require the real chinook.sqlite file on disk -- builds small
synthetic DataFrames matching the real schema shape instead, so this
suite runs anywhere without a data dependency.

Scope note: this script joins exactly the 4 tables specified
(Invoice, InvoiceLine, Track, Artist) plus Album (referentially required
to reach Artist from Track -- see the script's own module docstring).
Genre is NOT read or joined -- it isn't one of the named 4, and Album is
the only 5th table that's unavoidable, not a design choice. These tests
reflect exactly that scope.
"""
import pandas as pd
import pytest

from scripts.prepare_chinook import (
    EXPECTED_COLUMNS,
    _aggregate_to_invoice_grain,
    _mode_with_alphabetical_tiebreak,
    validate_output,
)


class TestModeWithAlphabeticalTiebreak:
    def test_clear_majority_wins(self):
        s = pd.Series(["AC/DC", "AC/DC", "AC/DC", "Queen"])
        assert _mode_with_alphabetical_tiebreak(s) == "AC/DC"

    def test_genuine_tie_breaks_alphabetically(self):
        s = pd.Series(["Queen", "AC/DC", "Queen", "AC/DC"])
        assert _mode_with_alphabetical_tiebreak(s) == "AC/DC"

    def test_three_way_tie_breaks_alphabetically(self):
        s = pd.Series(["Queen", "AC/DC", "Aerosmith"])
        assert _mode_with_alphabetical_tiebreak(s) == "AC/DC"

    def test_single_value(self):
        s = pd.Series(["Queen"])
        assert _mode_with_alphabetical_tiebreak(s) == "Queen"


class TestAggregateToInvoiceGrain:
    def _line_items(self) -> pd.DataFrame:
        """
        Synthetic invoice-line-grain data (InvoiceLine -> Track -> Album
        -> Artist join result, no Genre column at all): invoice 1 has 3
        lines across 2 artists; invoice 2 has 1 line.
        """
        return pd.DataFrame(
            {
                "InvoiceId": [1, 1, 1, 2],
                "InvoiceLineId": [10, 11, 12, 20],
                "TrackId": [100, 101, 102, 200],
                "AlbumId": [1000, 1000, 1001, 1002],
                "ArtistId": [1, 1, 2, 3],
                "ArtistName": ["AC/DC", "AC/DC", "Aerosmith", "Queen"],
            }
        )

    def test_one_row_per_invoice(self):
        result = _aggregate_to_invoice_grain(self._line_items())
        assert len(result) == 2
        assert set(result["InvoiceId"]) == {1, 2}

    def test_no_genre_columns_anywhere(self):
        """Genre is not one of the 4 named tables (plus Album) -- confirm
        the aggregation output never produces a genre-related column."""
        result = _aggregate_to_invoice_grain(self._line_items())
        assert "primary_genre" not in result.columns
        assert not any("genre" in c.lower() for c in result.columns)

    def test_track_count_is_line_count_not_distinct(self):
        result = _aggregate_to_invoice_grain(self._line_items())
        invoice_1 = result[result["InvoiceId"] == 1].iloc[0]
        assert invoice_1["track_count"] == 3

    def test_distinct_artists_purchased(self):
        result = _aggregate_to_invoice_grain(self._line_items())
        invoice_1 = result[result["InvoiceId"] == 1].iloc[0]
        assert invoice_1["distinct_artists_purchased"] == 2  # AC/DC, Aerosmith

    def test_distinct_tracks_purchased(self):
        result = _aggregate_to_invoice_grain(self._line_items())
        invoice_1 = result[result["InvoiceId"] == 1].iloc[0]
        assert invoice_1["distinct_tracks_purchased"] == 3  # tracks 100, 101, 102

    def test_primary_artist_is_the_majority_artist(self):
        result = _aggregate_to_invoice_grain(self._line_items())
        invoice_1 = result[result["InvoiceId"] == 1].iloc[0]
        assert invoice_1["primary_artist"] == "AC/DC"  # 2 lines vs Aerosmith's 1

    def test_single_line_invoice(self):
        result = _aggregate_to_invoice_grain(self._line_items())
        invoice_2 = result[result["InvoiceId"] == 2].iloc[0]
        assert invoice_2["track_count"] == 1
        assert invoice_2["distinct_artists_purchased"] == 1
        assert invoice_2["primary_artist"] == "Queen"


class TestValidateOutput:
    def _valid_df(self) -> pd.DataFrame:
        return pd.DataFrame({col: [1, 2] for col in EXPECTED_COLUMNS} | {"InvoiceId": [1, 2]})

    def test_valid_dataframe_passes(self):
        assert validate_output(self._valid_df()) == []

    def test_empty_dataframe_fails(self):
        empty = pd.DataFrame(columns=EXPECTED_COLUMNS)
        problems = validate_output(empty)
        assert len(problems) >= 1
        assert any("empty" in p.lower() for p in problems)

    def test_missing_column_fails(self):
        df = self._valid_df().drop(columns=["primary_artist"])
        problems = validate_output(df)
        assert any("primary_artist" in p for p in problems)

    def test_duplicate_invoice_id_fails(self):
        df = self._valid_df()
        df["InvoiceId"] = [5, 5]  # force a duplicate
        problems = validate_output(df)
        assert any("duplicate" in p.lower() for p in problems)

    def test_multiple_problems_all_reported(self):
        df = pd.DataFrame(columns=["InvoiceId"])  # empty AND missing columns
        problems = validate_output(df)
        assert len(problems) >= 2

    def test_expected_columns_has_no_genre_reference(self):
        """Guards against Genre-related columns silently creeping back in."""
        assert "primary_genre" not in EXPECTED_COLUMNS
        assert not any("genre" in c.lower() for c in EXPECTED_COLUMNS)