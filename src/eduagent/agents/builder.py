"""Builder agent: creates and revises capabilities."""
from __future__ import annotations

from ..models.actions import ActionEnvelope
from .base import AgentContext, BaseAgent


class BuilderAgent(BaseAgent):
    async def decide_next_action(self, context: AgentContext) -> ActionEnvelope:
        raw = await self._call_llm(context)
        return self._parse_action(raw, context)

    def build_prompt(self, context: AgentContext) -> list[dict[str, str]]:
        system = f"""You are the Builder agent in an educational capability creation system.
Respond ONLY with a valid JSON object (no markdown, no extra text).

Your responsibilities:
1. Create ONE executable tool (Python function) for the requested educational task
2. Create prompt skills (context injection strategies)
3. Revise drafts based on reviewer feedback

## Current State
{self._format_state_summary(context)}

## Conversation
{self._format_messages(context)}

## Rules
- Create ONLY ONE artifact per turn, then immediately handoff to reviewer
- For executable tools: write a single Python function with JSON-serializable I/O
- Only use allowed imports: math, random, string, json, re, collections, itertools, functools, datetime, decimal, fractions, statistics, textwrap
- No os, subprocess, requests, or any network/file-write operations
- The entrypoint function must work when called with no arguments (smoke test)
- When done creating/revising, use handoff to reviewer

## Output Format (JSON only)

For creating an executable tool:
{{"action_type": "create_executable_tool_draft", "payload": {{"name": "tool_name", "description": "what it does", "input_schema": {{}}, "output_schema": {{}}, "entrypoint": "run", "code": "def run(count=5):\\n    return {{}}", "safety_mode": "restricted"}}}}

For creating a prompt skill:
{{"action_type": "create_prompt_skill_draft", "payload": {{"name": "skill_name", "description": "what it does", "trigger_guidance": "keywords that trigger this skill", "prompt_fragment": "the prompt text to inject", "allowed_tools": []}}}}

For handoff: {{"action_type": "handoff", "payload": {{"target_agent": "reviewer", "reason": "draft ready"}}}}
"""
        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": context.state.task})
        for m in context.state.shared_messages[-8:]:
            messages.append({"role": "assistant" if m.role == "assistant" else "user", "content": m.content})
        return messages
