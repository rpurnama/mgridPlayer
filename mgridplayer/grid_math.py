"""Pure grid-layout helpers (no Qt) so they are easy to test."""

from __future__ import annotations

import math

PRESETS = ((1, 1), (1, 2), (2, 1), (2, 2), (2, 3), (3, 2), (3, 3), (3, 4), (4, 4), (5, 5), (6, 6))
MAX_DIM = 8


def auto_dims(n: int, aspect: float = 16 / 9) -> tuple[int, int]:
    """Rows/cols that fit ``n`` tiles, preferring wide layouts on wide windows."""
    n = max(1, int(n))
    best = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        if rows > MAX_DIM or cols > MAX_DIM:
            continue
        empty = rows * cols - n
        # Tile shape closest to 16:9 video, then fewest empty cells.
        tile_aspect = (aspect * rows) / cols
        score = (round(abs(math.log(tile_aspect / (16 / 9))) + empty * 0.35, 6), empty, rows)
        if best is None or score < best[0]:
            best = (score, (rows, cols))
    return best[1] if best else (MAX_DIM, MAX_DIM)


def grow_to_fit(rows: int, cols: int, needed: int) -> tuple[int, int]:
    """Smallest grid at least as big as (rows, cols) holding ``needed`` tiles."""
    while rows * cols < needed and (rows < MAX_DIM or cols < MAX_DIM):
        if cols <= rows and cols < MAX_DIM:
            cols += 1
        elif rows < MAX_DIM:
            rows += 1
        else:
            cols += 1
    return rows, cols


def compact_order(loaded: list[bool], capacity: int) -> list[int]:
    """Indices of tiles to keep when shrinking to ``capacity`` (loaded tiles win), in original order."""
    idx = list(range(len(loaded)))
    ordered = [i for i in idx if loaded[i]] + [i for i in idx if not loaded[i]]
    return sorted(ordered[:capacity])


def position(index: int, cols: int) -> tuple[int, int]:
    return divmod(index, cols)
