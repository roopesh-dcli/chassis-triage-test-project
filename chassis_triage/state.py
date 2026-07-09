
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class Tire(BaseModel):
    position: str
    tread_32nds: int
    condition: str


class RoadabilityData(BaseModel):

    model_config = ConfigDict(extra="allow")
    tires: list[Tire] = Field(default_factory=list)
    brakes_defective_pct: int = 0
    required_lamps_inoperative: list[str] = Field(default_factory=list)
    frame_crack: bool = False
    suspension_defect: bool = False
    kingpin_or_coupler_defect: bool = False
    airline_leak: bool = False
    wheel_or_fastener_defect: bool = False
    container_securing_defect: bool = False

    @property
    def ad_hoc_signals(self) -> dict:
        """Fields beyond the core OOS set (e.g. abs_fault_active) — a human-review trigger."""
        return dict(self.model_extra or {})


class Depot(BaseModel):
    code: str
    name: str
    city_state: str


class ReportedBy(BaseModel):
    name: str
    role: str


class Chassis(BaseModel):
    id: str
    type: str
    model_year: int
    in_service_years: int
    est_replacement_value_usd: float
    last_dot_inspection: str


class Report(BaseModel):
    report_id: str
    received_at: str
    depot: Depot
    reported_by: ReportedBy
    chassis: Chassis
    damage_description: str
    incident_context: str
    roadability_data: RoadabilityData
    reporter_confidence: Literal["low", "medium", "high"]


SeverityBand = Literal["minor", "moderate", "severe", "total_loss"]
RepairScope = Literal["on_site", "shop_vendor"]
Recommendation = Literal["repair_on_site", "vendor", "retire"]


class Assessment(BaseModel):
    """Structured output of the Damage Assessor — the single language boundary."""
    severity_band: SeverityBand
    repair_scope_hint: RepairScope
    total_loss_suspected: bool = False
    conflict_detected: bool = False
    end_of_life_suspected: bool = False
    decision_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = ""
    tool_calls: list[dict] = Field(default_factory=list)


class RoadabilityResult(BaseModel):
    roadable: bool
    fit_for_service: bool
    oos_reasons: list[str] = Field(default_factory=list)
    advisory_flags: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class LineItem(BaseModel):
    description: str
    amount_usd: float


class CostEstimate(BaseModel):
    amount_usd: float
    line_items: list[LineItem] = Field(default_factory=list)
    confidence: float = 1.0


class Disposition(BaseModel):
    recommendation: Recommendation
    rationale: str = ""
    confidence: float = 1.0


class Review(BaseModel):
    required: bool = False
    reasons: list[str] = Field(default_factory=list)
    status: Literal["pending", "approved", "overridden"] = "pending"
    human_decision: Optional[dict] = None