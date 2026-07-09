from __future__ import annotations
import math
from ..state import CostEstimate, LineItem, Report, RoadabilityResult, SeverityBand
from .roadability import tire_is_oos

COST_BOOK = {
    "tire": 350, "brake_position": 300, "lamp": 120, "airline": 250,
    "frame_crack": 4000, "suspension": 950, "kingpin_coupler": 1200,
    "wheel_fastener": 350, "container_securing": 500, "baseline": 150,
}
# Severity may only escalate cost, never reduce it (F1 safe direction).
_SEVERITY_MULT = {"minor": 1.0, "moderate": 1.0, "severe": 1.15, "total_loss": 1.25}


def estimate_cost(report: Report, roadability: RoadabilityResult,
                  severity_band: SeverityBand | None = None) -> CostEstimate:
    rd = report.roadability_data
    items: list[LineItem] = []

    for t in (t for t in rd.tires if tire_is_oos(t)):
        items.append(LineItem(description=f"tire {t.position} replacement", amount_usd=COST_BOOK["tire"]))
    if rd.brakes_defective_pct > 0:
        positions = math.ceil(rd.brakes_defective_pct / 25)
        items.append(LineItem(description=f"brake service ({rd.brakes_defective_pct}% ~ {positions} position(s))",
                              amount_usd=positions * COST_BOOK["brake_position"]))
    for lamp in rd.required_lamps_inoperative:
        items.append(LineItem(description=f"{lamp} lamp repair", amount_usd=COST_BOOK["lamp"]))
    if rd.airline_leak:
        items.append(LineItem(description="brake airline repair", amount_usd=COST_BOOK["airline"]))
    if rd.frame_crack:
        items.append(LineItem(description="frame rail repair (structural)", amount_usd=COST_BOOK["frame_crack"]))
    if rd.suspension_defect:
        items.append(LineItem(description="suspension repair", amount_usd=COST_BOOK["suspension"]))
    if rd.kingpin_or_coupler_defect:
        items.append(LineItem(description="upper-coupler service", amount_usd=COST_BOOK["kingpin_coupler"]))
    if rd.wheel_or_fastener_defect:
        items.append(LineItem(description="wheel / fastener repair", amount_usd=COST_BOOK["wheel_fastener"]))
    if rd.container_securing_defect:
        items.append(LineItem(description="twist-lock replacement", amount_usd=COST_BOOK["container_securing"]))
    if not items:
        items.append(LineItem(description="minor / cosmetic repair", amount_usd=COST_BOOK["baseline"]))

    subtotal = sum(i.amount_usd for i in items)
    amount = round(subtotal * _SEVERITY_MULT.get(severity_band, 1.0), 2)
    return CostEstimate(amount_usd=amount, line_items=items, confidence=1.0)