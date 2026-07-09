
from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .assessor import Assessor, get_assessor
from .config import CONF_MIN, HIGH_COST_THRESHOLD_USD
from .rules.cost import estimate_cost
from .rules.disposition import decide_disposition
from .rules.roadability import check_roadability
from .state import Assessment, CostEstimate, Disposition, Report, Review, RoadabilityResult

MAX_STEPS = 24  # loop guard — the router advances monotonically; this is insurance


class TriageState(TypedDict, total=False):
    report: dict
    assessment: Optional[dict]
    roadability: Optional[dict]
    cost: Optional[dict]
    disposition: Optional[dict]
    review: Optional[dict]
    routing_rationale: str
    planned_next: str
    step_count: int
    history: Annotated[list[dict], operator.add]


def initial_state(report: Report) -> dict:
    """Build the graph input from a Report (stored as a dict, like all state)."""
    return {"report": report.model_dump(), "history": []}


def _report(state: TriageState) -> Report:
    return Report.model_validate(state["report"])


def _hist(node: str, decision: str, confidence: float, tool_calls: list | None = None) -> dict:
    return {"node": node, "decision": decision, "confidence": confidence, "tool_calls": tool_calls or []}


# --- Human-review triggers (each a principled reason, PLAN.md §3.5) -------------


def _pre_disposition_reasons(state: TriageState) -> list[str]:
    a = state["assessment"]
    r = state["roadability"]
    reasons: list[str] = []
    if a["conflict_detected"]:
        reasons.append("narrative/data conflict")
    if r["advisory_flags"]:
        reasons.append(f"advisory signal: {', '.join(r['advisory_flags'])}")
    if a["decision_confidence"] < CONF_MIN:
        reasons.append(f"low assessor confidence ({a['decision_confidence']})")
    return reasons


def _post_disposition_reasons(state: TriageState) -> list[str]:
    a = state["assessment"]
    c = state["cost"]
    d = state["disposition"]
    reasons: list[str] = []
    if c["amount_usd"] >= HIGH_COST_THRESHOLD_USD:
        reasons.append(f"high cost (${c['amount_usd']:,.0f})")
    if d["recommendation"] == "retire":
        reasons.append("retirement recommended")
    if a["total_loss_suspected"]:
        reasons.append("total loss suspected")
    return reasons


def _route(state: TriageState) -> tuple[str, str]:
    """Deterministic next-hop from current state. Returns (target_node, rationale)."""
    if state.get("assessment") is None:
        return "assessor", "interpret the free-text narrative"
    if state.get("roadability") is None:
        return "roadability", "apply deterministic FMCSA out-of-service rules"

    review = state.get("review")
    reviewed = bool(review and review.get("status") in ("approved", "overridden"))

    if not reviewed:
        pre = _pre_disposition_reasons(state)
        if pre:
            return "human_review", "pause for human — " + "; ".join(pre)

    if state.get("cost") is None:
        return "cost", "estimate repair cost"
    if state.get("disposition") is None:
        return "disposition", "decide repair / vendor / retire"

    if not reviewed:
        post = _post_disposition_reasons(state)
        if post:
            return "human_review", "pause for human — " + "; ".join(post)

    return "resolve", "auto-resolve — no human trigger fired"


def build_graph(assessor: Assessor | None = None, checkpointer=None):
    assessor = assessor or get_assessor()
    checkpointer = checkpointer if checkpointer is not None else MemorySaver()

    def supervisor(
        state: TriageState,
    ) -> Command[Literal["assessor", "roadability", "cost", "disposition", "human_review", "resolve"]]:
        target, rationale = _route(state)
        step = state.get("step_count", 0) + 1
        if step > MAX_STEPS:
            target, rationale = "resolve", "step guard tripped"
        return Command(
            goto=target,
            update={
                "routing_rationale": rationale,
                "planned_next": target,
                "step_count": step,
                "history": [_hist("supervisor", f"-> {target}: {rationale}", 1.0)],
            },
        )

    def assessor_node(state: TriageState) -> dict:
        a = assessor.assess(_report(state))
        return {
            "assessment": a.model_dump(),
            "history": [_hist("assessor", f"severity={a.severity_band}, conf={a.decision_confidence}",
                              a.decision_confidence, a.tool_calls)],
        }

    def roadability_node(state: TriageState) -> dict:
        r = check_roadability(_report(state))
        if not r.roadable:
            decision = "OUT OF SERVICE"
        elif not r.fit_for_service:
            decision = "roadable, not fit for container"
        else:
            decision = "roadable"
        return {
            "roadability": r.model_dump(),
            "history": [_hist("roadability", decision, r.confidence,
                              [{"tool": "fmcsa_oos_rules", "args": {}, "result": r.oos_reasons or "clean"}])],
        }

    def cost_node(state: TriageState) -> dict:
        road = RoadabilityResult.model_validate(state["roadability"])
        c = estimate_cost(_report(state), road, state["assessment"]["severity_band"])
        return {
            "cost": c.model_dump(),
            "history": [_hist("cost", f"${c.amount_usd:,.0f}", c.confidence,
                              [{"tool": "cost_book", "args": {}, "result": [li.model_dump() for li in c.line_items]}])],
        }

    def disposition_node(state: TriageState) -> dict:
        road = RoadabilityResult.model_validate(state["roadability"])
        cost = CostEstimate.model_validate(state["cost"])
        assess = Assessment.model_validate(state["assessment"])
        d = decide_disposition(_report(state), road, cost, assess)
        return {"disposition": d.model_dump(), "history": [_hist("disposition", d.recommendation, d.confidence)]}

    def human_review_node(state: TriageState) -> dict:
        reasons = _pre_disposition_reasons(state)
        if state.get("disposition") is not None:
            reasons += _post_disposition_reasons(state)
        payload = {
            "report_id": state["report"]["report_id"],
            "reasons": reasons,
            "assessment": state["assessment"],
            "roadability": state["roadability"],
            "cost": state.get("cost"),
            "disposition": state.get("disposition"),
        }
        decision = interrupt(payload)  # durable pause; resume with Command(resume=decision)
        if isinstance(decision, str):
            decision = {"action": "approve", "note": decision}

        current = state.get("disposition")
        rec = decision.get("disposition") or (current["recommendation"] if current else "repair_on_site")
        status = "overridden" if decision.get("action") == "override" else "approved"
        review = Review(required=True, reasons=reasons, status=status, human_decision=decision)
        disposition = Disposition(recommendation=rec,
                                  rationale=f"Human {status}: {decision.get('note', '')}".strip(),
                                  confidence=1.0)
        return {"review": review.model_dump(), "disposition": disposition.model_dump(),
                "history": [_hist("human_review", f"{status} -> {rec}", 1.0)]}

    def resolve_node(state: TriageState) -> dict:
        d = state.get("disposition")
        outcome = d["recommendation"] if d else "unresolved"
        return {"history": [_hist("resolve", f"final disposition: {outcome}", 1.0)]}

    g = StateGraph(TriageState)
    g.add_node("supervisor", supervisor)
    g.add_node("assessor", assessor_node)
    g.add_node("roadability", roadability_node)
    g.add_node("cost", cost_node)
    g.add_node("disposition", disposition_node)
    g.add_node("human_review", human_review_node)
    g.add_node("resolve", resolve_node)

    g.add_edge(START, "supervisor")
    for n in ("assessor", "roadability", "cost", "disposition"):
        g.add_edge(n, "supervisor")
    g.add_edge("human_review", "resolve")
    g.add_edge("resolve", END)

    return g.compile(checkpointer=checkpointer)
