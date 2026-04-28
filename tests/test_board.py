import zlib

import pytest

from champion.board import Board


def _board_from_lines(lines: list[str], width: int = 12) -> Board:
    """Build a board from human-readable strings.

    '.' = empty, '#' = occupied. lines[0] is y=0 (top); lines[-1] is the floor.
    Each line must be exactly `width` chars. Pad to height=20 with empty rows on top.
    """
    height = 20
    rows = [[False] * width for _ in range(height)]
    pad = height - len(lines)
    for i, line in enumerate(lines):
        assert len(line) == width, f"row {i} has {len(line)} chars, expected {width}"
        for x, ch in enumerate(line):
            if ch == "#":
                rows[pad + i][x] = True
            elif ch != ".":
                raise ValueError(f"unknown char {ch!r}")
    cells = tuple(tuple(r) for r in rows)
    return Board(width, height, cells)


def test_empty_board_has_no_height_no_holes():
    b = Board.empty()
    assert b.column_heights() == (0,) * 12
    assert b.holes() == 0
    assert sum(sum(r) for r in b.cells) == 0


def test_apply_lock_i_horizontal_on_empty_board():
    """I-piece (rot=0) horizontal at x=0 on empty 12×20 → bottom row cells [0..4]."""
    b = Board.empty()
    new_b, cleared = b.apply_lock("I", 0, 0)
    assert cleared == 0
    assert new_b.cells[19] == (True, True, True, True, True, False, False, False, False, False, False, False)
    assert new_b.column_heights() == (1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0)
    assert new_b.holes() == 0


def test_apply_lock_two_i_pieces_clears_no_lines_on_partial():
    """Two I-pieces side-by-side cover 10 cells of bottom row (12 wide). No clear yet."""
    b = Board.empty()
    b1, _ = b.apply_lock("I", 0, 0)  # cells (0..4, 19)
    b2, _ = b1.apply_lock("I", 0, 5)  # cells (5..9, 19)
    assert sum(b2.cells[19]) == 10
    assert all(not b2.cells[19][x] for x in (10, 11))


def test_line_clear_full_bottom_row():
    """Construct a board with bottom row full except col 0. Drop a P piece (col 0, rot 0,
    bbox 2×3) → cells include (0, 19) → bottom row fills → 1 line clear."""
    b = _board_from_lines([
        ".###########",  # y=19, last 11 cols full
    ])
    # P rot=0: cells [(0,0),(0,1),(0,2),(1,0),(1,1)]; bbox 2×3.
    # Lands at lowest y where bottom-most P-cells touch the stack:
    # column 0 is empty, column 1 has stack at y=19 → P at x=0 must keep its
    # x=1 cells out of (1, 19). Lowest valid y is 16 (cells span y=16..18 in col 0,
    # y=16..17 in col 1).
    new_b, cleared = b.apply_lock("P", 0, 0)
    # The P fills (0,19) along with rows 16-18 in col 0; bottom row was 11/12 →
    # adding (0,19) closes the bottom row → 1 line clear.
    assert cleared == 1


def test_drop_y_topout_returns_none():
    """Stack reaches y=0 in the spawn columns of an X-piece (cols 4..6) → can't fit."""
    cells = [[False] * 12 for _ in range(20)]
    cells[0][5] = True  # block at (5, 0) — collides with X-piece center
    b = Board(12, 20, tuple(tuple(r) for r in cells))
    # X rot=0: cells [(0,1),(1,0),(1,1),(1,2),(2,1)] — cell (1,0) is at (x+1, 0).
    # If we drop X at x=4: cell (1,0) → (5,0) which is occupied → topout.
    assert b.drop_y("X", 0, 4) is None


def test_drop_y_lands_on_top_of_stack():
    b = _board_from_lines([
        "#...........",  # y=19, only column 0 occupied
    ])
    # I-piece rot=0 at x=0 (covers x=0..4): col 0 has block at y=19,
    # so I at x=0 must land at y=18.
    assert b.drop_y("I", 0, 0) == 18


