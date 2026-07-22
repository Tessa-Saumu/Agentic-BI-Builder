"""
Page-grouping and canvas layout.

Extracted from builder.py's original "Page-grouping and canvas layout"
section (the module docstring's own sectioning).

Grouping rule (per the agreed plan): cards are small and fit up to 3
per page; chart/table visuals need more room and fit up to 2 per
page. Greedily bucket cards separately from chart/table types, fill
pages up to their cap, and merge a trailing under-filled page forward
so no page (other than possibly the very first, if there's only one
KPI total) ends up with fewer than 2 visuals when more than one page
would otherwise exist.

Canvas: standard 1280x720 (Section 2.7). Layout uses a simple
non-overlapping grid; Position values are unconstrained floats per
Section 2.8, so any non-overlapping placement is valid -- exact pixel
aesthetics aren't a compiler concern here.

Public names (group_into_pages, layout_page) are exercised directly by
their own unit test suites in tests/test_pbir_compiler.py, in addition
to being used internally by builder.run_pbir_compiler. builder.py
re-exports both so `from pbir.compiler.builder import group_into_pages,
layout_page` continues to work unchanged for any existing
caller/test.
"""
from __future__ import annotations

from typing import List, Sequence

from pbir.models.visual import Visual, Position


CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720
CARDS_PER_PAGE = 3
CHARTS_PER_PAGE = 2

_CARD_TYPES = {"card"}
_WIDE_TYPES = {"barChart", "lineChart", "table"}


def group_into_pages(visuals: Sequence[Visual]) -> List[List[Visual]]:
    """
    Buckets visuals (already built, without final position) into page-sized
    groups. Returns a list of visual-lists; caller assigns page display
    names and calls layout_page() to set final positions.
    """
    cards = [v for v in visuals if v.chart_type in _CARD_TYPES]
    wide = [v for v in visuals if v.chart_type in _WIDE_TYPES]

    pages: List[List[Visual]] = []
    for i in range(0, len(cards), CARDS_PER_PAGE):
        pages.append(cards[i : i + CARDS_PER_PAGE])
    for i in range(0, len(wide), CHARTS_PER_PAGE):
        pages.append(wide[i : i + CHARTS_PER_PAGE])

    # Merge a trailing under-filled page (fewer than 2 visuals) into the
    # previous page, as long as doing so doesn't push that page over its
    # type's own cap and there's more than one page to merge into.
    if len(pages) > 1 and len(pages[-1]) < 2:
        last = pages[-1]
        prev = pages[-2]
        cap = CARDS_PER_PAGE if all(v.chart_type in _CARD_TYPES for v in last) else CHARTS_PER_PAGE
        if len(prev) + len(last) <= max(cap, CARDS_PER_PAGE):
            pages[-2] = prev + last
            pages.pop()

    return pages


def layout_page(visuals: Sequence[Visual]) -> None:
    """
    Mutates each Visual's .position in place for a single page, arranging
    them left-to-right in one row if they fit, else wrapping to a second row.
    Cards get smaller boxes than charts/tables since more of them share a page.
    """
    n = len(visuals)
    if n == 0:
        return

    is_card_page = all(v.chart_type in _CARD_TYPES for v in visuals)

    if is_card_page:
        # Up to 3 cards, single row, evenly spaced.
        card_width = CANVAS_WIDTH // n
        card_height = 200
        for i, v in enumerate(visuals):
            v.position = Position(
                x=i * card_width,
                y=40,
                z=i * 1000,
                width=card_width - 20,
                height=card_height,
                tab_order=i,
            )
        return

    # Chart/table pages: up to 2 side by side; if 3 (after a merge), 2 on
    # top row + 1 centered on a second row.
    if n <= 2:
        width = CANVAS_WIDTH // n
        height = CANVAS_HEIGHT - 40
        for i, v in enumerate(visuals):
            v.position = Position(
                x=i * width,
                y=0,
                z=i * 1000,
                width=width - 10,
                height=height,
                tab_order=i,
            )
    else:
        # 3 visuals: 2 on top row, 1 centered below.
        top_width = CANVAS_WIDTH // 2
        top_height = CANVAS_HEIGHT // 2
        for i in range(2):
            visuals[i].position = Position(
                x=i * top_width,
                y=0,
                z=i * 1000,
                width=top_width - 10,
                height=top_height - 10,
                tab_order=i,
            )
        visuals[2].position = Position(
            x=CANVAS_WIDTH // 4,
            y=top_height,
            z=2000,
            width=top_width - 10,
            height=top_height - 10,
            tab_order=2,
        )

