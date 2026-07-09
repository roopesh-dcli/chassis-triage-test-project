import pytest
from chassis_triage.config import HIGH_COST_THRESHOLD_USD
from chassis_triage.data import load_reports_by_id
from chassis_triage.golden import GOLDEN
from chassis_triage.rules.cost import estimate_cost
from chassis_triage.rules.roadability import check_roadability

REPORTS = load_reports_by_id()


@pytest.mark.parametrize("rid", sorted(GOLDEN))
def test_high_cost_classification_matches_golden(rid):
    report = REPORTS[rid]
    cost = estimate_cost(report, check_roadability(report))
    assert (cost.amount_usd >= HIGH_COST_THRESHOLD_USD) is GOLDEN[rid]["high_cost"], (rid, cost.amount_usd)


def test_severity_can_only_raise_cost():
    report = REPORTS["DMG-2026-0004"]  # frame crack
    road = check_roadability(report)
    low = estimate_cost(report, road, "minor")
    high = estimate_cost(report, road, "total_loss")
    assert high.amount_usd >= low.amount_usd >= HIGH_COST_THRESHOLD_USD


def test_cost_always_has_line_items():
    for rid, report in REPORTS.items():
        cost = estimate_cost(report, check_roadability(report))
        assert cost.line_items and cost.amount_usd > 0, rid