def test_holes_count_buried_cells():
    b = _board_from_lines([
        "############",  # y=18 — full row above
        "#####.######",  # y=19 — gap at col 5
    ])
    # col 5: occupied at y=18, empty at y=19 → 1 hole.
    assert b.holes() == 1


def test_holes_zero_for_no_overhangs():
    b = _board_from_lines([
        "..####......",
        ".######.....",
        "############",
    ])
    assert b.holes() == 0


def test_column_heights_with_terrain():
    b = _board_from_lines([
        "...#........",  # y=17
        ".###........",  # y=18
        "############",  # y=19
    ])
    heights = b.column_heights()
    # cols 0-2: 1 (only y=19) except col 1: 2 (y=18, y=19); col 2: 2; col 3: 3
    expected = (1, 2, 2, 3, 1, 1, 1, 1, 1, 1, 1, 1)
    assert heights == expected


def test_legal_placements_for_i_on_empty_board_includes_all_x():
    b = Board.empty()
    placements = list(b.legal_placements("I"))
    rots = sorted({rot for rot, _ in placements})
    # I has 2 unique rotations (0 horizontal, 1 vertical).
    assert rots == [0, 1]
    # rot=0 (5×1) → x ∈ 0..7 (8 placements).
    rot0 = sorted(x for rot, x in placements if rot == 0)
    assert rot0 == list(range(8))
    # rot=1 (1×5) → x ∈ 0..11 (12 placements).
    rot1 = sorted(x for rot, x in placements if rot == 1)
    assert rot1 == list(range(12))
    assert len(placements) == 20


def test_legal_placements_for_x_yields_one_rotation():
    b = Board.empty()
    placements = list(b.legal_placements("X"))
    assert {rot for rot, _ in placements} == {0}  # X has only 1 unique rotation
    assert len(placements) == 10  # bbox 3×3 → x ∈ 0..9


def test_crc32_state_empty_board():
    """Known fixed value: CRC32 of '0'*240."""
    expected = f"crc32:{zlib.crc32(b'0' * 240):08x}"
    assert Board.empty().crc32_state() == expected


def test_crc32_state_changes_after_lock():
    b = Board.empty()
    crc1 = b.crc32_state()
    new_b, _ = b.apply_lock("I", 0, 0)
    crc2 = new_b.crc32_state()
    assert crc1 != crc2


def test_with_delta_applies_set_and_clear():
    b = _board_from_lines([
        "###.........",  # y=19
    ])
    delta = [[0, 19, 0], [3, 19, 1], [4, 19, 2]]  # clear (0,19), set (3,19) and (4,19)
    new_b = b.with_delta(delta)
    assert not new_b.cells[19][0]
    assert new_b.cells[19][3]
    assert new_b.cells[19][4]
    assert new_b.cells[19][1]  # untouched
    assert new_b.cells[19][2]  # untouched


def test_apply_lock_does_not_mutate_original():
    b = Board.empty()
    b.apply_lock("I", 0, 0)
    assert b.column_heights() == (0,) * 12  # original unchanged


def test_full_line_clear_drops_blocks_above():
    """Build a stack with a single block at (0, 18) sitting on top of a full row at y=19."""
    b = _board_from_lines([
        "#...........",  # y=18
        "###########.",  # y=19, full except col 11
    ])
    # Drop an I-piece rot=1 (vertical, 1×5) at x=11 → cells (11, 15..19)
    # Bottom row y=19 fills → 1 line clears
    new_b, cleared = b.apply_lock("I", 1, 11)
    assert cleared == 1
    # After clear, the lone block at (0, 18) shifts to (0, 19); the I-piece's bottom
    # vanished with the cleared row, leaving 4 cells in col 11 at y=16..19.
    assert new_b.cells[19][0]
    for y in range(16, 20):
        assert new_b.cells[y][11], f"col 11 y={y} should be set"
    assert sum(new_b.cells[19]) == 2  # block at col 0 + I-piece at col 11
