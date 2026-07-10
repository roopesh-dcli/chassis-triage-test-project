
from __future__ import annotations

import os

REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
MODELS = ["anthropic.claude-opus-4-8", "anthropic.claude-sonnet-5"]

SYSTEM = "Extract a severity band and a confidence between 0 and 1 from the narrative."
PROMPT = "Narrative: Right-rear tire is flat with exposed cords. Reporter confidence: high."

SCHEMA = {
    "type": "object",
    "properties": {
        "severity_band": {"type": "string", "enum": ["minor", "moderate", "severe", "total_loss"]},
        "decision_confidence": {"type": "number"},
    },
    "required": ["severity_band", "decision_confidence"],
    "additionalProperties": False,
}

TOOL = {
    "name": "record_assessment",
    "description": "Record the assessment extracted from the narrative.",
    "input_schema": SCHEMA,
}


def main() -> None:
    from anthropic import AnthropicBedrockMantle

    client = AnthropicBedrockMantle(aws_region=REGION)
    base = dict(max_tokens=512, system=SYSTEM, messages=[{"role": "user", "content": PROMPT}])

    for model in MODELS:
        print(f"=========== {model}")

        # A. FULL error text for output_config.format
        print("\n[A] create + output_config.format")
        try:
            r = client.messages.create(
                model=model,
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
                **base,
            )
            print("    PASS:", next(b.text for b in r.content if b.type == "text")[:80])
        except Exception as e:  # noqa: BLE001
            print(f"    FAIL {type(e).__name__}")
            print(f"    FULL: {e}")

        # B. forced tool use  <-- the portable fallback
        print("\n[B] create + forced tool_choice (tool use)")
        try:
            r = client.messages.create(
                model=model,
                tools=[TOOL],
                tool_choice={"type": "tool", "name": "record_assessment"},
                **base,
            )
            blocks = [b for b in r.content if getattr(b, "type", None) == "tool_use"]
            if blocks:
                print(f"    PASS stop_reason={r.stop_reason} input={blocks[0].input}")
            else:
                print(f"    NO tool_use block; stop_reason={r.stop_reason}")
                print("    content types:", [getattr(b, 'type', '?') for b in r.content])
        except Exception as e:  # noqa: BLE001
            print(f"    FAIL {type(e).__name__}")
            print(f"    FULL: {e}")

        # C. forced tool use + strict (structured-output flavoured tool use)
        print("\n[C] create + forced tool_choice + strict=True")
        try:
            strict_tool = {**TOOL, "strict": True}
            r = client.messages.create(
                model=model,
                tools=[strict_tool],
                tool_choice={"type": "tool", "name": "record_assessment"},
                **base,
            )
            blocks = [b for b in r.content if getattr(b, "type", None) == "tool_use"]
            print(f"    PASS input={blocks[0].input}" if blocks else "    NO tool_use block")
        except Exception as e:  # noqa: BLE001
            print(f"    FAIL {type(e).__name__}")
            print(f"    FULL: {e}")

        print()


if __name__ == "__main__":
    main()
