from __future__ import annotations

from typing import Protocol

from ..state import Assessment, Report


class Assessor(Protocol):
    mode: str

    def assess(self, report: Report) -> Assessment: ...
