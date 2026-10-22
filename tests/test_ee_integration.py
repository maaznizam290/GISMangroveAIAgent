"""Earth Engine code paths.

The import test runs everywhere. The `ee` tests need an authenticated session
(EE_PROJECT set and credentials available) and talk to real Earth Engine; they are
deselected by default: run `pytest -m ee`.
"""

import importlib
import os

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "indus_delta.earthengine.util",
        "indus_delta.earthengine.prep",
        "indus_delta.earthengine.composite",
        "indus_delta.earthengine.inventory_ee",
        "indus_delta.earthengine.download",
        "indus_delta.m2",
        "indus_delta.m3_preview",
        "indus_delta.m3_export",
    ],
)
def test_modules_import(module):
    importlib.import_module(module)


needs_ee = pytest.mark.skipif(not os.environ.get("EE_PROJECT"), reason="EE_PROJECT not set")


@pytest.fixture(scope="module")
def ee_session():
    from indus_delta.ee_auth import initialize

    return initialize()


@pytest.mark.ee
@needs_ee
def test_inventory_landsat9_small(ee_session, cfgs, tmp_path):
    """Landsat 9 only (shortest record) over the primary AOI."""
    from indus_delta.m2 import run_inventory

    status, checks, out = run_inventory(cfgs, tmp_path, datasets=["landsat9_l2"])
    import pandas as pd

    inv = pd.read_csv(out / "image_inventory.csv")
    assert len(inv) > 0
    assert inv["valid_fraction"].between(0, 1).all()
    assert set(inv["dataset"]) == {"landsat9_l2"}


@pytest.mark.ee
@needs_ee
def test_preview_runs_and_writes_gate(ee_session, cfgs, tmp_path):
    from indus_delta.m3_preview import run_preview

    status, checks, out = run_preview(cfgs, tmp_path)
    assert (out / "preview_gate.json").is_file()
    assert status in {"PASS", "FAIL"}
