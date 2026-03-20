"""EventSink: unified event hub for persistence, SSE, and CLI display."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

from rich.console import Console
from rich.text import Text

from ..models.events import EventType, RuntimeEvent
from .structured import log_event

console = Console()

# Display config: event_type -> (label, style)
_DISPLAY = {
    EventType.RUN_STARTED: ("RUN", "bold green"),
    EventType.AGENT_TURN_STARTED: ("TURN", "bold cyan"),
    EventType.MESSAGE_CREATED: ("MSG", "white"),
    EventType.ACTION_CREATED: ("ACT", "yellow"),
    EventType.ACTION_RESULT: ("RES", "blue"),
    EventType.SKILL_INJECTED: ("SKILL", "magenta"),
    EventType.ARTIFACT_CREATED: ("ART+", "green"),
    EventType.ARTIFACT_UPDATED: ("ART~", "green"),
    EventType.EVALUATION_COMPLETED: ("EVAL", "cyan"),
    EventType.AGENT_TURN_ENDED: ("TURN", "dim cyan"),
    EventType.AGENT_HANDOFF: ("HAND", "bold yellow"),
    EventType.RUN_COMPLETED: ("DONE", "bold green"),
    EventType.RUN_FAILED: ("FAIL", "bold red"),
}


class EventSink:
    """Unified event sink. All runtime components emit events through here."""

    def __init__(self, run_id: str, runs_dir: str | Path = "runs", cli_display: bool = False):
        self._run_id = run_id
        self._run_dir = Path(runs_dir) / run_id
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self._run_dir / "events.jsonl"
        self._seq = 0
        self._subscribers: list[asyncio.Queue[RuntimeEvent | None]] = []
        self._cli_display = cli_display

    async def emit(self, event: RuntimeEvent):
        self._seq += 1
        event.sequence_number = self._seq
        event.run_id = self._run_id
        # Persist
        await self._write_to_run_log(event)
        # Push to SSE subscribers
        await self._push_to_subscribers(event)
        # CLI display
        if self._cli_display:
            self._display_to_console(event)
        # Structured log
        log_event(event)

    async def _write_to_run_log(self, event: RuntimeEvent):
        line = event.model_dump_json() + "\n"
        with open(self._events_path, "a") as f:
            f.write(line)

    async def _push_to_subscribers(self, event: RuntimeEvent):
        for q in self._subscribers:
            await q.put(event)

    def _display_to_console(self, event: RuntimeEvent):
        label, style = _DISPLAY.get(event.event_type, ("EVT", "white"))
        agent = event.agent_id or ""
        role = f"({event.agent_role.value})" if event.agent_role else ""
        step = f"step={event.step_in_turn}" if event.step_in_turn is not None else ""

        header = Text()
        header.append(f"[{label}]", style=style)
        header.append(f" R{event.round_number}", style="dim")
        if agent:
            header.append(f" {agent}{role}", style="dim cyan")
        if step:
            header.append(f" {step}", style="dim")

        payload_summary = self._summarize_payload(event)
        if payload_summary:
            header.append(f"  {payload_summary}", style="white")

        console.print(header)

    def _summarize_payload(self, event: RuntimeEvent) -> str:
        p = event.payload
        match event.event_type:
            case EventType.RUN_STARTED:
                return p.get("task", "")[:80]
            case EventType.ACTION_CREATED:
                return p.get("action_type", "")
            case EventType.ACTION_RESULT:
                ok = "ok" if p.get("success") else "FAIL"
                err = p.get("error", "")
                return f"{ok} {err}"[:80] if err else ok
            case EventType.AGENT_HANDOFF:
                return f"{p.get('from_agent','')} -> {p.get('to_agent','')}: {p.get('reason','')}"[:80]
            case EventType.RUN_COMPLETED:
                return p.get("final_answer", "")[:80]
            case EventType.RUN_FAILED:
                return p.get("error_detail", "")[:80]
            case EventType.ARTIFACT_CREATED | EventType.ARTIFACT_UPDATED:
                return p.get("artifact_id", "") or p.get("artifact_summary", {}).get("name", "")
            case EventType.EVALUATION_COMPLETED:
                card = p.get("evaluation_card", {})
                return f"{'APPROVE' if card.get('approve') else 'REJECT'} {card.get('artifact_id','')}"
            case EventType.SKILL_INJECTED:
                return p.get("skill_name", "")
            case _:
                return ""

    def subscribe(self) -> AsyncIterator[RuntimeEvent]:
        q: asyncio.Queue[RuntimeEvent | None] = asyncio.Queue()
        self._subscribers.append(q)
        return self._iter_queue(q)

    async def _iter_queue(self, q: asyncio.Queue[RuntimeEvent | None]) -> AsyncIterator[RuntimeEvent]:
        try:
            while True:
                event = await q.get()
                if event is None:
                    break
                yield event
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)

    async def close(self):
        for q in self._subscribers:
            await q.put(None)
        self._subscribers.clear()

    @staticmethod
    def load_events(run_dir: str | Path) -> list[RuntimeEvent]:
        events_path = Path(run_dir) / "events.jsonl"
        if not events_path.exists():
            return []
        events = []
        for line in events_path.read_text().strip().split("\n"):
            if line.strip():
                events.append(RuntimeEvent.model_validate_json(line))
        return events
