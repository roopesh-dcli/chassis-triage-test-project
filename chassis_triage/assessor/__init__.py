"""Damage Assessor factory — selects the implementation from LLM_MODE."""
from __future__ import annotations

import os

from .base import Assessor
from .stub import StubAssessor

__all__ = ["Assessor", "StubAssessor", "get_assessor"]


def get_assessor(mode: str | None = None) -> Assessor:
    """Return the configured assessor. Defaults to the deterministic stub."""
    mode = (mode or os.getenv("LLM_MODE", "stub")).lower()
    if mode == "stub":
        return StubAssessor()
    if mode == "bedrock":
        try:
            from .bedrock import BedrockAssessor
        except ImportError as e:
            raise NotImplementedError(
                "Bedrock assessor is added in step 6; run with LLM_MODE=stub for now."
            ) from e
        return BedrockAssessor()
    raise ValueError(f"unknown LLM_MODE: {mode!r} (expected 'stub' or 'bedrock')")
