import pytest

from chassis_triage.assessor import get_assessor
from chassis_triage.config import CONF_MIN
from chassis_triage.data import load_reports_by_id
from chassis_triage.state import (
    Assessment,
    Chassis,
    Depot,
    Report,
    ReportedBy,
    RoadabilityData,
)

REPORTS = load_reports_by_id()
ASSESS = get_assessor("stub").assess


@pytest.mark.parametrize("rid", sorted(REPORTS))
def test_assessment_is_valid_and_has_tool_calls(rid):
    a = ASSESS(REPORTS[rid])
    assert isinstance(a, Assessment)
    assert 0.0 <= a.decision_confidence <= 1.0
    tools = {tc["tool"] for tc in a.tool_calls}
    assert {"photo_analysis", "maintenance_history"} <= tools


def test_conflict_case_detected():
    a = ASSESS(REPORTS["DMG-2026-0013"])
    assert a.conflict_detected is True
    assert a.decision_confidence < CONF_MIN


def test_low_confidence_ambiguous_case():
    a = ASSESS(REPORTS["DMG-2026-0005"])
    assert a.decision_confidence < CONF_MIN
    assert a.conflict_detected is False


def test_end_of_life_case():
    assert ASSESS(REPORTS["DMG-2026-0012"]).end_of_life_suspected is True


def test_total_loss_case():
    a = ASSESS(REPORTS["DMG-2026-0015"])
    assert a.total_loss_suspected is True
    assert a.severity_band == "total_loss"


def test_collision_is_severe_not_total_loss():
    """Regression: #0009's 'light bar destroyed' must not read as a total loss."""
    a = ASSESS(REPORTS["DMG-2026-0009"])
    assert a.total_loss_suspected is False
    assert a.severity_band == "severe"


@pytest.mark.parametrize("rid", ["DMG-2026-0007", "DMG-2026-0011", "DMG-2026-0014"])
def test_shop_vendor_hint(rid):
    assert ASSESS(REPORTS[rid]).repair_scope_hint == "shop_vendor"


def test_cosmetic_is_minor_and_confident():
    a = ASSESS(REPORTS["DMG-2026-0001"])
    assert a.severity_band == "minor"
    assert a.decision_confidence >= CONF_MIN


# --- Anti-overfit: the stub must read CONTENT, not identity. Feed unseen narratives. ---


def _synthetic(desc: str, incident: str = "", reporter: str = "high") -> Report:
    return Report(
        report_id="SYNTH-9999",
        received_at="2026-01-01T00:00:00Z",
        depot=Depot(code="X", name="X", city_state="X"),
        reported_by=ReportedBy(name="tester", role="tester"),
        chassis=Chassis(id="TEST 000", type="40' tandem", model_year=2015,
                        in_service_years=10, est_replacement_value_usd=10000,
                        last_dot_inspection="2026-01-01"),
        damage_description=desc,
        incident_context=incident,
        roadability_data=RoadabilityData(),
        reporter_confidence=reporter,
    )


def test_generalizes_total_loss():
    a = ASSESS(_synthetic("Unit caught fire in the yard; harness burned, likely a total loss."))
    assert a.total_loss_suspected is True and a.severity_band == "total_loss"


def test_generalizes_cosmetic():
    a = ASSESS(_synthetic("Minor cosmetic scuff on the rail and a torn mud flap."))
    assert a.severity_band == "minor" and a.total_loss_suspected is False


def test_generalizes_ambiguous():
    a = ASSESS(_synthetic("Driver says it feels loose but the mechanic could not find anything.",
                          reporter="low"))
    assert a.decision_confidence < CONF_MIN and a.conflict_detected is False


def test_generalizes_shop_vendor():
    a = ASSESS(_synthetic("Kingpin worn beyond limit; this is a shop job, we send out."))
    assert a.repair_scope_hint == "shop_vendor"
