import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir():
    return FIXTURES_DIR


def load_fixture(name: str) -> str:
    """Load an HTML fixture file by parser name."""
    path = FIXTURES_DIR / f"{name}.html"
    return path.read_text()
