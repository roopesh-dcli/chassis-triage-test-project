import pytest
from chassis_triage.data import load_reports_by_id
from chassis_triage.rules.cost import estimate_cost
from chassis_triage.rules.disposition import decide_disposition
from chassis_triage.rules.roadability import check_roadability
from chassis_triage.state import Assessment

REPORTS = load_reports_by_id()


def mk(severity="moderate", scope="on_site", total_loss=False, end_of_life=False, conf=0.9):
    return Assessment(severity_band=severity, repair_scope_hint=scope, total_loss_suspected=total_loss,
                      end_of_life_suspected=end_of_life, decision_confidence=conf, rationale="test fixture")


def _disposition(rid, a):
    report = REPORTS[rid]
    road = check_roadability(report)
    cost = estimate_cost(report, road, a.severity_band)
    return decide_disposition(report, road, cost, a).recommendation


CASES = [
    ("DMG-2026-0001", mk(severity="minor"), "repair_on_site"),
    ("DMG-2026-0002", mk(), "repair_on_site"),
    ("DMG-2026-0003", mk(), "repair_on_site"),
    ("DMG-2026-0004", mk(severity="severe"), "retire"),
    ("DMG-2026-0006", mk(severity="minor"), "repair_on_site"),
    ("DMG-2026-0007", mk(scope="shop_vendor"), "vendor"),
    ("DMG-2026-0008", mk(), "repair_on_site"),
    ("DMG-2026-0009", mk(severity="severe"), "retire"),
    ("DMG-2026-0010", mk(severity="minor"), "repair_on_site"),
    ("DMG-2026-0011", mk(scope="shop_vendor"), "vendor"),
    ("DMG-2026-0012", mk(end_of_life=True), "retire"),
    ("DMG-2026-0014", mk(scope="shop_vendor"), "vendor"),
    ("DMG-2026-0015", mk(total_loss=True), "retire"),
]


@pytest.mark.parametrize("rid,a,expected", CASES, ids=[c[0] for c in CASES])
def test_disposition(rid, a, expected):
    assert _disposition(rid, a) == expected


def test_llm_hint_escalates_on_site_to_vendor():
    assert _disposition("DMG-2026-0006", mk(scope="on_site")) == "repair_on_site"
    assert _disposition("DMG-2026-0006", mk(scope="shop_vendor")) == "vendor"


def test_llm_hint_never_downgrades_vendor():
    assert _disposition("DMG-2026-0007", mk(scope="on_site")) == "vendor"