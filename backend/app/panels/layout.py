"""Panel space rules (PNL-001, PNL-003, PNL-004). Pure functions, no database."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

NUMBERINGS = ("odd_even", "sequential")
MAX_POLES = 3
MIN_SPACES = 2
MAX_SPACES = 84


@dataclass(frozen=True)
class Placement:
    """One channel's breaker: which channel, its starting space and pole count."""

    key: str
    slot: int
    poles: int


def _check_numbering(numbering: str) -> None:
    if numbering not in NUMBERINGS:
        raise ValueError(f"unknown panel numbering {numbering!r}")


def occupied(slot: int, poles: int, numbering: str) -> tuple[int, ...]:
    """Spaces a breaker takes. Odd/even panels step by two to stay on the same side."""
    _check_numbering(numbering)
    step = 2 if numbering == "odd_even" else 1
    return tuple(slot + step * i for i in range(poles))


def grid_position(slot: int, spaces: int, numbering: str) -> tuple[int, int]:
    """Zero-based (row, column) of a space; column 0 is the left side."""
    _check_numbering(numbering)
    if numbering == "odd_even":
        return (slot - 1) // 2, (slot - 1) % 2
    half = spaces // 2
    return (slot - 1) % half, (slot - 1) // half


def fit_error(slot: int, poles: int, spaces: int, numbering: str) -> str | None:
    """Why a breaker cannot sit at ``slot``, or None when it fits (PNL-003)."""
    if not 1 <= poles <= MAX_POLES:
        return f"a breaker has 1 to {MAX_POLES} poles"
    taken = occupied(slot, poles, numbering)
    for space in taken:
        if not 1 <= space <= spaces:
            return f"space {space} is outside this {spaces}-space panel"
    columns = {grid_position(space, spaces, numbering)[1] for space in taken}
    if len(columns) > 1:
        return "a multi-pole breaker must stay in one column"
    return None


def overlap(others: Iterable[Placement], candidate: Placement, numbering: str) -> Placement | None:
    """First placement that clashes with ``candidate`` (PNL-004).

    Sharing spaces is fine only for the same breaker, such as one CT on each leg of a
    double-pole breaker.
    """
    wanted = set(occupied(candidate.slot, candidate.poles, numbering))
    for other in others:
        if other.key == candidate.key:
            continue
        if (other.slot, other.poles) == (candidate.slot, candidate.poles):
            continue
        if wanted & set(occupied(other.slot, other.poles, numbering)):
            return other
    return None
