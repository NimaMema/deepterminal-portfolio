import copy
import re

import pytest

from deepterminal.data.case_file import parse_case
from deepterminal.evidence import LookAheadError
from deepterminal.pipeline import run_case
from deepterminal.reporting.dashboard import render_dashboard
from deepterminal.reporting.report import SECTIONS, render_report
from deepterminal.valuation.expectations import Verdict


def run(raw, price=None, **meta):
    raw = copy.deepcopy(raw)
    if price is not None:
        raw["market"]["share_price"]["value"] = price
    raw["meta"].update(meta)
    return run_case(parse_case(raw))


def test_fixture_pipeline_is_consistent(case_raw):
    a = run(case_raw)
    # market EV reproduced by the implied-growth model
    sol = a.reverse[0].solutions[0]
    assert sol.model.enterprise_value == pytest.approx(a.market.enterprise_value, rel=1e-7)
    # base scenario equals the base DCF
    assert a.scenarios.by_name("base").per_share == pytest.approx(a.base_bridge.value_per_share)
    assert a.citations.findings      # synthetic data is always flagged


@pytest.mark.parametrize("price,verdict", [(94.0, Verdict.POTENTIALLY_OVERVALUED),
                                           (72.0, Verdict.APPROXIMATELY_FAIR),
                                           (45.0, Verdict.POTENTIALLY_UNDERVALUED)])
def test_verdicts(case_raw, price, verdict):
    a = run(case_raw, price)
    assert a.assessment.verdict is verdict
    assert "under specified assumptions" in a.assessment.verdict.value


def test_low_quality_or_stale_price_is_too_uncertain(case_raw):
    raw = copy.deepcopy(case_raw)
    raw["evidence_quality"] = "low"
    assert run(raw).assessment.verdict is Verdict.TOO_UNCERTAIN
    stale = run(case_raw, analysis_date="2026-12-31")
    assert stale.assessment.verdict is Verdict.TOO_UNCERTAIN


def test_research_steps_not_invented(case_raw):
    steps = {s.number: s for s in run(case_raw).assessment.steps}
    for n in (9, 10, 11, 12):
        assert not steps[n].performed and "not performed" in steps[n].detail


def test_look_ahead_rejected(case_raw):
    with pytest.raises(LookAheadError):
        run(case_raw, analysis_date="2026-01-01")


def test_report_has_all_24_sections_and_disclaimers(case_raw):
    md = render_report(run(case_raw))
    heads = re.findall(r"^## (\d+)\. (.+)$", md, flags=re.M)
    assert [int(n) for n, _ in heads] == list(range(1, 25))
    assert [t for _, t in heads] == list(SECTIONS)
    assert "SYNTHETIC DATA" in md and "not investment advice" in md
    for q in ("Is this a good business?", "defensible range of economic value",
              "expectations are embedded", "market be overlooking", "invalidate the thesis"):
        assert q in md
    assert not re.search(r"\bnan\b", md.lower())


def test_dashboard_has_eight_panels(case_raw):
    page = render_dashboard(run(case_raw))
    for n in range(1, 9):
        assert f"<h2>{n} · " in page
    assert "as of <b>2026-10-27</b>" in page and "Synthetic data" in page
    assert "http://" not in page and "https://" not in page   # fully self-contained
