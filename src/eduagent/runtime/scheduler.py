"""Scheduler: baton-style agent selection."""
from __future__ import annotations

from ..agents.base import BaseAgent
from ..models.actions import ActionType
from ..models.agent_profile import AgentRole
from ..models.conversation import ConversationState
from ..models.results import ActionResult


class Scheduler:
    def __init__(self, agents: dict[str, BaseAgent], max_rounds: int = 20):
        self._agents = agents
        self._max_rounds = max_rounds

    def select_next_agent(self, state: ConversationState) -> BaseAgent | None:
        """Select next agent based on state and last result."""
        # Initial state -> planner
        if state.current_agent_id is None:
            return self._agents.get("planner")

        last = state.last_action_result
        if last is None:
            return self._agents.get("planner")

        # If current agent had consecutive failures (parse errors), cut back to planner
        if self._current_agent_stuck(state):
            return self._agents.get("planner")

        # Respect explicit suggested_next_agent if valid
        if last.suggested_next_agent and last.suggested_next_agent in self._agents:
            return self._agents[last.suggested_next_agent]

        current_role = self._get_role(state.current_agent_id)

        # Handoff action -> follow the target
        if last.action_type == ActionType.HANDOFF.value:
            target = None
            if isinstance(last.output, dict):
                target = last.output.get("target_agent")
            if target and target in self._agents:
                return self._agents[target]

        # Draft created -> reviewer
        if last.action_type in (
            ActionType.CREATE_EXECUTABLE_TOOL_DRAFT.value,
            ActionType.CREATE_PROMPT_SKILL_DRAFT.value,
        ):
            return self._agents.get("reviewer")

        # Review submitted
        if last.action_type == ActionType.SUBMIT_REVIEW.value:
            approved = isinstance(last.output, dict) and last.output.get("approve")
            if current_role == AgentRole.REVIEWER:
                if approved:
                    return self._agents.get("user_simulator")
                else:
                    return self._agents.get("builder")
            elif current_role == AgentRole.USER_SIMULATOR:
                if approved:
                    return self._agents.get("planner")
                else:
                    return self._agents.get("builder")

        # Activation -> planner
        if last.action_type == ActionType.ACTIVATE_ARTIFACT.value:
            return self._agents.get("planner")

        # Rejection -> planner
        if last.action_type == ActionType.REJECT_ARTIFACT.value:
            return self._agents.get("planner")

        # Tool call failure -> planner to reassess
        if not last.success:
            return self._agents.get("planner")

        # Default -> planner
        return self._agents.get("planner")

    def should_terminate(self, state: ConversationState) -> bool:
        if state.terminated:
            return True
        if state.final_answer is not None:
            return True
        if state.round_number >= self._max_rounds:
            return True
        # All pending rejected with no revision room
        if self._all_rejected_no_revision(state):
            return True
        return False

    def _current_agent_stuck(self, state: ConversationState) -> bool:
        """Check if the current agent produced only errors in its last turn."""
        if not state.current_agent_id:
            return False
        # Look at the last N results from the current agent
        agent_results = [
            r for r in state.result_history[-6:]
            if r.agent_id == state.current_agent_id
        ]
        if len(agent_results) >= 2 and all(not r.success for r in agent_results[-2:]):
            return True
        return False

    def _all_rejected_no_revision(self, state: ConversationState) -> bool:
        """Check if all artifacts are rejected with >= 2 revisions."""
        if not state.artifact_ids:
            return False
        # Check result history for reject patterns
        reject_counts: dict[str, int] = {}
        for r in state.result_history:
            if r.action_type == ActionType.REJECT_ARTIFACT.value and r.success:
                for aid in r.artifacts_changed:
                    reject_counts[aid] = reject_counts.get(aid, 0) + 1
        if not reject_counts:
            return False
        # If any artifact has been rejected >= 2 times and there are no active ones
        if not state.active_artifact_ids and all(
            c >= 2 for c in reject_counts.values()
        ):
            return True
        return False

    def _get_role(self, agent_id: str) -> AgentRole | None:
        agent = self._agents.get(agent_id)
        if agent:
            return agent.profile.role
        return None
