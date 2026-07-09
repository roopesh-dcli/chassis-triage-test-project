"""The eval oracle (PLAN.md §5) — expected deterministic outcomes for the 15 reports.

TEST FIXTURES, not the logic. These must be reproducible by running the rules blind.
Only deterministic (no-LLM) columns live here.
"""
from __future__ import annotations

GOLDEN: dict[str, dict] = {
    "DMG-2026-0001": dict(oos=False, roadable=True,  fit=True,  advisory=False, high_cost=False),
    "DMG-2026-0002": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=False),
    "DMG-2026-0003": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=False),
    "DMG-2026-0004": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=True),
    "DMG-2026-0005": dict(oos=False, roadable=True,  fit=True,  advisory=False, high_cost=False),
    "DMG-2026-0006": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=False),
    "DMG-2026-0007": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=False),
    "DMG-2026-0008": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=False),
    "DMG-2026-0009": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=True),
    "DMG-2026-0010": dict(oos=False, roadable=True,  fit=True,  advisory=False, high_cost=False),
    "DMG-2026-0011": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=False),
    "DMG-2026-0012": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=False),
    "DMG-2026-0013": dict(oos=False, roadable=True,  fit=True,  advisory=True,  high_cost=False),
    "DMG-2026-0014": dict(oos=False, roadable=True,  fit=False, advisory=False, high_cost=False),
    "DMG-2026-0015": dict(oos=True,  roadable=False, fit=False, advisory=False, high_cost=True),
}