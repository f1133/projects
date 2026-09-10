import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from gearbox import config  # noqa: E402


@pytest.fixture(scope="session")
def design():
    """The design as committed, so the tests fail if the TOML stops loading."""
    return config.load(ROOT / "config" / "gearbox.toml")


@pytest.fixture(scope="session")
def geom(design):
    return design.geometry
