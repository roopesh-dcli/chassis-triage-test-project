"""Small structured-event seam for local logs and future CloudWatch ingestion."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

LOGGER = logging.getLogger("chassis_triage.events")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False


def emit_event(event: str, **fields: Any) -> None:
    """Write one JSON event without coupling triage code to a log vendor."""
    payload = {"event": event, "ts": datetime.now(UTC).isoformat(), **fields}
    LOGGER.info("%s", json.dumps(payload, default=str, separators=(",", ":")))
