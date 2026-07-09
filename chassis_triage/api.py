"""FastAPI backend — HTTP + SSE around the triage graph.

Endpoints:
  GET  /reports                     list the 15 reports (dashboard queue)
  GET  /reports/{id}                one full report
  GET  /graph                       static node/edge topology for React Flow
  GET  /triage/stream?report_id=..  run a report; stream node events + planned_next (SSE)
  POST /triage/{thread}/resume      submit a human decision; un-pause the review
  GET  /triage/{thread}/state       current snapshot (reconnect/poll fallback)

"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .data import load_reports, load_reports_by_id
from .graph import build_graph, initial_state
from .state import Report

# Static topology for the dashboard graph view (the supervisor routes dynamically via
# Command(goto), so we declare the drawable shape explicitly).
TOPOLOGY = {
    "nodes": [
        {"id": "supervisor", "label": "Supervisor", "kind": "router"},
        {"id": "assessor", "label": "Damage Assessor", "kind": "agent"},
        {"id": "roadability", "label": "Roadability Checker", "kind": "rules"},
        {"id": "cost", "label": "Cost Estimator", "kind": "rules"},
        {"id": "disposition", "label": "Disposition", "kind": "rules"},
        {"id": "human_review", "label": "Human Review", "kind": "human"},
        {"id": "resolve", "label": "Resolve", "kind": "terminal"},
    ],
    "edges": [
        {"source": "supervisor", "target": "assessor"},
        {"source": "supervisor", "target": "roadability"},
        {"source": "supervisor", "target": "cost"},
        {"source": "supervisor", "target": "disposition"},
        {"source": "supervisor", "target": "human_review"},
        {"source": "supervisor", "target": "resolve"},
        {"source": "assessor", "target": "supervisor"},
        {"source": "roadability", "target": "supervisor"},
        {"source": "cost", "target": "supervisor"},
        {"source": "disposition", "target": "supervisor"},
        {"source": "human_review", "target": "resolve"},
    ],
}


class Decision(BaseModel):
    action: Literal["approve", "override"] = "approve"
    disposition: Optional[Literal["repair_on_site", "vendor", "retire"]] = None
    note: str = ""


def _summary(r: Report) -> dict:
    return {
        "report_id": r.report_id,
        "depot": r.depot.city_state,
        "chassis_id": r.chassis.id,
        "chassis_type": r.chassis.type,
        "in_service_years": r.chassis.in_service_years,
        "reporter_confidence": r.reporter_confidence,
        "damage_description": r.damage_description,
    }


def _step_event(node: str, upd: dict) -> dict:
    """Turn one graph-update chunk into a clean event for the dashboard."""
    hist = upd.get("history") or []
    entry = hist[-1] if hist else {}
    return {
        "node": node,
        "decision": entry.get("decision"),
        "confidence": entry.get("confidence"),
        "tool_calls": entry.get("tool_calls", []),
        "planned_next": upd.get("planned_next"),        # supervisor only
        "routing_rationale": upd.get("routing_rationale"),
    }


async def _astep(graph, config, graph_input):
    """Async-stream one graph run, yielding a step event per executed node."""
    async for chunk in graph.astream(graph_input, config, stream_mode="updates"):
        for node, upd in chunk.items():
            if node == "__interrupt__":
                continue
            yield _step_event(node, upd)


# Predictable state shape for the dashboard — keys always present, even when a node was
# skipped (e.g. a conflict case never runs cost/disposition).
STATE_KEYS = ("report", "assessment", "roadability", "cost", "disposition", "review",
              "routing_rationale", "planned_next", "history")


def _normalize_state(values: dict) -> dict:
    return {k: values.get(k) for k in STATE_KEYS}


async def _terminal(graph, config) -> dict:
    snap = await graph.aget_state(config)
    return {
        "terminal": "human_review" if snap.next else "resolved",
        "planned_next": snap.next[0] if snap.next else None,
        "state": _normalize_state(snap.values),
    }


def create_app(graph=None) -> FastAPI:
    if graph is not None:
        app = FastAPI(title="Chassis Triage API")
        app.state.graph = graph
        _configure(app)
        return app

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        db = os.getenv("CHASSIS_DB", "triage.sqlite")
        async with AsyncSqliteSaver.from_conn_string(db) as saver:
            app.state.graph = build_graph(checkpointer=saver)
            yield

    app = FastAPI(title="Chassis Triage API", lifespan=lifespan)
    _configure(app)
    return app


def _configure(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/reports")
    def reports():
        return [_summary(r) for r in load_reports()]

    @app.get("/reports/{rid}")
    def report(rid: str):
        by = load_reports_by_id()
        if rid not in by:
            raise HTTPException(404, "unknown report")
        return by[rid].model_dump()

    @app.get("/graph")
    def graph_topology():
        return TOPOLOGY

    @app.get("/triage/stream")
    async def triage_stream(request: Request, report_id: str, thread_id: Optional[str] = None):
        graph = request.app.state.graph
        by = load_reports_by_id()
        if report_id not in by:
            raise HTTPException(404, "unknown report")
        report = by[report_id]
        tid = thread_id or f"t-{uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": tid}}

        async def gen():
            yield {"event": "start", "data": json.dumps({"thread_id": tid, "report_id": report_id})}
            async for step in _astep(graph, config, initial_state(report)):
                yield {"event": "step", "data": json.dumps(step)}
            yield {"event": "complete", "data": json.dumps(await _terminal(graph, config))}

        return EventSourceResponse(gen())

    @app.post("/triage/{thread_id}/resume")
    async def resume(request: Request, thread_id: str, decision: Decision):
        graph = request.app.state.graph
        config = {"configurable": {"thread_id": thread_id}}
        steps = [s async for s in _astep(graph, config, Command(resume=decision.model_dump()))]
        result = await _terminal(graph, config)
        result["steps"] = steps
        return result

    @app.get("/triage/{thread_id}/state")
    async def state(request: Request, thread_id: str):
        graph = request.app.state.graph
        return await _terminal(graph, {"configurable": {"thread_id": thread_id}})


app = create_app()
