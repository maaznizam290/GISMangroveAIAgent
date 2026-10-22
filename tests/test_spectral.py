"""Index formulas and masks. All arrays are MOCK DATA."""

import numpy as np
import pytest

from indus_delta.spectral import (
    bits_to_mask_value,
    compute_index,
    index_bounds,
    qa_clear,
    saturation_bits,
    scale_reflectance,
    valid_reflectance,
)


def test_bits_to_mask_value():
    assert bits_to_mask_value([0, 1, 3, 4, 5]) == 0b111011
    with pytest.raises(ValueError):
        bits_to_mask_value([16])


def test_qa_clear_uses_configured_bits(cfgs):
    oli = cfgs.preprocessing.landsat.mask_bits_for("landsat_oli")
    tm = cfgs.preprocessing.landsat.mask_bits_for("landsat_tm_etm")
    assert 2 in oli and 2 not in tm  # cirrus bit only defined for OLI
    qa = np.array([0b1000000, 0b1000, 0b10000, 0b100, 1])  # clear, cloud, shadow, cirrus, fill
    assert qa_clear(qa, oli).tolist() == [True, False, False, False, False]
    assert qa_clear(qa, tm).tolist() == [True, False, False, True, False]


def test_saturation_bits_follow_band_number():
    assert saturation_bits(["SR_B2", "SR_B7"]) == [1, 6]


def test_landsat_c2_scaling(cfgs):
    ds = cfgs.datasets.datasets["landsat8_l2"]
    out = scale_reflectance(np.array([7273, 43636]), ds.reflectance_scale, ds.reflectance_offset)
    assert out == pytest.approx([0.0000075, 0.99999], abs=1e-6)


def test_invalid_reflectance_masked_not_clipped():
    v = valid_reflectance(np.array([-0.01, 0.0, 0.5, 1.0, 1.2, np.nan]), 0.0, 1.0)
    assert v.tolist() == [False, True, True, True, False, False]


def _bands(**kw):
    base = dict(blue=0.05, green=0.08, red=0.06, nir=0.30, swir1=0.15, swir2=0.08)
    base.update(kw)
    return {k: np.array([v], dtype=float) for k, v in base.items()}


def test_index_values(cfgs):
    b = _bands()
    assert compute_index("ndvi", b, cfgs.indices)[0] == pytest.approx((0.30 - 0.06) / 0.36)
    assert compute_index("ndmi", b, cfgs.indices)[0] == pytest.approx(0.15 / 0.45)
    assert compute_index("mndwi", b, cfgs.indices)[0] == pytest.approx(-0.07 / 0.23)
    assert compute_index("mvi", b, cfgs.indices)[0] == pytest.approx(0.22 / 0.07)
    ndwi = (0.08 - 0.30) / 0.38
    assert compute_index("cmri", b, cfgs.indices)[0] == pytest.approx(0.24 / 0.36 - ndwi)


def test_zero_denominator_is_masked(cfgs):
    b = _bands(swir1=0.08)  # SWIR1 == Green -> MVI denominator 0
    assert np.isnan(compute_index("mvi", b, cfgs.indices)[0])
    b = _bands(nir=0.0, red=0.0)
    assert np.isnan(compute_index("ndvi", b, cfgs.indices)[0])


def test_masked_input_propagates(cfgs):
    b = _bands(red=np.nan)
    assert np.isnan(compute_index("ndvi", b, cfgs.indices)[0])
    assert np.isnan(compute_index("cmri", b, cfgs.indices)[0])


def test_index_bounds(cfgs):
    assert index_bounds("ndvi", cfgs.indices) == (-1.0, 1.0)
    assert index_bounds("cmri", cfgs.indices) == (-2.0, 2.0)
    assert index_bounds("mvi", cfgs.indices) is None
