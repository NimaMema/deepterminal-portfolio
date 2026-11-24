import json
from datetime import date

import pytest

from conftest import FIXTURES
from deepterminal.data.sec_edgar import SECClient, annual_series, build_periods, detect_revisions

FACTS = json.loads((FIXTURES / "sec_companyfacts_synthetic.json").read_text())


def test_original_vs_latest_and_quarterlies_excluded():
    orig = annual_series(FACTS, "revenue", revision="original")
    late = annual_series(FACTS, "revenue", revision="latest")
    assert orig[date(2022, 12, 31)].value == 1000e6
    assert late[date(2022, 12, 31)].value == 980e6
    assert set(late) == {date(2022, 12, 31), date(2023, 12, 31)}   # 10-Q quarter excluded


def test_point_in_time_hides_later_filings():
    periods = build_periods(FACTS, as_of=date(2023, 6, 30))
    assert [p.fiscal_year for p in periods] == [2022]
    assert periods[0].revenue == pytest.approx(1000)          # restatement not yet public
    assert periods[0].filed == date(2023, 2, 10)
    assert detect_revisions(FACTS, as_of=date(2023, 6, 30)) == []


def test_revision_detection_and_latest_build():
    revs = detect_revisions(FACTS)
    assert [(r.field, r.original, r.revised) for r in revs] == [("revenue", 1000e6, 980e6)]
    periods = build_periods(FACTS)
    assert [p.revenue for p in periods] == pytest.approx([980, 1200])
    assert periods[1].diluted_shares == pytest.approx(51)
    assert "accession" in periods[1].source_ref


def test_client_requires_contact_user_agent(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPTERMINAL_SEC_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError):
        SECClient(cache_dir=tmp_path)
