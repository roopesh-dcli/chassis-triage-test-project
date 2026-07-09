
from __future__ import annotations

from ..config import CONF_MIN  # noqa: F401  (documents the routing threshold this feeds)
from ..state import Assessment, Report, RepairScope, SeverityBand
from .tools import maintenance_history, photo_analysis

# Narrative cue families. Deliberately specific to avoid false positives (e.g. "destroyed"
# is excluded — #0009's "light bar destroyed" is collision damage, not a total loss).
TOTAL_LOSS_CUES = ("total loss", "totaled", "fire", "burned", "burnt", "melted")
STRUCTURAL_CUES = ("structural", "frame rail", "cracked frame", "bent frame", "collision",
                   "major repair", "propagating")
CONFLICT_CUES = ("disagree", "conflict", "contradict", "does not match", "doesn't match", "mismatch")
END_OF_LIFE_CUES = ("end of life", "end-of-life", "near end", "keep seeing", "recurring")
AMBIGUITY_CUES = ("feels loose", "could not find", "couldn't find", "can't find",
                  "nothing visible", "no obvious", "no visible defect", "intermittent")
SHOP_CUES = ("shop job", "send out", "sent out", "we send", "beyond what we do")
COSMETIC_CUES = ("cosmetic", "scuff", "mud flap")

REPORTER_CONF_BASE = {"high": 0.9, "medium": 0.65, "low": 0.35}


def _any(text: str, cues: tuple[str, ...]) -> bool:
    return any(c in text for c in cues)


class StubAssessor:
    mode = "stub"

    def assess(self, report: Report) -> Assessment:
        text = f"{report.damage_description}\n{report.incident_context}".lower()

        # Observable tool calls for the dashboard.
        tool_calls = [photo_analysis(report), maintenance_history(report)]

        total_loss = _any(text, TOTAL_LOSS_CUES)
        conflict = _any(text, CONFLICT_CUES)
        end_of_life = _any(text, END_OF_LIFE_CUES)
        ambiguous = _any(text, AMBIGUITY_CUES)
        shop = _any(text, SHOP_CUES)

        if total_loss:
            severity: SeverityBand = "total_loss"
        elif _any(text, STRUCTURAL_CUES):
            severity = "severe"
        elif _any(text, COSMETIC_CUES) and not ambiguous:
            severity = "minor"
        else:
            severity = "moderate"

        conf = REPORTER_CONF_BASE.get(report.reporter_confidence, 0.6)
        if conflict:
            conf = min(conf, 0.3)
        elif ambiguous:
            conf = min(conf, 0.4)

        repair_scope: RepairScope = "shop_vendor" if shop else "on_site"

        return Assessment(
            severity_band=severity,
            repair_scope_hint=repair_scope,
            total_loss_suspected=total_loss,
            conflict_detected=conflict,
            end_of_life_suspected=end_of_life,
            decision_confidence=round(conf, 2),
            rationale=self._rationale(total_loss, conflict, end_of_life, ambiguous, shop, severity),
            tool_calls=tool_calls,
        )

    @staticmethod
    def _rationale(total_loss, conflict, end_of_life, ambiguous, shop, severity) -> str:
        notes = [f"severity={severity}"]
        if total_loss:
            notes.append("total-loss language")
        if conflict:
            notes.append("narrative/data conflict")
        if end_of_life:
            notes.append("end-of-life language")
        if ambiguous:
            notes.append("unconfirmed / ambiguous complaint")
        if shop:
            notes.append("depot flagged shop/vendor work")
        return "Stub narrative read: " + "; ".join(notes) + "."
