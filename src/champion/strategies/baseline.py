"""Dellacherie-style 2-feature scorer; see docs/strategy.md."""

from __future__ import annotations

from dataclasses import dataclass

from ..board import Board


@dataclass(frozen=True)
class Weights:
    w_h: float = 1.0
    w_holes: float = 2.0


DEFAULT_WEIGHTS = Weights()


def score(board: Board, weights: Weights = DEFAULT_WEIGHTS) -> float:
    """Lower is better. Sum-of-heights plus heavily-weighted hole count."""
    return weights.w_h * sum(board.column_heights()) + weights.w_holes * board.holes()


def choose_placement(
    board: Board, kind: str, weights: Weights = DEFAULT_WEIGHTS
) -> tuple[int, int] | None:
    """Pick the (rot, x) placement that minimizes score after apply_lock.

    Tie-break: smaller x first, then smaller rot. None if no legal placement
    (every drop tops out — the agent cannot save this match).
    """
    best: tuple[float, int, int] | None = None
    for rot, x in board.legal_placements(kind):
        new_board, _cleared = board.apply_lock(kind, rot, x)
        s = score(new_board, weights)
        key = (s, x, rot)
        if best is None or key < best:
            best = key
    if best is None:
        return None
    _, x, rot = best
    return (rot, x)
