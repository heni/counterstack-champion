"""Local well state — mirror of the server's authoritative board.

Coordinates: (0, 0) is the top-left of the well, x grows right (0..W-1),
y grows DOWN (0..H-1). Bottom row is y=H-1.
"""

from __future__ import annotations

import zlib
from typing import Iterator

from .pieces import BBOX, CELLS, UNIQUE_ROTATIONS

DEFAULT_WIDTH = 12
DEFAULT_HEIGHT = 20

_Cells = tuple[tuple[bool, ...], ...]


class Board:
    """Immutable well state. Mutating operations return a new Board."""

    __slots__ = ("width", "height", "cells")

    def __init__(self, width: int, height: int, cells: _Cells | None = None):
        self.width = width
        self.height = height
        if cells is None:
            cells = tuple(tuple(False for _ in range(width)) for _ in range(height))
        else:
            assert len(cells) == height
            assert all(len(row) == width for row in cells)
        self.cells = cells

    @classmethod
    def empty(cls, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT) -> "Board":
        return cls(width, height)

    def is_occupied(self, x: int, y: int) -> bool:
        return self.cells[y][x]

    def fits(self, kind: str, rot: int, x: int, y: int) -> bool:
        for dx, dy in CELLS[(kind, rot)]:
            cx, cy = x + dx, y + dy
            if cx < 0 or cx >= self.width:
                return False
            if cy < 0 or cy >= self.height:
                return False
            if self.cells[cy][cx]:
                return False
        return True

    def drop_y(self, kind: str, rot: int, x: int) -> int | None:
        """Largest y where piece anchored at (x, y) fits without collision.

        None if piece doesn't fit at y=0 (would top out at spawn).
        """
        bbox_w, bbox_h = BBOX[(kind, rot)]
        if x < 0 or x + bbox_w > self.width:
            return None
        if not self.fits(kind, rot, x, 0):
            return None
        y = 0
        max_y = self.height - bbox_h
        while y < max_y and self.fits(kind, rot, x, y + 1):
            y += 1
        return y

    def apply_lock(self, kind: str, rot: int, x: int) -> tuple["Board", int]:
        """Drop piece into column x at rot, lock, clear full rows.

        Returns (new_board, cleared_rows). Raises ValueError if placement
        would top out at spawn.
        """
        y = self.drop_y(kind, rot, x)
        if y is None:
            raise ValueError(
                f"placement {kind}/rot={rot}/x={x} would top out on this board"
            )
        new_rows = [list(row) for row in self.cells]
        for dx, dy in CELLS[(kind, rot)]:
            new_rows[y + dy][x + dx] = True
        full_indices = [yy for yy in range(self.height) if all(new_rows[yy])]
        cleared = len(full_indices)
        if cleared:
            full_set = set(full_indices)
            kept = [new_rows[yy] for yy in range(self.height) if yy not in full_set]
            empty = [[False] * self.width for _ in range(cleared)]
            new_rows = empty + kept
        cells = tuple(tuple(r) for r in new_rows)
        return Board(self.width, self.height, cells), cleared

    def column_heights(self) -> tuple[int, ...]:
        """For each column: number of rows from the highest occupied cell to the floor.

        Empty column → 0. Cell at y=H-1 only → 1. Full column → H.
        """
        heights = []
        for x in range(self.width):
            h = 0
            for y in range(self.height):
                if self.cells[y][x]:
                    h = self.height - y
                    break
            heights.append(h)
        return tuple(heights)

    def holes(self) -> int:
        """Empty cells with at least one occupied cell above in the same column."""
        count = 0
        for x in range(self.width):
            seen_block = False
            for y in range(self.height):
                if self.cells[y][x]:
                    seen_block = True
                elif seen_block:
                    count += 1
        return count

    def legal_placements(self, kind: str) -> Iterator[tuple[int, int]]:
        """Yield (rot, x) for every placement that doesn't top out at spawn.

        Iterates UNIQUE_ROTATIONS[kind] only — symmetric duplicates skipped.
        """
        for rot in UNIQUE_ROTATIONS[kind]:
            bbox_w, _ = BBOX[(kind, rot)]
            for x in range(self.width - bbox_w + 1):
                if self.drop_y(kind, rot, x) is not None:
                    yield (rot, x)

    def crc32_state(self) -> str:
        """SPEC §11.3.4: 'crc32:' + 8-hex of zlib CRC-32 over the row-major bitstring."""
        flat = bytearray(self.width * self.height)
        idx = 0
        for y in range(self.height):
            row = self.cells[y]
            for x in range(self.width):
                flat[idx] = 0x31 if row[x] else 0x30
                idx += 1
        return f"crc32:{zlib.crc32(bytes(flat)):08x}"

    def with_delta(self, delta: list[list[int]]) -> "Board":
        """Apply tick.p.own_board_delta — list of [x, y, v] where v=0 means empty."""
        new_rows = [list(row) for row in self.cells]
        for entry in delta:
            x, y, v = entry[0], entry[1], entry[2]
            new_rows[y][x] = bool(v)
        cells = tuple(tuple(r) for r in new_rows)
        return Board(self.width, self.height, cells)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Board):
            return NotImplemented
        return (
            self.width == other.width
            and self.height == other.height
            and self.cells == other.cells
        )

    def __hash__(self) -> int:
        return hash((self.width, self.height, self.cells))

    def __repr__(self) -> str:
        return f"Board({self.width}x{self.height}, occupied={sum(sum(r) for r in self.cells)})"
