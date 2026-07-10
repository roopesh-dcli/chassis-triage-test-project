"""API tests — endpoints + SSE streaming, driven in-process via httpx ASGITransport.

Uses a MemorySaver graph injected through create_app(graph=...), so no server or SQLite
is needed. A single client keeps one graph/checkpointer, so stream-then-resume shares a thread.
"""
import json

import httpx

from chassis_triage.api import create_app
from chassis_triage.graph import build_graph
from langgraph.checkpoint.memory import MemorySaver


def make_client() -> httpx.AsyncClient:
    app = create_app(graph=build_graph(checkpointer=MemorySaver()))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def parse_sse(text: str) -> list[dict]:
    events = []
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # SSE uses \r\n line endings
    for block in text.strip().split("\n\n"):
        ev = {}
        for line in block.splitlines():
            if line.startswith("event:"):
                ev["event"] = line[len("event:"):].strip()
            elif line.startswith("data:"):
                ev["data"] = json.loads(line[len("data:"):].strip())
        if "event" in ev:
            events.append(ev)
    return events


async def test_dashboard_is_served_at_root():
    async with make_client() as c:
        response = await c.get("/")
        assert response.status_code == 200
        assert "DCLI Chassis Triage" in response.text


async def test_health_reports_configured_llm_mode(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "bedrock")
    async with make_client() as c:
        response = await c.get("/health")
        assert response.json() == {"ok": True, "llm_mode": "bedrock"}


async def test_reports_list():
    async with make_client() as c:
        r = await c.get("/reports")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 15
        assert all("report_id" in d and "damage_description" in d for d in data)


async def test_graph_topology():
    async with make_client() as c:
        g = (await c.get("/graph")).json()
        ids = {n["id"] for n in g["nodes"]}
        assert {"supervisor", "assessor", "roadability", "cost", "disposition",
                "human_review", "resolve"} <= ids
        assert {"source": "supervisor", "target": "human_review"} in g["edges"]


async def test_unknown_report_404():
    async with make_client() as c:
        assert (await c.get("/reports/NOPE")).status_code == 404


async def test_stream_auto_case():
    async with make_client() as c:
        r = await c.get("/triage/stream", params={"report_id": "DMG-2026-0001", "thread_id": "a1"})
        events = parse_sse(r.text)
        assert events[0]["event"] == "start"
        assert events[-1]["event"] == "complete"

        complete = events[-1]["data"]
        assert complete["terminal"] == "resolved"
        assert complete["state"]["disposition"]["recommendation"] == "repair_on_site"

        step_nodes = [e["data"]["node"] for e in events if e["event"] == "step"]
        assert "assessor" in step_nodes and "resolve" in step_nodes
        # planned_next surfaced during the run (the dashboard's "what's next")
        assert any(e["data"].get("planned_next") for e in events if e["event"] == "step")


async def test_stream_human_case_pauses():
    async with make_client() as c:
        r = await c.get("/triage/stream", params={"report_id": "DMG-2026-0013", "thread_id": "h13"})
        complete = parse_sse(r.text)[-1]["data"]
        assert complete["terminal"] == "human_review"
        assert complete["planned_next"] == "human_review"
        st = complete["state"]
        assert st["cost"] is None and st["disposition"] is None
        assert "conflict" in st["routing_rationale"]


async def test_resume_overrides_disposition():
    async with make_client() as c:
        r = await c.get("/triage/stream", params={"report_id": "DMG-2026-0013", "thread_id": "r13"})
        assert parse_sse(r.text)[-1]["data"]["terminal"] == "human_review"

        rr = await c.post("/triage/r13/resume",
                          json={"action": "override", "disposition": "vendor", "note": "abs diag"})
        body = rr.json()
        assert body["terminal"] == "resolved"
        assert body["state"]["disposition"]["recommendation"] == "vendor"
        assert body["state"]["review"]["status"] == "overridden"
