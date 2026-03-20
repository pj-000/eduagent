"""DashScope provider using OpenAI-compatible API."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .base import ModelProvider, ProviderResponse


class DashScopeProvider(ModelProvider):
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        load_dotenv()
        self._client = AsyncOpenAI(
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY", ""),
            base_url=base_url or os.getenv("DASHSCOPE_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1"),
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "qwen-plus",
        response_format: dict | None = None,
    ) -> ProviderResponse:
        # Some models (glm-5, kimi) require the word "json" in messages
        # when using response_format=json_object. Inject it into system prompt.
        if response_format and response_format.get("type") == "json_object":
            messages = self._ensure_json_keyword(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if response_format:
            kwargs["response_format"] = response_format

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        content = choice.message.content or ""

        # Extract JSON from markdown code blocks if present
        content = self._extract_json(content)

        return ProviderResponse(
            content=content,
            raw=resp.model_dump() if resp else None,
            usage=(
                {
                    "prompt_tokens": resp.usage.prompt_tokens,
                    "completion_tokens": resp.usage.completion_tokens,
                }
                if resp.usage
                else None
            ),
        )

    def _ensure_json_keyword(self, messages: list[dict]) -> list[dict]:
        """Ensure at least one message contains 'json' (required by some models)."""
        combined = " ".join(m.get("content", "") for m in messages).lower()
        if "json" in combined:
            return messages
        # Append json reminder to the last system message, or first message
        messages = [dict(m) for m in messages]
        for m in messages:
            if m.get("role") == "system":
                m["content"] = m["content"] + "\n\nRespond with a valid JSON object."
                return messages
        messages[0]["content"] = messages[0]["content"] + "\n\nRespond with a valid JSON object."
        return messages

    def _extract_json(self, content: str) -> str:
        """Extract JSON from markdown code blocks or raw text."""
        content = content.strip()
        # Strip ```json ... ``` or ``` ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        # If it already starts with {, return as-is
        if content.startswith("{"):
            return content
        # Try to find first { ... } block
        match = re.search(r"(\{.*\})", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content
