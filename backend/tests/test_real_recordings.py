"""Backend logic on genuine recorded SEC responses (tests/recorded/sec). Skipped if recordings are absent."""

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from deepterminal_api.analysis.analogues import first_public, profile_at

REC = Path(__file__).resolve().parents[2] / "tests" / "recorded" / "sec"


def facts(cik: int) -> dict:
    p = REC / f"companyfacts_{cik:010d}.json.gz"
    if not p.exists():
        pytest.skip("no recording")
    return json.loads(gzip.open(p).read())


def test_decision_date_survives_a_revenue_tag_change():
    # NVIDIA switched revenue tags in 2022; FY2020 was public when its 10-K was filed on 2020-02-20.
    d = facts(1045810)
    assert first_public(d, date(2020, 1, 26)) == date(2020, 2, 20)
    assert first_public(d, date(2021, 1, 31)) == date(2021, 2, 26)


def test_capex_tagged_with_a_custom_concept_is_missing_not_zero():
    # In the FY2022 10-K NVIDIA reported capex under a company-specific tag; it is unknown as of that date.
    prof = profile_at(facts(1045810), date(2022, 1, 30), date(2022, 3, 18))
    assert prof["capex_pct"] is None and prof["op_margin"] > 0.3
