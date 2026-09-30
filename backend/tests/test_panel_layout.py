"""Panel space rules (PNL-001, PNL-003, PNL-004, PNL-007)."""

import pytest

from app.panels.layout import Placement, fit_error, grid_position, occupied, overlap


def test_pnl_003_odd_even_double_pole_skips_to_same_side():
    assert occupied(5, 2, "odd_even") == (5, 7)
    assert occupied(2, 3, "odd_even") == (2, 4, 6)


def test_pnl_003_sequential_double_pole_uses_next_space():
    assert occupied(5, 2, "sequential") == (5, 6)
    assert occupied(9, 1, "sequential") == (9,)


@pytest.mark.parametrize(
    ("slot", "numbering", "expected"),
    [
        (1, "odd_even", (0, 0)),
        (2, "odd_even", (0, 1)),
        (7, "odd_even", (3, 0)),
        (1, "sequential", (0, 0)),
        (20, "sequential", (19, 0)),
        (21, "sequential", (0, 1)),
        (40, "sequential", (19, 1)),
    ],
)
def test_pnl_001_grid_position_for_40_space_panel(slot, numbering, expected):
    assert grid_position(slot, 40, numbering) == expected


def test_pnl_003_fit_accepts_breaker_inside_panel():
    assert fit_error(39, 1, 40, "odd_even") is None
    assert fit_error(37, 2, 40, "odd_even") is None


def test_pnl_003_fit_rejects_spaces_past_the_end():
    assert "space 41" in (fit_error(39, 2, 40, "odd_even") or "")
    assert fit_error(0, 1, 40, "odd_even") is not None


def test_pnl_003_fit_rejects_crossing_columns_in_sequential_panel():
    assert "column" in (fit_error(20, 2, 40, "sequential") or "")
    assert fit_error(19, 2, 40, "sequential") is None


def test_pnl_003_fit_rejects_bad_pole_count():
    assert fit_error(1, 4, 40, "odd_even") is not None
    assert fit_error(1, 0, 40, "odd_even") is not None


def test_pnl_001_fit_rejects_unknown_numbering():
    with pytest.raises(ValueError):
        fit_error(1, 1, 40, "zigzag")


def test_pnl_004_same_breaker_on_two_legs_is_allowed():
    others = [Placement("a", 5, 2)]
    assert overlap(others, Placement("b", 5, 2), "odd_even") is None


def test_pnl_004_partial_overlap_is_rejected():
    others = [Placement("a", 5, 2)]
    clash = overlap(others, Placement("b", 7, 1), "odd_even")
    assert clash == Placement("a", 5, 2)


def test_pnl_004_different_pole_count_on_same_start_is_rejected():
    others = [Placement("a", 5, 1)]
    assert overlap(others, Placement("b", 5, 2), "odd_even") is not None


def test_pnl_004_placement_ignores_itself():
    others = [Placement("a", 5, 1)]
    assert overlap(others, Placement("a", 5, 2), "odd_even") is None


def test_pnl_004_neighbours_do_not_overlap():
    others = [Placement("a", 5, 2)]
    assert overlap(others, Placement("b", 6, 1), "odd_even") is None
    assert overlap(others, Placement("b", 9, 1), "odd_even") is None
