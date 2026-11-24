import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


@pytest.fixture
def case_raw():
    return json.loads((FIXTURES / "synthetic_widget_corp.json").read_text())
