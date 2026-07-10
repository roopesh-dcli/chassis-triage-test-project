from __future__ import annotations

import os
import sys

REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
# Sonnet 5 is the verified development model for this account's Mantle endpoint.
# Set BEDROCK_MODEL_ID to anthropic.claude-opus-4-8 for a final validation run.
MODEL = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-5")

print(f"region : {REGION}")
print(f"model  : {MODEL}")

# --- 1. who am I? (no secrets printed) ---
try:
    import boto3

    ident = boto3.client("sts", region_name=REGION).get_caller_identity()
    print(f"account: {ident['Account']}")
    print(f"arn    : {ident['Arn']}")
except Exception as e:  # noqa: BLE001
    print(f"\nSTS failed ({type(e).__name__}): {e}")
    print("-> credentials are not set, or have expired. Re-export them and retry.")
    sys.exit(1)

# --- 2. which Anthropic models does this account see here? ---
try:
    bedrock = boto3.client("bedrock", region_name=REGION)
    models = bedrock.list_foundation_models(byProvider="anthropic")["modelSummaries"]
    print(f"\nanthropic foundation models visible ({len(models)}):")
    for m in models:
        print(f"   {m['modelId']:<55} {m.get('inferenceTypesSupported')}")
except Exception as e:  # noqa: BLE001
    print(f"\nlist_foundation_models failed ({type(e).__name__}): {e}")

try:
    profiles = boto3.client("bedrock", region_name=REGION).list_inference_profiles()
    ids = [p["inferenceProfileId"] for p in profiles["inferenceProfileSummaries"]]
    anthropic_ids = [i for i in ids if "anthropic" in i]
    print(f"\ninference profiles mentioning anthropic ({len(anthropic_ids)}):")
    for i in anthropic_ids[:25]:
        print(f"   {i}")
except Exception as e:  # noqa: BLE001
    print(f"\nlist_inference_profiles failed ({type(e).__name__}): {e}")

# --- 3. the only test that matters: can we actually invoke? ---
print(f"\nsmoke test -> {MODEL}")
try:
    from anthropic import AnthropicBedrockMantle

    client = AnthropicBedrockMantle(aws_region=REGION)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    print(f"   SUCCESS (Mantle client) -> {text!r}")
except Exception as e:  # noqa: BLE001
    print(f"   Mantle client failed ({type(e).__name__}): {e}")
    print("   -> paste this error back; it tells us whether it's IAM, region, model access,")
    print("      or that this account needs the legacy bedrock-runtime path instead.")
