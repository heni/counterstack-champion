import pytest

from champion import pieces
from champion.pieces import BBOX, CELLS, KINDS, UNIQUE_ROTATIONS, rotated_cell, spawn_x


def test_kinds_count_and_order():
    assert KINDS == ("F", "I", "L", "N", "P", "T", "U", "V", "W", "X", "Y", "Z")
    assert len(KINDS) == 12


def test_every_piece_has_4_rotations_with_5_cells():
    for k in KINDS:
        for r in (0, 1, 2, 3):
            cells = CELLS[(k, r)]
            assert len(cells) == 5, f"{k} rot={r} has {len(cells)} cells"


def test_cells_are_normalized_to_bbox_top_left():
    for (k, r), cells in CELLS.items():
        min_x = min(c[0] for c in cells)
        min_y = min(c[1] for c in cells)
        assert min_x == 0, f"{k} rot={r} not normalized x: min_x={min_x}"
        assert min_y == 0, f"{k} rot={r} not normalized y: min_y={min_y}"


def test_bbox_matches_cells_extent():
    for (k, r), cells in CELLS.items():
        bw, bh = BBOX[(k, r)]
        assert bw == max(c[0] for c in cells) + 1
        assert bh == max(c[1] for c in cells) + 1


def test_unique_rotation_counts_total_41():
    expected = {
        "F": 4, "I": 2, "L": 4, "N": 4, "P": 4, "T": 4,
        "U": 4, "V": 4, "W": 4, "X": 1, "Y": 4, "Z": 2,
    }
    total = 0
    for k in KINDS:
        rots = UNIQUE_ROTATIONS[k]
        assert len(rots) == expected[k], f"{k}: got {len(rots)}, expected {expected[k]}"
        total += len(rots)
    assert total == 41


def test_unique_rotations_yield_distinct_shapes():
    for k in KINDS:
        shapes = {CELLS[(k, r)] for r in UNIQUE_ROTATIONS[k]}
        assert len(shapes) == len(UNIQUE_ROTATIONS[k])


def test_symmetric_rotations_match_canonical():
    """For X, I, Z: the redundant rotations carry the same cells as the canonical."""
    assert CELLS[("X", 0)] == CELLS[("X", 1)] == CELLS[("X", 2)] == CELLS[("X", 3)]
    assert CELLS[("I", 0)] == CELLS[("I", 2)]
    assert CELLS[("I", 1)] == CELLS[("I", 3)]
    assert CELLS[("Z", 0)] == CELLS[("Z", 2)]
    assert CELLS[("Z", 1)] == CELLS[("Z", 3)]


@pytest.mark.parametrize("k", KINDS)
def test_rotation_rule_matches_table(k: str):
    """Verify rot=k+1 cells match (H-1-y, x) + normalize transform of rot=k."""
    for r in (0, 1, 2):
        bw, bh = BBOX[(k, r)]
        rotated = [rotated_cell(x, y, bh) for x, y in CELLS[(k, r)]]
        # Normalize to bbox top-left.
        min_rx = min(c[0] for c in rotated)
        min_ry = min(c[1] for c in rotated)
        normalized = frozenset((rx - min_rx, ry - min_ry) for rx, ry in rotated)
        assert normalized == CELLS[(k, r + 1)], (
            f"{k}: rot {r}→{r + 1} transform mismatch; "
            f"expected {sorted(CELLS[(k, r + 1)])}, got {sorted(normalized)}"
        )


@pytest.mark.parametrize(
    "kind, rot, field_width, expected",
    [
        ("I", 0, 12, 3),  # bbox 5×1 → (12-5)//2 = 3
        ("I", 1, 12, 5),  # bbox 1×5 → (12-1)//2 = 5
        ("X", 0, 12, 4),  # bbox 3×3 → (12-3)//2 = 4
        ("F", 0, 12, 4),  # bbox 3×3 → (12-3)//2 = 4
        ("U", 0, 12, 4),  # bbox 3×2 → (12-3)//2 = 4
    ],
)
def test_spawn_x(kind, rot, field_width, expected):
    assert spawn_x(kind, rot, field_width) == expected


def test_kinds_data_complete():
    """No missing (kind, rot) entries."""
    expected_keys = {(k, r) for k in KINDS for r in (0, 1, 2, 3)}
    assert set(CELLS.keys()) == expected_keys
    assert set(BBOX.keys()) == expected_keys


def test_pieces_module_exports():
    assert hasattr(pieces, "KINDS")
    assert hasattr(pieces, "CELLS")
    assert hasattr(pieces, "BBOX")
    assert hasattr(pieces, "UNIQUE_ROTATIONS")
    assert hasattr(pieces, "spawn_x")
