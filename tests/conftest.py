"""Shared fixtures. Synthetic arrays in tests are MOCK DATA for unit tests only."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from indus_delta.config import ProjectConfig, load_configs

REPO = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO / "configs"


@pytest.fixture(scope="session")
def cfgs():
    return load_configs(CONFIG_DIR)


@pytest.fixture(scope="session")
def raw_project() -> dict:
    return yaml.safe_load((CONFIG_DIR / "project.yaml").read_text())


@pytest.fixture
def make_project(raw_project):
    """Build a ProjectConfig from the real file with nested overrides applied."""

    def _make(**overrides) -> ProjectConfig:
        data = copy.deepcopy(raw_project)
        for dotted, value in overrides.items():
            node = data
            *parents, leaf = dotted.split("__")
            for key in parents:
                node = node[key]
            node[leaf] = value
        return ProjectConfig.model_validate(data)

    return _make
