import pytest
from rasterio.transform import Affine

from indus_delta.grid import aligned_bounds, aligned_box, grid_offset, is_aligned, transform_list


def test_grid_offset_from_native_transform():
    assert grid_offset([30, 0, 357885, 0, -30, 2700015], 30) == (15, 15)
    with pytest.raises(ValueError):
        grid_offset([10, 0, 0, 0, -10, 0], 30)


def test_aligned_box_covers_and_aligns():
    tf, w, h = aligned_box(342606.68, 2671064.28, 1500, 30, (15, 15))
    assert is_aligned(tf, 30, (15, 15))
    assert tf.c <= 342606.68 - 1500 and tf.c + w * 30 >= 342606.68 + 1500
    assert tf.f >= 2671064.28 + 1500 and tf.f - h * 30 <= 2671064.28 - 1500
    assert (w, h) in {(100, 100), (101, 101), (100, 101), (101, 100)}


def test_aligned_bounds_exact_multiple():
    tf, w, h = aligned_bounds((0, 0, 300, 600), 30)
    assert (tf.c, tf.f, w, h) == (0, 600, 10, 20)


def test_is_aligned_detects_shift():
    assert not is_aligned(Affine(30, 0, 7, 0, -30, 0), 30, (0, 0))
    assert not is_aligned(Affine(10, 0, 0, 0, -10, 0), 30, (0, 0))


def test_transform_list_is_row_major():
    assert transform_list(Affine(30, 0, 100, 0, -30, 200)) == [30, 0, 100, 0, -30, 200]
