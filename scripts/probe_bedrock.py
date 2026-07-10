from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict

REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

MODELS = [
    "anthropic.claude-opus-4-8",
    "anthropic.claude-sonnet-5",
    "anthropic.claude-sonnet-4-6",
]

PROMPT = "Narrative: Right-rear tire is flat with exposed cords. Reporter confidence: high."
SYSTEM = "Extract a severity band and a confidence between 0 and 1."


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity_band: str
    decision_confidence: float


SCHEMA = {
    "type": "object",
    "properties": {
        "severity_band": {"type": "string", "enum": ["minor", "moderate", "severe", "total_loss"]},
        "decision_confidence": {"type": "number"},
    },
    "required": ["severity_band", "decision_confidence"],
    "additionalProperties": False,
}


def short(e: Exception, n: int = 130) -> str:
    msg = str(e).replace("\n", " ")
    return f"{type(e).__name__}: {msg[:n]}"


def main() -> None:
    import anthropic
    from anthropic import AnthropicBedrockMantle
    from anthropic.resources.messages import Messages

    print(f"anthropic       : {anthropic.__version__}")
    print(f"region          : {REGION}")
    print(f"Messages.parse  : {hasattr(Messages, 'parse')}")
    print()

    client = AnthropicBedrockMantle(aws_region=REGION)
    print(f"client.messages.parse present: {hasattr(client.messages, 'parse')}\n")

    base = dict(max_tokens=256, system=SYSTEM, messages=[{"role": "user", "content": PROMPT}])

    for model in MODELS:
        print(f"--- {model}")

        # 1. baseline invoke
        try:
            client.messages.create(model=model, **base)
            print("   [1] plain create                 : PASS")
        except Exception as e:  # noqa: BLE001
            print(f"   [1] plain create                 : FAIL  {short(e)}")
            print("       (model not invokable here; skipping rest)\n")
            continue

        # 2. structured output via output_config.format
        try:
            r = client.messages.create(
                model=model,
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
                **base,
            )
            txt = next(b.text for b in r.content if b.type == "text")
            print(f"   [2] create + output_config.format: PASS  {txt[:60]}")
        except Exception as e:  # noqa: BLE001
            print(f"   [2] create + output_config.format: FAIL  {short(e)}")

        # 3. structured output via the SDK's messages.parse helper
        try:
            r = client.messages.parse(model=model, output_format=Wire, **base)
            print(f"   [3] messages.parse(output_format): PASS  {r.parsed_output}")
        except Exception as e:  # noqa: BLE001
            print(f"   [3] messages.parse(output_format): FAIL  {short(e)}")

        # 4. does this model accept temperature?
        try:
            client.messages.create(model=model, temperature=0, **base)
            print("   [4] temperature=0                : PASS (accepted)")
        except Exception as e:  # noqa: BLE001
            print(f"   [4] temperature=0                : FAIL  {short(e)}")

        print()


if __name__ == "__main__":
    main()
