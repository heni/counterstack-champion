import pytest

from champion.board import Board
from champion.strategies.baseline import (
    DEFAULT_WEIGHTS,
    Weights,
    choose_placement,
    score,
)


def _board_from_lines(lines: list[str], width: int = 12) -> Board:
    height = 20
    rows = [[False] * width for _ in range(height)]
    pad = height - len(lines)
    for i, line in enumerate(lines):
        for x, ch in enumerate(line):
            if ch == "#":
                rows[pad + i][x] = True
    cells = tuple(tuple(r) for r in rows)
    return Board(width, height, cells)


def test_score_empty_board_is_zero():
    assert score(Board.empty()) == 0.0


def test_score_weighted():
    """sum_heights=10, holes=2, w_h=1, w_holes=2 → 10 + 4 = 14."""
    b = _board_from_lines([
        "############",  # y=18 — full row
        "##.#########",  # y=19 — gap at col 2 → 1 hole (col 2 empty under 18)
    ])
    # heights: 12 cols × 2 each = 24. Holes: col 2 has block at 18, empty at 19 → 1.
    s = score(b, Weights(w_h=1.0, w_holes=2.0))
    assert s == 24 + 2  # 24 + 1*2


def test_choose_placement_does_not_introduce_holes_on_cliff_terrain():
    """Cols 0..4 stacked to height 10, cols 5..11 empty — a cliff at x=4/5.
    Baseline must NOT drop the I-piece across the cliff (would create a row of holes).
    With only sum-of-heights+holes, flat-vs-tall is a tie (Phase 3 adds bumpiness),
    but the holes term breaks the across-cliff placements."""
    rows = [[False] * 12 for _ in range(20)]
    for y in range(10, 20):
        for x in range(5):
            rows[y][x] = True
    b = Board(12, 20, tuple(tuple(r) for r in rows))
    placement = choose_placement(b, "I", DEFAULT_WEIGHTS)
    assert placement is not None
    rot, x = placement
    new_b, _ = b.apply_lock("I", rot, x)
    assert new_b.holes() == b.holes(), (
        f"baseline introduced holes on cliff terrain: "
        f"chose rot={rot} x={x}, holes {b.holes()} → {new_b.holes()}"
    )


def test_choose_placement_completes_a_line():
    """Bottom row 11/12 full at col 0 only empty. Drop a 1×5 I-piece (rot=1)
    vertically into col 0: the I-piece touches y=15..19 in col 0 → bottom row
    becomes full → 1 line clear, post-state has very low heights."""
    b = _board_from_lines([
        ".###########",  # y=19, col 0 empty
    ])
    placement = choose_placement(b, "I", DEFAULT_WEIGHTS)
    rot, x = placement
    new_b, cleared = b.apply_lock("I", rot, x)
    assert cleared == 1, f"baseline should clear the line; got {cleared} on rot={rot} x={x}"


def test_choose_placement_avoids_creating_holes():
    """Stack with a 1-cell gap underneath an overhang. The piece could fill it (cleaner)
    or sit on top adding new holes (worse). Strategy with high w_holes picks the cleaner."""
    b = _board_from_lines([
        ".###########",  # y=18 — overhang at cols 1..11, col 0 empty
        "############",  # y=19 — full row
    ])
    # The overhang at y=18 means col 0 at y=19 is reachable only by (0,19).
    # heights are dominated by the overhang.
    # An I-vertical at x=0 fills (0, 15..19) → height col 0 = 5; but row y=19
    # was already full, so it clears immediately, dropping everything down by 1.
    # Holes go to 0 in this trace.
    placement = choose_placement(b, "I", DEFAULT_WEIGHTS)
    rot, x = placement
    new_b, cleared = b.apply_lock("I", rot, x)
    # Baseline should not increase holes from this terrain — pre-board has 0 holes,
    # and a sound placement preserves that.
    assert new_b.holes() == 0


def test_choose_placement_returns_none_when_no_legal_placement():
    """Stack reaching y=0 in all spawn columns of the X piece → no placement fits."""
    rows = [[True] * 12 for _ in range(20)]
    b = Board(12, 20, tuple(tuple(r) for r in rows))
    assert choose_placement(b, "X") is None


def test_choose_placement_deterministic_tiebreak():
    """On an empty board with X piece, every placement scores the same (heights
    determine score; X placement creates a 3-tall column wherever it lands).
    Tie-break by smaller x → x=0."""
    b = Board.empty()
    placement = choose_placement(b, "X", DEFAULT_WEIGHTS)
    rot, x = placement
    assert rot == 0
    assert x == 0  # smallest x wins on tie


@pytest.mark.parametrize("kind", ["F", "I", "L", "N", "P", "T", "U", "V", "W", "X", "Y", "Z"])
def test_choose_placement_returns_legal_placement_for_each_piece(kind):
    """On an empty board, every kind has at least one legal placement."""
    b = Board.empty()
    placement = choose_placement(b, kind, DEFAULT_WEIGHTS)
    assert placement is not None
    rot, x = placement
    new_b, _ = b.apply_lock(kind, rot, x)
    # Sanity: post-state is valid and contains 5 new cells (no clears on empty board).
    occupied = sum(sum(r) for r in new_b.cells)
    assert occupied == 5
