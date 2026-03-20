"""RunService: creates runs, executes in background, queries status, streams events."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator

from ..agents.base import BaseAgent
from ..agents.builder import BuilderAgent
from ..agents.planner import PlannerAgent
from ..agents.reviewer import ReviewerAgent
from ..agents.user_simulator import UserSimulatorAgent
from ..builtin_tools import BUILTIN_TOOLS
from ..logging.event_sink import EventSink
from ..models.agent_profile import AgentProfile, AgentRole
from ..models.conversation import ConversationState
from ..models.events import EventType, RuntimeEvent
from ..models.results import ActionResult
from ..providers.base import ModelProvider
from ..registry.artifact_registry import ArtifactRegistry
from ..runtime.agent_runner import AgentRunner
from ..runtime.executor import ActionExecutor
from ..runtime.sandbox import Sandbox
from ..runtime.scheduler import Scheduler


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunInfo:
    def __init__(self, run_id: str, task: str):
        self.run_id = run_id
        self.task = task
        self.status = RunStatus.PENDING
        self.created_at = datetime.now()
        self.completed_at: datetime | None = None
        self.final_answer: str | None = None
        self.round_number: int = 0
        self.current_agent: str | None = None
        self.error: str | None = None
        self.event_sink: EventSink | None = None
        self._task: asyncio.Task | None = None


class RunService:
    def __init__(
        self,
        registry: ArtifactRegistry,
        providers: dict[str, ModelProvider],
        runs_dir: str | Path = "runs",
        max_rounds: int = 20,
    ):
        self._registry = registry
        self._providers = providers
        self._runs_dir = Path(runs_dir)
        self._runs: dict[str, RunInfo] = {}
        self._max_rounds = max_rounds

    def _build_agents(self) -> dict[str, BaseAgent]:
        profiles = {
            "planner": AgentProfile(
                agent_id="planner",
                role=AgentRole.PLANNER,
                display_name="Planner",
                model_name="qwen3.5-plus",
                max_actions_per_turn=5,
            ),
            "builder": AgentProfile(
                agent_id="builder",
                role=AgentRole.BUILDER,
                display_name="Builder",
                model_name="qwen3.5-plus",
                max_actions_per_turn=2,
            ),
            "reviewer": AgentProfile(
                agent_id="reviewer",
                role=AgentRole.REVIEWER,
                display_name="Reviewer",
                model_name="glm-5",
                max_actions_per_turn=2,
            ),
            "user_simulator": AgentProfile(
                agent_id="user_simulator",
                role=AgentRole.USER_SIMULATOR,
                display_name="User Simulator",
                model_name="MiniMax-M2.5",
                max_actions_per_turn=2,
            ),
        }

        agent_classes = {
            "planner": PlannerAgent,
            "builder": BuilderAgent,
            "reviewer": ReviewerAgent,
            "user_simulator": UserSimulatorAgent,
        }

        agents = {}
        for name, profile in profiles.items():
            provider = self._providers.get(name) or self._providers.get("default")
            if provider is None:
                raise ValueError(f"No provider configured for agent '{name}' or 'default'")
            agents[name] = agent_classes[name](profile=profile, provider=provider)
        return agents

    async def create_run(self, task: str, cli_display: bool = False) -> str:
        run_id = uuid.uuid4().hex[:12]
        info = RunInfo(run_id=run_id, task=task)
        info.event_sink = EventSink(
            run_id=run_id,
            runs_dir=self._runs_dir,
            cli_display=cli_display,
        )
        self._runs[run_id] = info
        return run_id

    async def start_run(self, run_id: str) -> asyncio.Task:
        info = self._runs.get(run_id)
        if info is None:
            raise ValueError(f"Run {run_id} not found")
        info.status = RunStatus.RUNNING
        task = asyncio.create_task(self._execute_run(info))
        info._task = task
        return task

    async def _execute_run(self, info: RunInfo):
        event_sink = info.event_sink
        try:
            agents = self._build_agents()
            sandbox = Sandbox()
            executor = ActionExecutor(
                registry=self._registry,
                sandbox=sandbox,
                builtin_tools=BUILTIN_TOOLS,
            )
            runner = AgentRunner(
                executor=executor,
                event_sink=event_sink,
                registry=self._registry,
            )
            scheduler = Scheduler(agents=agents, max_rounds=self._max_rounds)

            state = ConversationState(run_id=info.run_id, task=info.task)

            await event_sink.emit(RuntimeEvent(
                event_type=EventType.RUN_STARTED,
                run_id=info.run_id,
                payload={"task": info.task},
            ))

            while not scheduler.should_terminate(state):
                agent = scheduler.select_next_agent(state)
                if agent is None:
                    break

                state.current_agent_id = agent.profile.agent_id
                state.round_number += 1
                info.round_number = state.round_number
                info.current_agent = agent.profile.agent_id

                results = await runner.run_agent_turn(agent, state)

                # Check for final_answer
                for r in results:
                    if r.action_type == "final_answer" and r.success:
                        output = r.output
                        if isinstance(output, dict):
                            state.final_answer = output.get("content", "")
                        state.terminated = True
                        break

            info.status = RunStatus.COMPLETED
            info.completed_at = datetime.now()
            info.final_answer = state.final_answer

            await event_sink.emit(RuntimeEvent(
                event_type=EventType.RUN_COMPLETED,
                run_id=info.run_id,
                round_number=state.round_number,
                payload={
                    "final_answer": state.final_answer or "",
                    "total_rounds": state.round_number,
                },
            ))

        except Exception as e:
            info.status = RunStatus.FAILED
            info.error = str(e)
            info.completed_at = datetime.now()
            await event_sink.emit(RuntimeEvent(
                event_type=EventType.RUN_FAILED,
                run_id=info.run_id,
                round_number=info.round_number,
                payload={
                    "error_detail": str(e),
                    "last_agent": info.current_agent,
                    "last_round": info.round_number,
                },
            ))
        finally:
            await event_sink.close()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        info = self._runs.get(run_id)
        if info is None:
            return None
        return {
            "run_id": info.run_id,
            "task": info.task,
            "status": info.status.value,
            "created_at": info.created_at.isoformat(),
            "completed_at": info.completed_at.isoformat() if info.completed_at else None,
            "final_answer": info.final_answer,
            "round_number": info.round_number,
            "current_agent": info.current_agent,
            "error": info.error,
        }

    def get_event_sink(self, run_id: str) -> EventSink | None:
        info = self._runs.get(run_id)
        if info:
            return info.event_sink
        return None

    def subscribe_events(self, run_id: str) -> AsyncIterator[RuntimeEvent] | None:
        sink = self.get_event_sink(run_id)
        if sink:
            return sink.subscribe()
        return None
