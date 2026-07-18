"""
Rectangle packing for the texture atlas.

Implements the MaxRects algorithm with the Best Short Side Fit heuristic.
Sprites are never rotated, as required by the unpacking engine.
"""

from math import ceil, sqrt
from typing import NamedTuple, Optional


MAX_ATLAS_SIZE = 16384
_MAX_ATTEMPTS = 64


class PackError(Exception):
    """Raised when the sprites cannot be packed into the maximum atlas size."""


class Placement(NamedTuple):
    x: int
    y: int
    w: int
    h: int


class _FreeRect(NamedTuple):
    x: int
    y: int
    w: int
    h: int


def _next_pot(value: int) -> int:
    pot = 1
    while pot < value:
        pot *= 2
    return pot


class _MaxRects:
    """A single fixed-size MaxRects bin."""

    def __init__(self, width: int, height: int):
        self.free_rects = [_FreeRect(0, 0, width, height)]

    def insert(self, w: int, h: int) -> Optional[tuple[int, int]]:
        """
        Places a w x h rectangle at the free spot with the best short side fit.
        Returns the (x, y) position, or None if it does not fit anywhere.
        """

        best: Optional[tuple[int, int]] = None
        best_score: Optional[tuple[int, int]] = None

        for rect in self.free_rects:
            if rect.w < w or rect.h < h:
                continue

            leftover_w = rect.w - w
            leftover_h = rect.h - h
            score = (min(leftover_w, leftover_h), max(leftover_w, leftover_h))

            if best_score is None or score < best_score:
                best = (rect.x, rect.y)
                best_score = score

        if best is not None:
            self._split(best[0], best[1], w, h)
        return best

    def _split(self, x: int, y: int, w: int, h: int):
        """
        Splits every free rectangle that overlaps the newly used area into
        up to four smaller free rectangles, then prunes redundant ones.
        """

        right = x + w
        bottom = y + h
        next_free: list[_FreeRect] = []

        for rect in self.free_rects:
            rect_right = rect.x + rect.w
            rect_bottom = rect.y + rect.h

            no_overlap = (
                rect.x >= right
                or rect_right <= x
                or rect.y >= bottom
                or rect_bottom <= y
            )
            if no_overlap:
                next_free.append(rect)
                continue

            if x > rect.x:
                next_free.append(_FreeRect(rect.x, rect.y, x - rect.x, rect.h))
            if right < rect_right:
                next_free.append(_FreeRect(right, rect.y, rect_right - right, rect.h))
            if y > rect.y:
                next_free.append(_FreeRect(rect.x, rect.y, rect.w, y - rect.y))
            if bottom < rect_bottom:
                next_free.append(_FreeRect(rect.x, bottom, rect.w, rect_bottom - bottom))

        self.free_rects = _prune(next_free)


def _prune(rects: list[_FreeRect]) -> list[_FreeRect]:
    """Removes free rectangles fully contained inside another one."""

    result = []

    for i, a in enumerate(rects):
        contained = False

        for j, b in enumerate(rects):
            if i == j:
                continue
            covers = (
                b.x <= a.x
                and b.y <= a.y
                and b.x + b.w >= a.x + a.w
                and b.y + b.h >= a.y + a.h
            )
            # For exact duplicates, only keep the first occurrence
            if covers and (a != b or j < i):
                contained = True
                break

        if not contained:
            result.append(a)

    return result


def _try_pack(
    sizes: list[tuple[str, int, int]], width: int, height: int
) -> Optional[dict[str, tuple[int, int]]]:
    packer = _MaxRects(width, height)
    result = {}

    for key, w, h in sizes:
        position = packer.insert(w, h)
        if position is None:
            return None
        result[key] = position

    return result


def pack_rects(
    sizes: list[tuple[str, int, int]],
    spacing: int = 0,
    power_of_two: bool = False,
    max_size: int = MAX_ATLAS_SIZE,
) -> tuple[dict[str, Placement], int, int]:
    """
    Packs (key, width, height) rectangles into an atlas without rotating them.

    Starts from an area-based size estimate and grows the atlas until
    everything fits. Returns ({key: Placement}, atlas_width, atlas_height).

    @param sizes List of (key, width, height) tuples with unique keys
    @param spacing Minimum distance in pixels between packed rectangles
    @param power_of_two If True, the atlas dimensions are powers of two
    @param max_size Maximum allowed atlas width and height
    """

    if not sizes:
        return {}, 1, 1

    original_sizes = {key: (w, h) for key, w, h in sizes}

    # Sorting by largest side (area as tiebreaker) improves MaxRects results
    order = sorted(sizes, key=lambda s: (max(s[1], s[2]), s[1] * s[2]), reverse=True)
    padded = [(key, w + spacing, h + spacing) for key, w, h in order]

    min_w = max(w for _, w, _ in padded)
    min_h = max(h for _, _, h in padded)
    if max(min_w, min_h) > max_size:
        raise PackError(
            f"A sprite ({min_w}x{min_h}px including spacing) exceeds the "
            f"maximum atlas size of {max_size}px."
        )

    side = ceil(sqrt(sum(w * h for _, w, h in padded)))
    width = min(max(side, min_w), max_size)
    height = min(max(side, min_h), max_size)
    if power_of_two:
        width = _next_pot(width)
        height = _next_pot(height)

    positions = None
    for _ in range(_MAX_ATTEMPTS):
        positions = _try_pack(padded, width, height)
        if positions is not None:
            break

        if width >= max_size and height >= max_size:
            raise PackError(
                f"Could not fit all sprites into the maximum atlas size "
                f"of {max_size}x{max_size}px."
            )

        # Grow the smaller dimension and try again
        if power_of_two:
            if width <= height:
                width *= 2
            else:
                height *= 2
        else:
            if width <= height:
                width = ceil(width * 1.25)
            else:
                height = ceil(height * 1.25)
        width = min(width, max_size)
        height = min(height, max_size)

    if positions is None:
        raise PackError("Could not pack the sprites into an atlas.")

    placements = {
        key: Placement(x, y, *original_sizes[key]) for key, (x, y) in positions.items()
    }

    used_w = max(p.x + p.w for p in placements.values())
    used_h = max(p.y + p.h for p in placements.values())
    if power_of_two:
        used_w = _next_pot(used_w)
        used_h = _next_pot(used_h)

    return placements, used_w, used_h
