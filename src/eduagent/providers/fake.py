"""Fake provider for testing with pre-recorded scripts."""
from __future__ import annotations

import json
import re
from collections import deque

from .base import ModelProvider, ProviderResponse


class FakeProvider(ModelProvider):
    def __init__(self, responses: list[str] | None = None):
        self._responses: deque[str] = deque(responses or [])

    def add_response(self, content: str):
        self._responses.append(content)

    def add_responses(self, contents: list[str]):
        self._responses.extend(contents)

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "fake",
        response_format: dict | None = None,
    ) -> ProviderResponse:
        if not self._responses:
            return ProviderResponse(content='{"action_type":"final_answer","payload":{"content":"No more scripted responses"}}')
        content = self._responses.popleft()

        # Replace __PENDING__ with actual artifact IDs from conversation context
        if "__PENDING__" in content:
            artifact_id = self._extract_pending_artifact_id(messages)
            if artifact_id:
                content = content.replace("__PENDING__", artifact_id)

        return ProviderResponse(content=content)

    def _extract_pending_artifact_id(self, messages: list[dict[str, str]]) -> str | None:
        """Extract the most recent artifact_id from conversation messages."""
        for msg in reversed(messages):
            text = msg.get("content", "")
            # Look for artifact_id in JSON-like patterns
            match = re.search(r'"artifact_id"\s*:\s*"([a-f0-9]+)"', text)
            if match:
                return match.group(1)
            # Look for artifact IDs in list format: ['abc123'] or Pending artifacts: ['abc123']
            match = re.search(r"'([a-f0-9]{8,12})'", text)
            if match:
                return match.group(1)
            # Look for artifact_id= or id= patterns
            match = re.search(r'(?:artifact[_ ]?id|id)[ =:]+([a-f0-9]{8,12})', text)
            if match:
                return match.group(1)
            # Look for (id=xxx) pattern used in reviewer prompts
            match = re.search(r'\(id=([a-f0-9]{8,12})\)', text)
            if match:
                return match.group(1)
        return None
