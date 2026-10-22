"""Accuracy statistics on small hand-checkable MOCK confusion matrices."""

import numpy as np
import pytest

from indus_delta.accuracy import class_metrics, confusion, olofsson, overall, wilson

CODES = [1, 2]
NAMES = ["a", "b"]


def test_confusion_orientation():
    cm = confusion(np.array([1, 1, 1, 2]), np.array([1, 2, 1, 2]), CODES)
    assert cm.tolist() == [[2, 1], [0, 1]]  # rows reference, columns map


def test_class_metrics_values():
    cm = np.array([[40, 10], [5, 45]])  # rows reference
    m = class_metrics(cm, CODES, NAMES, 0.95).set_index("class_name")
    assert m.loc["a", "producers_accuracy"] == pytest.approx(40 / 50)
    assert m.loc["a", "users_accuracy"] == pytest.approx(40 / 45)
    assert m.loc["a", "iou"] == pytest.approx(40 / (50 + 45 - 40))
    ua, pa = 40 / 45, 40 / 50
    assert m.loc["a", "f1"] == pytest.approx(2 * ua * pa / (ua + pa))
    assert m.loc["a", "users_accuracy_ci_low"] < ua < m.loc["a", "users_accuracy_ci_high"]


def test_overall_and_kappa():
    cm = np.array([[40, 10], [5, 45]])
    o = overall(cm, 0.95)
    assert o.overall_accuracy == pytest.approx(0.85)
    pe = (45 * 50 + 55 * 50) / 100**2
    assert o.kappa == pytest.approx((0.85 - pe) / (1 - pe))


def test_wilson_bounds():
    lo, hi = wilson(50, 50, 0.95)
    assert hi == 1.0 and 0.9 < lo < 1.0
    assert np.isnan(wilson(0, 0, 0.95)[0])


def test_olofsson_hand_example():
    # Map strata: class a 1000 px, class b 9000 px; 50 validation samples per stratum.
    # In map-a: 45 ref a, 5 ref b. In map-b: 2 ref a, 48 ref b. cm rows = reference.
    cm = np.array([[45, 2], [5, 48]])
    est = olofsson(cm, np.array([1000, 9000]), pixel_area=900.0)
    W = np.array([0.1, 0.9])
    p_aa = W[0] * 45 / 50
    p_ba, p_bb = W[1] * 2 / 50, W[1] * 48 / 50
    assert est["overall_accuracy"] == pytest.approx(p_aa + p_bb)
    assert est["users_accuracy"][0] == pytest.approx(45 / 50)
    assert est["producers_accuracy"][0] == pytest.approx(p_aa / (p_aa + p_ba))
    assert est["area_proportion"][0] == pytest.approx(p_aa + p_ba)
    assert est["area"].sum() == pytest.approx(10000 * 900.0)
    se_oa = np.sqrt(W[0] ** 2 * 0.9 * 0.1 / 49 + W[1] ** 2 * 0.96 * 0.04 / 49)
    assert est["overall_accuracy_se"] == pytest.approx(se_oa)


def test_olofsson_perfect_map_has_zero_error():
    cm = np.array([[30, 0], [0, 30]])
    est = olofsson(cm, np.array([400, 600]), 1.0)
    assert est["overall_accuracy"] == 1.0
    assert np.allclose(est["producers_accuracy_se"], 0)
    assert np.allclose(est["area"], [400, 600])


def test_olofsson_needs_samples_in_every_stratum():
    with pytest.raises(ValueError, match="every map stratum"):
        olofsson(np.array([[5, 0], [3, 0]]), np.array([10, 10]), 1.0)
