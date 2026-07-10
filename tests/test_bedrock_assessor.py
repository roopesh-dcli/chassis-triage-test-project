"""Unit and opt-in integration coverage for the live Bedrock assessor."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from chassis_triage.assessor import BedrockAssessor, get_assessor
from chassis_triage.assessor.bedrock import (
    DEFAULT_BEDROCK_MODEL_ID,
    BedrockAssessmentOutput,
)
from chassis_triage.data import load_reports_by_id
from chassis_triage.state import Assessment

REPORT = load_reports_by_id()["DMG-2026-0005"]


class _FakeMessages:
    def __init__(self, parsed_output) -> None:
        self.parsed_output = parsed_output
        self.request: dict | None = None

    def parse(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(parsed_output=self.parsed_output)


class _FakeClient:
    def __init__(self, parsed_output) -> None:
        self.messages = _FakeMessages(parsed_output)


def _wire_output(**overrides) -> dict:
    return {
        "severity_band": "moderate",
        "repair_scope_hint": "on_site",
        "total_loss_suspected": False,
        "conflict_detected": False,
        "end_of_life_suspected": False,
        "decision_confidence": 0.4,
        "rationale": "The report describes an unconfirmed loose feeling with no visible defect.",
        **overrides,
    }


def test_factory_selects_bedrock_without_contacting_aws():
    assessor = get_assessor("bedrock")
    assert isinstance(assessor, BedrockAssessor)
    assert assessor.model_id == DEFAULT_BEDROCK_MODEL_ID


def test_bedrock_assessor_uses_structured_output_and_preserves_contract():
    client = _FakeClient(_wire_output())
    assessment = BedrockAssessor(client=client).assess(REPORT)

    assert isinstance(assessment, Assessment)
    assert assessment.decision_confidence == 0.4
    assert {call["tool"] for call in assessment.tool_calls} == {
        "photo_analysis",
        "maintenance_history",
    }

    request = client.messages.request
    assert request is not None
    assert request["model"] == DEFAULT_BEDROCK_MODEL_ID
    assert request["output_format"] is BedrockAssessmentOutput
    assert request["temperature"] == 0

    # The LLM receives narrative evidence, not an ID it could overfit or the
    # structured OOS data reserved for the deterministic roadability node.
    payload = json.loads(request["messages"][0]["content"])
    assert set(payload) == {"damage_description", "incident_context", "reporter_confidence"}
    assert "report_id" not in request["messages"][0]["content"]
    assert "roadability_data" not in request["messages"][0]["content"]


def test_final_domain_model_enforces_confidence_bound():
    client = _FakeClient(_wire_output(decision_confidence=1.5))
    with pytest.raises(ValueError, match="Assessment contract"):
        BedrockAssessor(client=client).assess(REPORT)


def test_missing_structured_output_is_a_clear_error():
    client = _FakeClient(None)
    with pytest.raises(RuntimeError, match="no parsed structured"):
        BedrockAssessor(client=client).assess(REPORT)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_BEDROCK_INTEGRATION") != "1",
    reason="set RUN_BEDROCK_INTEGRATION=1 with a valid AWS SSO session to call Bedrock",
)
def test_live_bedrock_marks_end_of_life_case_for_review():
    """Small live rubric check; use BEDROCK_MODEL_ID=...opus-4-8 for final validation."""
    assessment = BedrockAssessor().assess(load_reports_by_id()["DMG-2026-0012"])
    assert isinstance(assessment, Assessment)
    assert assessment.end_of_life_suspected is True
    assert 0.0 <= assessment.decision_confidence <= 1.0
