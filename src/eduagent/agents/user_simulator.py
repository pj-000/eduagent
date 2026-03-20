"""User simulator agent: evaluates from adoption and educational perspective."""
from __future__ import annotations

from ..models.actions import ActionEnvelope
from .base import AgentContext, BaseAgent


class UserSimulatorAgent(BaseAgent):
    async def decide_next_action(self, context: AgentContext) -> ActionEnvelope:
        raw = await self._call_llm(context)
        return self._parse_action(raw, context)

    def build_prompt(self, context: AgentContext) -> list[dict[str, str]]:
        # Find the most recently created draft artifact to review
        draft_artifacts = [
            a for a in context.available_artifacts
            if a.get("status") == "draft"
        ]
        draft_artifacts.sort(key=lambda a: a.get("created_at", ""), reverse=True)

        target_id = draft_artifacts[0].get("artifact_id", "__UNKNOWN__") if draft_artifacts else "__UNKNOWN__"

        artifacts_info = ""
        for a in draft_artifacts[:1]:
            artifacts_info += f"\nArtifact ID: {a.get('artifact_id')}\n"
            artifacts_info += f"Kind: {a.get('kind')}\n"
            artifacts_info += f"Name: {a.get('name')}\n"
            artifacts_info += f"Description: {a.get('description')}\n"
            if a.get("prompt_fragment"):
                artifacts_info += f"Prompt fragment: {a.get('prompt_fragment')}\n"

        system = f"""You are the User Simulator agent. You evaluate artifacts as a teacher or student.
Respond ONLY with a valid JSON object (no markdown, no extra text).

## Pending Artifacts to Review
{artifacts_info if artifacts_info else "No pending artifacts."}

## Scoring Criteria
- usability (0.0-1.0): Is it easy to use?
- educational_value (0.0-1.0): Does it help learning?
- age_appropriateness (0.0-1.0): Is it suitable for the target age?

## Output Format (JSON only)

{{"action_type": "submit_review", "payload": {{"artifact_id": "{target_id}", "approve": true, "scores": {{"usability": 0.9, "educational_value": 0.85, "age_appropriateness": 0.9}}, "rationale": "explanation here", "required_revisions": []}}}}
"""
        messages = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": f"Please review artifact {target_id} from a user perspective and respond with a JSON review."})
        return messages
