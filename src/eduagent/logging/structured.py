"""Structured logging using unified event schema."""
from __future__ import annotations

import logging
from typing import Any

from ..models.events import RuntimeEvent

logger = logging.getLogger("eduagent")


def log_event(event: RuntimeEvent):
    logger.info(
        "[%s] %s agent=%s round=%d step=%s",
        event.event_type.value,
        event.run_id[:8],
        event.agent_id or "-",
        event.round_number,
        event.step_in_turn if event.step_in_turn is not None else "-",
    )
