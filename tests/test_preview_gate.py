"""Preview checks, gate and gated export planning. Rasters are MOCK DATA written to tmp."""

import json
from datetime import date

import numpy as np
import pytest
import rasterio

from indus_delta.gate import GateError, require_preview_pass, write_gate
from indus_delta.grid import aligned_box
from indus_delta.m3_export import check_preconditions, plan_exports
from indus_delta.preview_checks import PreviewExpectation, check_preview
from indus_delta.spectral import compute_index

ROLES = ["blue", "green", "red", "nir", "swir1", "swir2"]


def _optical_names(cfgs):
    return [*ROLES, *cfgs.indices.indices, "valid_obs"]


def _write(path, arrays, names, tf, nodata):
    h, w = arrays[0].shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=w,
        height=h,
        count=len(arrays),
        dtype="float32",
        crs="EPSG:32642",
        transform=tf,
        nodata=nodata,
    ) as dst:
        for i, (a, n) in enumerate(zip(arrays, names, strict=True), start=1):
            dst.write(a.astype("float32"), i)
            dst.set_band_description(i, n)


def _mock_optical(tmp_path, cfgs, corrupt=None):
    rng = np.random.default_rng(0)
    tf, w, h = aligned_box(342606.68, 2671064.28, 300, 30, (15, 15))
    base = dict(blue=0.05, green=0.08, red=0.06, nir=0.30, swir1=0.15, swir2=0.08)
    bands = {
        r: (v + rng.uniform(-0.01, 0.01, (h, w))).astype("float32").astype(float)
        for r, v in base.items()
    }
    idx = {n: compute_index(n, bands, cfgs.indices) for n in cfgs.indices.indices}
    obs = np.full((h, w), 5.0)
    if corrupt == "index":
        idx["ndvi"] = idx["ndvi"] + 0.05
    if corrupt == "reflectance":
        bands["red"][0, 0] = 1.7
    names = _optical_names(cfgs)
    arrays = [bands[r] for r in ROLES] + [idx[n] for n in cfgs.indices.indices] + [obs]
    path = tmp_path / "mock_landsat.tif"
    _write(path, arrays, names, tf, cfgs.preprocessing.composites.nodata_value)
    exp = PreviewExpectation("landsat", "optical", 32642, 30, tf, w, h, names, (15, 15))
    return path, exp


def _statuses(checks):
    return {c.name: c.status for c in checks}


def test_consistent_preview_passes(tmp_path, cfgs):
    path, exp = _mock_optical(tmp_path, cfgs)
    s = _statuses(check_preview(path, exp, cfgs))
    assert set(s.values()) == {"PASS"}, s
    assert "landsat_index_cmri_recomputed" in s


def test_wrong_index_fails(tmp_path, cfgs):
    path, exp = _mock_optical(tmp_path, cfgs, corrupt="index")
    s = _statuses(check_preview(path, exp, cfgs))
    assert s["landsat_index_ndvi_recomputed"] == "FAIL"
    assert s["landsat_index_ndmi_recomputed"] == "PASS"


def test_out_of_range_reflectance_fails(tmp_path, cfgs):
    path, exp = _mock_optical(tmp_path, cfgs, corrupt="reflectance")
    assert _statuses(check_preview(path, exp, cfgs))["landsat_reflectance_range"] == "FAIL"


def test_grid_mismatch_fails(tmp_path, cfgs):
    path, exp = _mock_optical(tmp_path, cfgs)
    shifted = PreviewExpectation(
        exp.label,
        exp.kind,
        exp.epsg,
        exp.scale,
        exp.transform @ rasterio.Affine.translation(1, 0),
        exp.width,
        exp.height,
        exp.band_names,
        (0, 0),
    )
    s = _statuses(check_preview(path, shifted, cfgs))
    assert s["landsat_grid_matches_request"] == "FAIL"
    assert s["landsat_grid_aligned_to_native"] == "FAIL"


