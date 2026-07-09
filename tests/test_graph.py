import pytest
from langgraph.types import Command

from chassis_triage.data import load_reports_by_id
from chassis_triage.graph import build_graph, initial_state

REPORTS = load_reports_by_id()

# Expected to pause for a human (PLAN.md §5). Everything else auto-resolves.
HUMAN_REVIEW = {
    "DMG-2026-0004",  # frame crack -> high cost / retire
    "DMG-2026-0005",  # loose feel, nothing visible -> low confidence
    "DMG-2026-0009",  # collision -> high cost / retire
    "DMG-2026-0012",  # 19-yr end-of-life -> retire
    "DMG-2026-0013",  # ABS conflict -> advisory (pre-disposition)
    "DMG-2026-0015",  # fire -> total loss / retire
}


def _run(rid):
    graph = build_graph()
    cfg = {"configurable": {"thread_id": rid}}
    graph.invoke(initial_state(REPORTS[rid]), cfg)
    return graph, cfg


@pytest.mark.parametrize("rid", sorted(REPORTS))
def test_terminal_split(rid):
    graph, cfg = _run(rid)
    st = graph.get_state(cfg)
    assert bool(st.next) is (rid in HUMAN_REVIEW), (rid, st.next, st.values.get("disposition"))


@pytest.mark.parametrize("rid", sorted(set(REPORTS) - HUMAN_REVIEW))
def test_auto_cases_reach_resolution(rid):
    graph, cfg = _run(rid)
    st = graph.get_state(cfg)
    assert st.next == ()
    assert st.values["disposition"] is not None


def test_conflict_case_skips_cost_and_disposition():
    """#0013: pre-disposition gate -> human review; cost + disposition never run."""
    graph, cfg = _run("DMG-2026-0013")
    st = graph.get_state(cfg)
    assert st.next == ("human_review",)
    assert st.values.get("cost") is None
    assert st.values.get("disposition") is None
    # the ABS ad-hoc signal survived the dict round-trip and drove the advisory
    assert st.values["roadability"]["advisory_flags"]


def test_planned_next_names_real_targets():
    """Fix 1: get_state().next names the real target after the supervisor, not 'supervisor'."""
    graph, cfg = _run("DMG-2026-0001")
    nexts = [snap.next for snap in graph.get_state_history(cfg)]
    for target in [("roadability",), ("cost",), ("disposition",), ("resolve",)]:
        assert target in nexts, (target, nexts)


def test_supervisor_reentered_and_order():
    graph = build_graph()
    order: list[str] = []
    stream = graph.stream(
        initial_state(REPORTS["DMG-2026-0002"]),
        {"configurable": {"thread_id": "order"}},
        stream_mode="updates",
    )
    for chunk in stream:
        order.extend(chunk.keys())
    assert order.count("supervisor") >= 4
    assert order.index("assessor") < order.index("roadability") < order.index("cost") < order.index("disposition")


def test_human_resume_overrides_disposition():
    graph = build_graph()
    cfg = {"configurable": {"thread_id": "resume-0013"}}
    graph.invoke(initial_state(REPORTS["DMG-2026-0013"]), cfg)
    assert graph.get_state(cfg).next == ("human_review",)

    graph.invoke(Command(resume={"action": "override", "disposition": "vendor", "note": "send for ABS diagnosis"}), cfg)
    st = graph.get_state(cfg)
    assert st.next == ()
    assert st.values["disposition"]["recommendation"] == "vendor"
    assert st.values["review"]["status"] == "overridden"


def test_history_records_each_node():
    graph, cfg = _run("DMG-2026-0001")
    nodes = [h["node"] for h in graph.get_state(cfg).values["history"]]
    assert nodes[0] == "supervisor"
    assert {"assessor", "roadability", "cost", "disposition", "resolve"} <= set(nodes)


def test_runs_with_sqlite_checkpointer():
    """Durable path: state serializes through the SQLite checkpointer, pause + resume."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    with SqliteSaver.from_conn_string(":memory:") as saver:
        graph = build_graph(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "sq"}}
        graph.invoke(initial_state(REPORTS["DMG-2026-0004"]), cfg)
        assert graph.get_state(cfg).next == ("human_review",)
        graph.invoke(Command(resume={"action": "approve", "note": "ok"}), cfg)
        assert graph.get_state(cfg).next == ()
