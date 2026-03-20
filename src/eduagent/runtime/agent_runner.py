"""AgentRunner: drives single agent multi-step loop."""
from __future__ import annotations

from typing import Any

from ..agents.base import AgentContext, BaseAgent
from ..logging.event_sink import EventSink
from ..models.actions import ActionEnvelope, ActionType
from ..models.artifacts import ArtifactStatus
from ..models.conversation import ConversationState, Message
from ..models.events import EventType, RuntimeEvent
from ..models.results import ActionResult
from ..registry.artifact_registry import ArtifactRegistry
from .executor import ActionExecutor


class AgentRunner:
    def __init__(
        self,
        executor: ActionExecutor,
        event_sink: EventSink,
        registry: ArtifactRegistry,
    ):
        self.executor = executor
        self.event_sink = event_sink
        self.registry = registry

    async def run_agent_turn(
        self,
        agent: BaseAgent,
        state: ConversationState,
    ) -> list[ActionResult]:
        await self.event_sink.emit(RuntimeEvent(
            event_type=EventType.AGENT_TURN_STARTED,
            run_id=state.run_id,
            round_number=state.round_number,
            agent_id=agent.profile.agent_id,
            agent_role=agent.profile.role,
            payload={},
        ))

        results: list[ActionResult] = []
        consecutive_failures = 0
        skill_emitted = False

        for step in range(agent.profile.max_actions_per_turn):
            context = await self._build_context(agent, state, results)

            # Emit SKILL_INJECTED event once per turn
            if not skill_emitted and context.injected_skill:
                await self.event_sink.emit(RuntimeEvent(
                    event_type=EventType.SKILL_INJECTED,
                    run_id=state.run_id,
                    round_number=state.round_number,
                    agent_id=agent.profile.agent_id,
                    agent_role=agent.profile.role,
                    step_in_turn=step,
                    payload={
                        "skill_id": context.injected_skill.get("skill_id", ""),
                        "skill_name": context.injected_skill.get("name", ""),
                        "trigger_reason": "keyword_match",
                    },
                ))
                skill_emitted = True

            try:
                action = await agent.decide_next_action(context)
            except Exception as e:
                # LLM parse failure — emit and break
                error_result = ActionResult(
                    action_id="parse_error",
                    agent_id=agent.profile.agent_id,
                    action_type="error",
                    success=False,
                    error=f"Failed to parse agent output: {e}",
                )
                results.append(error_result)
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    break
                continue

            # Build action_created payload with key details
            action_payload: dict = {"action_type": action.action_type.value}
            if action.action_type.value == "call_tool":
                action_payload["tool_name"] = action.payload.tool_name
                action_payload["arguments"] = action.payload.arguments
            elif action.action_type.value in ("create_executable_tool_draft", "create_prompt_skill_draft"):
                action_payload["name"] = action.payload.name
                action_payload["description"] = action.payload.description
                if hasattr(action.payload, "code"):
                    action_payload["code_preview"] = action.payload.code[:300]
                if hasattr(action.payload, "prompt_fragment"):
                    action_payload["prompt_fragment"] = action.payload.prompt_fragment
            elif action.action_type.value == "handoff":
                action_payload["target_agent"] = action.payload.target_agent
                action_payload["reason"] = action.payload.reason
            elif action.action_type.value == "final_answer":
                action_payload["content"] = action.payload.content
            elif action.action_type.value == "activate_artifact":
                action_payload["artifact_id"] = action.payload.artifact_id
            elif action.action_type.value == "send_message":
                action_payload["content"] = action.payload.content

            await self.event_sink.emit(RuntimeEvent(
                event_type=EventType.ACTION_CREATED,
                run_id=state.run_id,
                round_number=state.round_number,
                agent_id=agent.profile.agent_id,
                agent_role=agent.profile.role,
                step_in_turn=step,
                related_action_id=action.action_id,
                payload=action_payload,
            ))

            result = await self.executor.execute(action)

            # Build action_result payload with output
            import json as _json
            result_payload: dict = {
                "success": result.success,
                "error": result.error,
                "action_type": result.action_type,
            }
            if result.success and result.output is not None:
                try:
                    # Serialize output, truncate if too large
                    out_str = _json.dumps(result.output, ensure_ascii=False, default=str)
                    result_payload["output"] = _json.loads(out_str[:2000])
                except Exception:
                    result_payload["output"] = str(result.output)[:500]

            await self.event_sink.emit(RuntimeEvent(
                event_type=EventType.ACTION_RESULT,
                run_id=state.run_id,
                round_number=state.round_number,
                agent_id=agent.profile.agent_id,
                agent_role=agent.profile.role,
                step_in_turn=step,
                related_action_id=action.action_id,
                payload=result_payload,
            ))

            results.append(result)
            self._update_state(state, action, result)

            # Emit artifact events
            for aid in result.artifacts_changed:
                art = await self.registry.get_artifact(aid)
                if art:
                    evt_type = EventType.ARTIFACT_CREATED if art.revision == 0 else EventType.ARTIFACT_UPDATED
                    await self.event_sink.emit(RuntimeEvent(
                        event_type=evt_type,
                        run_id=state.run_id,
                        round_number=state.round_number,
                        agent_id=agent.profile.agent_id,
                        agent_role=agent.profile.role,
                        step_in_turn=step,
                        payload={"artifact_id": aid, "artifact_summary": {"name": art.name, "status": art.status.value}},
                    ))

            # Emit evaluation event for submit_review
            if action.action_type == ActionType.SUBMIT_REVIEW and result.success:
                await self.event_sink.emit(RuntimeEvent(
                    event_type=EventType.EVALUATION_COMPLETED,
                    run_id=state.run_id,
                    round_number=state.round_number,
                    agent_id=agent.profile.agent_id,
                    agent_role=agent.profile.role,
                    step_in_turn=step,
                    payload={"evaluation_card": result.output},
                ))

            if self._should_end_turn(action, result, consecutive_failures):
                # Emit handoff event if applicable
                if action.action_type == ActionType.HANDOFF:
                    await self.event_sink.emit(RuntimeEvent(
                        event_type=EventType.AGENT_HANDOFF,
                        run_id=state.run_id,
                        round_number=state.round_number,
                        agent_id=agent.profile.agent_id,
                        agent_role=agent.profile.role,
                        step_in_turn=step,
                        payload={
                            "from_agent": agent.profile.agent_id,
                            "to_agent": result.suggested_next_agent or "",
                            "reason": result.output.get("reason", "") if isinstance(result.output, dict) else "",
                        },
                    ))
                break

            consecutive_failures = 0 if result.success else consecutive_failures + 1

        await self.event_sink.emit(RuntimeEvent(
            event_type=EventType.AGENT_TURN_ENDED,
            run_id=state.run_id,
            round_number=state.round_number,
            agent_id=agent.profile.agent_id,
            agent_role=agent.profile.role,
            payload={"actions_taken": len(results), "yield_reason": "turn_complete"},
        ))

        return results

    async def _build_context(
        self,
        agent: BaseAgent,
        state: ConversationState,
        recent_results: list[ActionResult],
    ) -> AgentContext:
        # Gather artifact info
        available = []
        for aid in state.artifact_ids:
            art = await self.registry.get_artifact(aid)
            if art:
                info = art.model_dump()
                # Load code for executable tools
                from ..models.artifacts import ExecutableToolSpec
                if isinstance(art, ExecutableToolSpec) and art.code_path:
                    from pathlib import Path
                    cp = Path(art.code_path)
                    if cp.exists():
                        info["code"] = cp.read_text()
                available.append(info)

        # Active tools for planner — include code signature so planner knows correct args
        active_tools = []
        for t in await self.registry.list_active_tools():
            tool_info: dict = {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            # Extract function signature from code for accurate arg names
            if t.code_path:
                from pathlib import Path as _Path
                import ast as _ast
                cp = _Path(t.code_path)
                if cp.exists():
                    try:
                        code = cp.read_text()
                        tree = _ast.parse(code)
                        for node in _ast.walk(tree):
                            if isinstance(node, _ast.FunctionDef) and node.name == t.entrypoint:
                                args = []
                                defaults_offset = len(node.args.args) - len(node.args.defaults)
                                for i, arg in enumerate(node.args.args):
                                    if arg.arg == "self":
                                        continue
                                    di = i - defaults_offset
                                    if di >= 0 and di < len(node.args.defaults):
                                        d = node.args.defaults[di]
                                        default = _ast.literal_eval(d) if isinstance(d, _ast.Constant) else "..."
                                        args.append(f"{arg.arg}={repr(default)}")
                                    else:
                                        args.append(arg.arg)
                                tool_info["signature"] = f"{t.entrypoint}({', '.join(args)})"
                                break
                    except Exception:
                        pass
            active_tools.append(tool_info)

        # Add builtin tools with their signatures
        for name, func in self.executor.builtin_tools.items():
            import inspect as _inspect
            try:
                sig = str(_inspect.signature(func))
            except Exception:
                sig = "()"
            desc = (func.__doc__ or "").split("\n")[0].strip() if callable(func) else str(name)
            active_tools.append({"name": name, "description": desc, "signature": f"{name}{sig}"})

        # Skill injection
        injected_skill = await self._select_skill(state)

        return AgentContext(
            state=state,
            available_artifacts=available,
            recent_results=recent_results[-5:],
            injected_skill=injected_skill,
            active_tools=active_tools,
        )

    async def _select_skill(self, state: ConversationState) -> dict | None:
        """Deterministic skill selection (no LLM)."""
        active_skills = await self.registry.list_active_skills()
        if not active_skills:
            return None

        # Build text to match against
        match_text = state.task.lower()
        for m in state.shared_messages[-3:]:
            match_text += " " + m.content.lower()

        # Score each skill
        scored = []
        for skill in active_skills:
            trigger_words = set(skill.trigger_guidance.lower().split())
            text_words = set(match_text.split())
            score = len(trigger_words & text_words)

            # Failure weighting
            if state.last_action_result and not state.last_action_result.success:
                err_text = (state.last_action_result.error or "").lower()
                err_words = set(err_text.split())
                score += len(trigger_words & err_words)

            scored.append((score, skill.created_at, skill))

        # Sort by score desc, then created_at asc for stability
        scored.sort(key=lambda x: (-x[0], x[1]))

        if scored and scored[0][0] > 0:
            skill = scored[0][2]
            return {
                "skill_id": skill.artifact_id,
                "name": skill.name,
                "prompt_fragment": skill.prompt_fragment,
                "allowed_tools": skill.allowed_tools,
            }
        return None

    def _update_state(
        self,
        state: ConversationState,
        action: ActionEnvelope,
        result: ActionResult,
    ):
        state.action_history.append(action)
        state.result_history.append(result)
        state.last_action_result = result

        # Track artifacts
        for aid in result.artifacts_changed:
            if aid not in state.artifact_ids:
                state.artifact_ids.append(aid)

        # Update pending/active lists based on action type
        if action.action_type in (
            ActionType.CREATE_EXECUTABLE_TOOL_DRAFT,
            ActionType.CREATE_PROMPT_SKILL_DRAFT,
        ):
            for aid in result.artifacts_changed:
                if aid not in state.pending_artifact_ids:
                    state.pending_artifact_ids.append(aid)

        if action.action_type == ActionType.ACTIVATE_ARTIFACT and result.success:
            # Use artifact_id from both result.artifacts_changed and action payload
            activated_ids = set(result.artifacts_changed)
            if hasattr(action.payload, "artifact_id"):
                activated_ids.add(action.payload.artifact_id)
            for aid in activated_ids:
                if aid in state.pending_artifact_ids:
                    state.pending_artifact_ids.remove(aid)
                if aid not in state.active_artifact_ids:
                    state.active_artifact_ids.append(aid)

        if action.action_type == ActionType.REJECT_ARTIFACT and result.success:
            for aid in result.artifacts_changed:
                if aid in state.pending_artifact_ids:
                    state.pending_artifact_ids.remove(aid)

        # Add messages for send_message actions
        if action.action_type == ActionType.SEND_MESSAGE and result.success:
            from ..models.actions import SendMessagePayload
            p: SendMessagePayload = action.payload
            state.shared_messages.append(Message(
                role="assistant",
                content=p.content,
                agent_id=action.agent_id,
            ))

        # Add tool call results so agents can see what happened
        if action.action_type == ActionType.CALL_TOOL:
            from ..models.actions import CallToolPayload
            import json
            p: CallToolPayload = action.payload
            if result.success:
                output_str = json.dumps(result.output, ensure_ascii=False, default=str)
                state.shared_messages.append(Message(
                    role="system",
                    content=f"[Tool:{p.tool_name}] 调用成功，结果：{output_str[:500]}",
                    agent_id=action.agent_id,
                ))
            else:
                state.shared_messages.append(Message(
                    role="system",
                    content=f"[Tool:{p.tool_name}] 调用失败：{result.error}",
                    agent_id=action.agent_id,
                ))

        # Add evaluation feedback as message
        if result.evaluation_feedback:
            state.shared_messages.append(Message(
                role="system",
                content=f"[Evaluation] {result.evaluation_feedback}",
                agent_id=result.agent_id,
            ))

    def _should_end_turn(
        self,
        action: ActionEnvelope,
        result: ActionResult,
        consecutive_failures: int,
    ) -> bool:
        if action.action_type in (ActionType.HANDOFF, ActionType.FINAL_ANSWER):
            return True
        if consecutive_failures >= 3:
            return True
        if not result.should_continue_current_agent:
            return True
        # Builder stops after creating a draft
        if action.action_type in (
            ActionType.CREATE_EXECUTABLE_TOOL_DRAFT,
            ActionType.CREATE_PROMPT_SKILL_DRAFT,
        ) and result.success:
            return True
        # Planner stops after successful activation — next turn it will call the tool
        if action.action_type == ActionType.ACTIVATE_ARTIFACT and result.success:
            return True
        # Planner stops after call_tool failure — next turn it will retry with different args
        if action.action_type == ActionType.CALL_TOOL and not result.success:
            return True
        return False

