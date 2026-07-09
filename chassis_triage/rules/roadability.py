from __future__ import annotations
from ..config import BRAKES_OOS_PCT, TIRE_MIN_TREAD_32NDS
from ..state import Report, RoadabilityResult, Tire

OOS_TIRE_CONDITIONS = {"flat", "exposed_cords", "sidewall_bulge", "audible_leak", "melted"}
BENIGN_TIRE_CONDITIONS = {"ok", "worn"}  # roadworthiness rides on the tread check instead


def tire_is_oos(tire: Tire) -> bool:
    if tire.tread_32nds < TIRE_MIN_TREAD_32NDS:
        return True
    if tire.condition in OOS_TIRE_CONDITIONS:
        return True
    return tire.condition not in BENIGN_TIRE_CONDITIONS  # unrecognized -> conservative OOS


def check_roadability(report: Report) -> RoadabilityResult:
    rd = report.roadability_data
    oos: list[str] = []

    for t in rd.tires:
        if t.tread_32nds < TIRE_MIN_TREAD_32NDS:
            oos.append(f"tire {t.position}: tread {t.tread_32nds}/32 < {TIRE_MIN_TREAD_32NDS}/32")
        elif t.condition in OOS_TIRE_CONDITIONS:
            oos.append(f"tire {t.position}: condition '{t.condition}'")
        elif t.condition not in BENIGN_TIRE_CONDITIONS:
            oos.append(f"tire {t.position}: unrecognized condition '{t.condition}'")

    if rd.brakes_defective_pct >= BRAKES_OOS_PCT:
        oos.append(f"brakes: {rd.brakes_defective_pct}% defective >= {BRAKES_OOS_PCT}%")
    if rd.required_lamps_inoperative:
        oos.append(f"required lamp(s) inoperative: {', '.join(rd.required_lamps_inoperative)}")
    if rd.frame_crack:
        oos.append("frame crack (structural)")
    if rd.suspension_defect:
        oos.append("suspension defect")
    if rd.kingpin_or_coupler_defect:
        oos.append("kingpin / upper-coupler wear beyond limit")
    if rd.airline_leak:
        oos.append("brake airline leak")
    if rd.wheel_or_fastener_defect:
        oos.append("cracked wheel / broken or missing fastener")

    roadable = len(oos) == 0
    fit_for_service = roadable and not rd.container_securing_defect  # stricter than roadable
    advisory_flags = [k for k, v in rd.ad_hoc_signals.items() if v]

    return RoadabilityResult(
        roadable=roadable, fit_for_service=fit_for_service,
        oos_reasons=oos, advisory_flags=advisory_flags, confidence=1.0,
    )