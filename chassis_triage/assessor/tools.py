
from __future__ import annotations

from ..state import Report


def photo_analysis(report: Report) -> dict:
   
    return {
        "tool": "photo_analysis",
        "args": {"report_id": report.report_id},
        "result": "no image attached (text-only dataset); vision stub returned no additional findings",
    }


def maintenance_history(report: Report) -> dict:
    """Simulated maintenance-history lookup, derived deterministically from the chassis."""
    yrs = report.chassis.in_service_years
    prior = min(9, max(0, yrs - 5))
    return {
        "tool": "maintenance_history",
        "args": {"chassis_id": report.chassis.id},
        "result": f"{prior} prior work order(s) on record ({yrs} yrs in service)",
    }