def test_low_valid_fraction_fails(tmp_path, cfgs):
    path, exp = _mock_optical(tmp_path, cfgs)
    with rasterio.open(path, "r+") as dst:
        a = dst.read(4)
        a[: a.shape[0] // 2] = cfgs.preprocessing.composites.nodata_value
        dst.write(a, 4)
    assert _statuses(check_preview(path, exp, cfgs))["landsat_valid_fraction"] == "FAIL"


def test_sar_db_range(tmp_path, cfgs):
    tf, w, h = aligned_box(342606.68, 2671064.28, 100, 10)
    vv, vh, obs = np.full((h, w), -12.0), np.full((h, w), -19.0), np.full((h, w), 30.0)
    vh[0, 0] = 35.0  # linear-scale-looking value: must be caught
    path = tmp_path / "mock_s1.tif"
    names = ["VV", "VH", "valid_obs"]
    _write(path, [vv, vh, obs], names, tf, cfgs.preprocessing.composites.nodata_value)
    exp = PreviewExpectation("sentinel1", "sar", 32642, 10, tf, w, h, names, (0, 0))
    s = _statuses(check_preview(path, exp, cfgs))
    assert s["sentinel1_VV_db_range"] == "PASS" and s["sentinel1_VH_db_range"] == "FAIL"


def test_gate_round_trip(tmp_path, cfgs):
    from indus_delta.checks import Check

    write_gate(tmp_path, cfgs, [Check("a", "PASS", ""), Check("b", "WARN", "")], {})
    assert require_preview_pass(cfgs, tmp_path)["status"] == "PASS"
    write_gate(tmp_path, cfgs, [Check("a", "FAIL", "")], {})
    with pytest.raises(GateError, match="FAIL"):
        require_preview_pass(cfgs, tmp_path)


def test_gate_bound_to_configuration(tmp_path, cfgs):
    from indus_delta.checks import Check

    path = write_gate(tmp_path, cfgs, [Check("a", "PASS", "")], {})
    data = json.loads(path.read_text())
    data["config_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(GateError, match="configuration changed"):
        require_preview_pass(cfgs, tmp_path)


def test_missing_gate(tmp_path, cfgs):
    with pytest.raises(GateError, match="no preview gate"):
        require_preview_pass(cfgs, tmp_path)


def test_full_processing_refused_until_aoi_confirmed(tmp_path, cfgs):
    with pytest.raises(GateError, match="operator_confirmed"):
        check_preconditions(cfgs, tmp_path)


def _fake_gate():
    products = {
        s: {"grid_offset": [15, 15] if s == "landsat" else [0, 0]}
        for s in ("landsat", "sentinel2", "sentinel1")
    }
    return {"status": "PASS", "metadata": {"products": products}}


def test_plan_exports(cfgs):
    plan = plan_exports(cfgs, _fake_gate(), ["landsat", "sentinel2"], date(2026, 10, 22))
    land = [p for p in plan if p["series"] == "landsat"]
    assert len(land) == 44
    assert sum(p["completeness"] == "partial" for p in land) == 1
    assert land[-1]["description"] == "landsat_post_monsoon_2026_partial"
    tf = land[0]["crs_transform"]
    assert (tf[2] - 15) % 30 == 0 and (tf[5] - 15) % 30 == 0
    s2 = [p for p in plan if p["series"] == "sentinel2"]
    assert len(s2) == 14 and s2[0]["crs_transform"][0] == 10


def test_plan_requires_product_in_gate(cfgs):
    gate = _fake_gate()
    del gate["metadata"]["products"]["sentinel1"]
    with pytest.raises(GateError, match="sentinel1"):
        plan_exports(cfgs, gate, ["sentinel1"], date(2026, 10, 22))


@pytest.mark.parametrize(
    ("bucket", "folder", "ok"),
    [
        ("mangroove-exports", None, True),
        (None, "indus_delta_exports", True),
        ("https://drive.google.com/drive/folders/10Xys?usp=sharing", None, False),
        ("gs://mangroove-exports", None, False),
        (None, "https://drive.google.com/drive/folders/10Xys", False),
        (None, None, False),
    ],
)
def test_export_destination_validation(monkeypatch, bucket, folder, ok):
    from indus_delta.m3_export import export_destination

    for name, value in (("EXPORT_BUCKET", bucket), ("EXPORT_DRIVE_FOLDER", folder)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    if ok:
        assert export_destination() == (bucket, folder)
    else:
        with pytest.raises(GateError):
            export_destination()
