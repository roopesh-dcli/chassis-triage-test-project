from __future__ import annotations
from ..config import RETIRE_COST_FRACTION, TYPICAL_SERVICE_LIFE_YEARS
from ..state import Assessment, CostEstimate, Disposition, Report, RoadabilityResult
from .cost import COST_BOOK


def _defect_needs_vendor(report: Report) -> bool:
    rd = report.roadability_data
    return (rd.kingpin_or_coupler_defect or rd.suspension_defect
            or rd.container_securing_defect or rd.frame_crack)


def decide_disposition(report: Report, roadability: RoadabilityResult, cost: CostEstimate,
                       assessment: Assessment | None = None) -> Disposition:
    chassis = report.chassis
    replacement = chassis.est_replacement_value_usd
    total_loss = bool(assessment and assessment.total_loss_suspected)
    end_of_life = bool(assessment and assessment.end_of_life_suspected)
    needs_real_spend = cost.amount_usd > COST_BOOK["baseline"]

    if total_loss:
        return Disposition(recommendation="retire", rationale="Total loss suspected.")
    if cost.amount_usd >= RETIRE_COST_FRACTION * replacement:
        return Disposition(recommendation="retire",
            rationale=f"Repair ${cost.amount_usd:,.0f} >= {RETIRE_COST_FRACTION:.0%} of replacement ${replacement:,.0f}.")
    if end_of_life and chassis.in_service_years >= TYPICAL_SERVICE_LIFE_YEARS and needs_real_spend:
        return Disposition(recommendation="retire",
            rationale=f"End-of-life unit ({chassis.in_service_years} yrs >= {TYPICAL_SERVICE_LIFE_YEARS}) needing real spend.")

    if _defect_needs_vendor(report):
        return Disposition(recommendation="vendor", rationale="Defect type is a shop/vendor job.")
    if assessment and assessment.repair_scope_hint == "shop_vendor":
        return Disposition(recommendation="vendor", rationale="Depot flagged as beyond on-site capability (escalated).")

    return Disposition(recommendation="repair_on_site", rationale="Minor / serviceable defect within depot capability.")