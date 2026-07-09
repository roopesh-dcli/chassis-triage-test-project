import pytest
from chassis_triage.data import load_reports_by_id
from chassis_triage.golden import GOLDEN
from chassis_triage.rules.roadability import check_roadability

REPORTS = load_reports_by_id()


@pytest.mark.parametrize("rid", sorted(GOLDEN))
def test_roadability_matches_golden(rid):
    exp, res = GOLDEN[rid], check_roadability(REPORTS[rid])
    assert res.roadable is exp["roadable"], (rid, res.oos_reasons)
    assert res.fit_for_service is exp["fit"], (rid, res.oos_reasons)
    assert (len(res.oos_reasons) > 0) is exp["oos"], (rid, res.oos_reasons)
    assert (len(res.advisory_flags) > 0) is exp["advisory"], (rid, res.advisory_flags)


def test_conflict_case_is_roadable_but_flagged():
    res = check_roadability(REPORTS["DMG-2026-0013"])
    assert res.roadable is True and res.advisory_flags and not res.oos_reasons


def test_container_defect_is_roadable_but_not_fit():
    res = check_roadability(REPORTS["DMG-2026-0014"])
    assert res.roadable is True and res.fit_for_service is False


def test_loose_lugnuts_are_not_oos():
    assert check_roadability(REPORTS["DMG-2026-0010"]).roadable is True

