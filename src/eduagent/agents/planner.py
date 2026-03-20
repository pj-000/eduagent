"""Planner agent: task decomposition, gap identification, final integration."""
from __future__ import annotations

from ..models.actions import ActionEnvelope, ActionType
from .base import AgentContext, BaseAgent


class PlannerAgent(BaseAgent):
    async def decide_next_action(self, context: AgentContext) -> ActionEnvelope:
        raw = await self._call_llm(context)
        return self._parse_action(raw, context)

    def build_prompt(self, context: AgentContext) -> list[dict[str, str]]:
        skill_section = ""
        if context.injected_skill:
            skill_section = f"""
## Injected Skill
Name: {context.injected_skill.get('name', '')}
Guidance: {context.injected_skill.get('prompt_fragment', '')}
Allowed tools: {context.injected_skill.get('allowed_tools', [])}
"""

        # Summarize pending artifacts that have been approved — exclude already-active ones
        pending_approved = []
        for r in context.state.result_history[-10:]:
            if r.action_type == "submit_review" and r.success:
                output = r.output or {}
                if output.get("approve") and output.get("artifact_id"):
                    aid = output["artifact_id"]
                    if (aid in context.state.pending_artifact_ids
                            and aid not in context.state.active_artifact_ids):
                        pending_approved.append(aid)
        # Deduplicate
        pending_approved = list(dict.fromkeys(pending_approved))

        activation_hint = ""
        if pending_approved:
            activation_hint = f"""
## PENDING ACTIVATION
The following artifacts have been approved by both reviewer and user_simulator and are ready to activate:
{pending_approved}
You MUST call activate_artifact for each one before using them or producing final_answer.
"""

        system = f"""You are the Planner agent in an educational capability creation system.
Respond ONLY with a valid JSON object (no markdown, no extra text).

Your responsibilities:
1. Analyze the task and identify what tools or skills are needed
2. If a needed tool/skill doesn't exist, handoff to builder
3. If artifacts are pending activation (approved by both reviewers), activate them first
4. Call available tools to accomplish the task
5. Produce final_answer with the complete result

## Current State
{self._format_state_summary(context)}

## Available Tools
{self._format_available_tools(context)}
{skill_section}{activation_hint}
## Decision Rules (follow in order)
1. If there are approved artifacts pending activation → use activate_artifact ONCE, then stop
2. If a needed tool doesn't exist → handoff to builder
3. If tools are available → call_tool to get the result
4. If call_tool fails → try different arguments, do NOT re-activate
5. Once you have the tool result → immediately output final_answer
6. Do NOT activate the same artifact twice
7. Do NOT call the same tool twice with the same arguments

## Output Format (JSON only)

For activate_artifact: {{"action_type": "activate_artifact", "payload": {{"artifact_id": "..."}}}}
For handoff: {{"action_type": "handoff", "payload": {{"target_agent": "builder", "reason": "..."}}}}
For call_tool: {{"action_type": "call_tool", "payload": {{"tool_name": "...", "arguments": {{...}}}}}}
For final_answer: {{"action_type": "final_answer", "payload": {{"content": "...", "artifact_ids": [...]}}}}
For send_message: {{"action_type": "send_message", "payload": {{"content": "..."}}}}
"""

        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": context.state.task})
        for m in context.state.shared_messages[-10:]:
            messages.append({
                "role": "assistant" if m.role == "assistant" else "user",
                "content": m.content,
            })
        return messages
