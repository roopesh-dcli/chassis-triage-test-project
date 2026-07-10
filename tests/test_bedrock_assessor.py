"""Unit and opt-in integration coverage for the live Bedrock assessor."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from chassis_triage.assessor import BedrockAssessor, get_assessor
from chassis_triage.assessor.bedrock import (
    ASSESSMENT_TOOL,
    DEFAULT_BEDROCK_MODEL_ID,
    TOOL_NAME,
    BedrockAssessmentOutput,
)
from chassis_triage.data import load_reports_by_id
from chassis_triage.state import Assessment

REPORT = load_reports_by_id()["DMG-2026-0005"]


class _FakeMessages:
    """Mimics the shape Bedrock actually returns: a forced tool_use content block."""

    def __init__(self, tool_input, *, stop_reason="tool_use", emit_tool_use=True) -> None:
        self._tool_input = tool_input
        self._stop_reason = stop_reason
        self._emit_tool_use = emit_tool_use
        self.request: dict | None = None

    def create(self, **kwargs):
        self.request = kwargs
        content = []
        if self._emit_tool_use:
            content.append(
                SimpleNamespace(type="tool_use", name=TOOL_NAME, input=self._tool_input)
            )
        return SimpleNamespace(content=content, stop_reason=self._stop_reason)


class _FakeClient:
    def __init__(self, tool_input, **kwargs) -> None:
        self.messages = _FakeMessages(tool_input, **kwargs)


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
    assert DEFAULT_BEDROCK_MODEL_ID.startswith("anthropic.")  # Bedrock IDs are prefixed


def test_development_default_is_the_verified_low_cost_model():
    """Sonnet 5 passed forced-tool use; Sonnet 4.6 returned 404 on this endpoint."""
    assert DEFAULT_BEDROCK_MODEL_ID == "anthropic.claude-sonnet-5"


def test_tool_schema_matches_the_wire_model():
    """Guards against the schema and the Pydantic model drifting apart."""
    assert ASSESSMENT_TOOL["input_schema"]["required"] == list(BedrockAssessmentOutput.model_fields)
    assert ASSESSMENT_TOOL["input_schema"]["additionalProperties"] is False
    # Bedrock rejects `strict`; numeric bounds are enforced client-side, not on the wire.
    assert "strict" not in ASSESSMENT_TOOL
    conf = ASSESSMENT_TOOL["input_schema"]["properties"]["decision_confidence"]
    assert "minimum" not in conf and "maximum" not in conf


def test_bedrock_assessor_forces_the_tool_and_preserves_contract():
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
    assert request["tools"] == [ASSESSMENT_TOOL]
    assert request["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    # Sampling params are rejected (400) by current Claude models — never send them.
    assert "temperature" not in request
    assert "top_p" not in request
    # Constrained decoding is unavailable on this surface; we must not send it.
    assert "output_config" not in request


def test_language_boundary_is_narrative_only():
    """The model sees narrative evidence — never an ID it could overfit, never the OOS data."""
    client = _FakeClient(_wire_output())
    BedrockAssessor(client=client).assess(REPORT)
    content = client.messages.request["messages"][0]["content"]

    payload = json.loads(content)
    assert set(payload) == {"damage_description", "incident_context", "reporter_confidence"}
    for leak in ("report_id", "DMG-2026-0005", "roadability_data", "frame_crack", "DCLZ"):
        assert leak not in content


def test_final_domain_model_enforces_confidence_bound():
    client = _FakeClient(_wire_output(decision_confidence=1.5))
    with pytest.raises(ValueError, match="Assessment contract"):
        BedrockAssessor(client=client).assess(REPORT)


def test_unknown_field_from_model_is_rejected():
    client = _FakeClient(_wire_output(sneaky_extra="nope"))
    with pytest.raises(ValueError, match="Assessment contract"):
        BedrockAssessor(client=client).assess(REPORT)


def test_missing_tool_use_block_is_a_clear_error():
    client = _FakeClient(None, emit_tool_use=False, stop_reason="end_turn")
    with pytest.raises(RuntimeError, match="no tool_use"):
        BedrockAssessor(client=client).assess(REPORT)


def test_refusal_is_a_clear_error():
    client = _FakeClient(None, emit_tool_use=False, stop_reason="refusal")
    with pytest.raises(RuntimeError, match="refused"):
        BedrockAssessor(client=client).assess(REPORT)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_BEDROCK_INTEGRATION") != "1",
    reason="set RUN_BEDROCK_INTEGRATION=1 with valid AWS credentials to call Bedrock",
)
def test_live_bedrock_marks_end_of_life_case_for_review():
    """#0012 is the one case with no deterministic backstop — it rides entirely on the model."""
    assessment = BedrockAssessor().assess(load_reports_by_id()["DMG-2026-0012"])
    assert isinstance(assessment, Assessment)
    assert assessment.end_of_life_suspected is True
    assert 0.0 <= assessment.decision_confidence <= 1.0
