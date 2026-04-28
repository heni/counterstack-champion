"""Pentomino data per http://counter-stack.rutsh.com/rotations.html (v0.5)."""

from __future__ import annotations

KINDS: tuple[str, ...] = ("F", "I", "L", "N", "P", "T", "U", "V", "W", "X", "Y", "Z")

# Cells per (kind, rot) as frozensets of (dx, dy) offsets from the bbox top-left.
# Source: appendix table; symmetric rotations carry the same shape as their
# canonical counterpart but a distinct rot integer (per SPEC §4).
CELLS: dict[tuple[str, int], frozenset[tuple[int, int]]] = {
    ("F", 0): frozenset({(0, 1), (1, 0), (1, 1), (1, 2), (2, 0)}),
    ("F", 1): frozenset({(0, 1), (1, 0), (1, 1), (2, 1), (2, 2)}),
    ("F", 2): frozenset({(0, 2), (1, 0), (1, 1), (1, 2), (2, 1)}),
    ("F", 3): frozenset({(0, 0), (0, 1), (1, 1), (1, 2), (2, 1)}),
    ("I", 0): frozenset({(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)}),
    ("I", 1): frozenset({(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)}),
    ("I", 2): frozenset({(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)}),
    ("I", 3): frozenset({(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)}),
    ("L", 0): frozenset({(0, 0), (0, 1), (0, 2), (0, 3), (1, 3)}),
    ("L", 1): frozenset({(0, 0), (0, 1), (1, 0), (2, 0), (3, 0)}),
    ("L", 2): frozenset({(0, 0), (1, 0), (1, 1), (1, 2), (1, 3)}),
    ("L", 3): frozenset({(0, 1), (1, 1), (2, 1), (3, 0), (3, 1)}),
    ("N", 0): frozenset({(0, 2), (0, 3), (1, 0), (1, 1), (1, 2)}),
    ("N", 1): frozenset({(0, 0), (1, 0), (1, 1), (2, 1), (3, 1)}),
    ("N", 2): frozenset({(0, 1), (0, 2), (0, 3), (1, 0), (1, 1)}),
    ("N", 3): frozenset({(0, 0), (1, 0), (2, 0), (2, 1), (3, 1)}),
    ("P", 0): frozenset({(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)}),
    ("P", 1): frozenset({(0, 0), (1, 0), (1, 1), (2, 0), (2, 1)}),
    ("P", 2): frozenset({(0, 1), (0, 2), (1, 0), (1, 1), (1, 2)}),
    ("P", 3): frozenset({(0, 0), (0, 1), (1, 0), (1, 1), (2, 1)}),
    ("T", 0): frozenset({(0, 0), (1, 0), (1, 1), (1, 2), (2, 0)}),
    ("T", 1): frozenset({(0, 1), (1, 1), (2, 0), (2, 1), (2, 2)}),
    ("T", 2): frozenset({(0, 2), (1, 0), (1, 1), (1, 2), (2, 2)}),
    ("T", 3): frozenset({(0, 0), (0, 1), (0, 2), (1, 1), (2, 1)}),
    ("U", 0): frozenset({(0, 0), (0, 1), (1, 1), (2, 0), (2, 1)}),
    ("U", 1): frozenset({(0, 0), (0, 1), (0, 2), (1, 0), (1, 2)}),
    ("U", 2): frozenset({(0, 0), (0, 1), (1, 0), (2, 0), (2, 1)}),
    ("U", 3): frozenset({(0, 0), (0, 2), (1, 0), (1, 1), (1, 2)}),
    ("V", 0): frozenset({(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)}),
    ("V", 1): frozenset({(0, 0), (0, 1), (0, 2), (1, 0), (2, 0)}),
    ("V", 2): frozenset({(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)}),
    ("V", 3): frozenset({(0, 2), (1, 2), (2, 0), (2, 1), (2, 2)}),
    ("W", 0): frozenset({(0, 0), (0, 1), (1, 1), (1, 2), (2, 2)}),
    ("W", 1): frozenset({(0, 1), (0, 2), (1, 0), (1, 1), (2, 0)}),
    ("W", 2): frozenset({(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)}),
    ("W", 3): frozenset({(0, 2), (1, 1), (1, 2), (2, 0), (2, 1)}),
    ("X", 0): frozenset({(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)}),
    ("X", 1): frozenset({(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)}),
    ("X", 2): frozenset({(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)}),
    ("X", 3): frozenset({(0, 1), (1, 0), (1, 1), (1, 2), (2, 1)}),
    ("Y", 0): frozenset({(0, 1), (1, 0), (1, 1), (1, 2), (1, 3)}),
    ("Y", 1): frozenset({(0, 1), (1, 1), (2, 0), (2, 1), (3, 1)}),
    ("Y", 2): frozenset({(0, 0), (0, 1), (0, 2), (0, 3), (1, 2)}),
    ("Y", 3): frozenset({(0, 0), (1, 0), (1, 1), (2, 0), (3, 0)}),
    ("Z", 0): frozenset({(0, 0), (1, 0), (1, 1), (1, 2), (2, 2)}),
    ("Z", 1): frozenset({(0, 1), (0, 2), (1, 1), (2, 0), (2, 1)}),
    ("Z", 2): frozenset({(0, 0), (1, 0), (1, 1), (1, 2), (2, 2)}),
    ("Z", 3): frozenset({(0, 1), (0, 2), (1, 1), (2, 0), (2, 1)}),
}

# Bounding box (width, height) per (kind, rot).
BBOX: dict[tuple[str, int], tuple[int, int]] = {
    key: (max(c[0] for c in cells) + 1, max(c[1] for c in cells) + 1)
    for key, cells in CELLS.items()
}

# Canonical rot values per kind: smallest rot that yields each visually distinct shape.
# X: 1 shape. I, Z: 2 shapes (rot 2/3 duplicate 0/1). Others: 4 distinct.
UNIQUE_ROTATIONS: dict[str, tuple[int, ...]] = {}
for _kind in KINDS:
    seen: dict[frozenset[tuple[int, int]], int] = {}
    rots = []
    for _r in (0, 1, 2, 3):
        shape = CELLS[(_kind, _r)]
        if shape not in seen:
            seen[shape] = _r
            rots.append(_r)
    UNIQUE_ROTATIONS[_kind] = tuple(rots)


def spawn_x(kind: str, rot: int, field_width: int) -> int:
    """X position of bbox top-left at spawn — bbox centered on the field (SPEC §3)."""
    bbox_w, _ = BBOX[(kind, rot)]
    return (field_width - bbox_w) // 2


def rotated_cell(x: int, y: int, height: int) -> tuple[int, int]:
    """Apply one CW rotation step to a cell within a bbox of height H.

    From rotations.html: (x', y') = (H - 1 - y, x). Caller normalizes the result.
    """
    return (height - 1 - y, x)
