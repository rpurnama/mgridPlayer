import pytest

from mgridplayer.grid_math import MAX_DIM, auto_dims, compact_order, grow_to_fit


@pytest.mark.parametrize("n", range(1, 40))
def test_auto_dims_fits(n):
    r, c = auto_dims(n)
    assert r * c >= min(n, MAX_DIM * MAX_DIM)
    assert r <= MAX_DIM and c <= MAX_DIM


@pytest.mark.parametrize("n,expected", [(1, (1, 1)), (2, (1, 2)), (4, (2, 2)), (9, (3, 3))])
def test_auto_dims_common(n, expected):
    assert auto_dims(n) == expected


def test_auto_dims_no_wasted_row():
    for n in range(1, 30):
        r, c = auto_dims(n)
        assert (r - 1) * c < n, "a whole empty row would be wasteful"


def test_grow_to_fit():
    assert grow_to_fit(1, 1, 1) == (1, 1)
    assert grow_to_fit(1, 1, 2) == (1, 2)
    assert grow_to_fit(1, 1, 4) == (2, 2)
    assert grow_to_fit(2, 2, 6) == (2, 3)
    r, c = grow_to_fit(1, 1, 100)
    assert r == MAX_DIM and c == MAX_DIM


def test_compact_order_prefers_loaded():
    loaded = [False, True, False, True, True]
    assert compact_order(loaded, 3) == [1, 3, 4]
    assert compact_order(loaded, 4) == [0, 1, 3, 4]
    assert compact_order([False] * 4, 2) == [0, 1]
