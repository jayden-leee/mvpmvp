"""
opener-ultra-mvp / engine / core.py
====================================
Event-driven Agent State Manager
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ──────────────────────────────────────────
# Enums
# ──────────────────────────────────────────

class AgentStatus(str, Enum):
    IDLE       = "idle"
    RUNNING    = "running"
    COMPLETED  = "completed"
    FAILED     = "failed"
    PAUSED     = "paused"


class EventType(str, Enum):
    AGENT_STARTED    = "agent.started"
    AGENT_UPDATED    = "agent.updated"
    AGENT_COMPLETED  = "agent.completed"
    AGENT_FAILED     = "agent.failed"
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_DONE    = "pipeline.done"
    STATE_SNAPSHOT   = "state.snapshot"


# ──────────────────────────────────────────
# Data models
# ──────────────────────────────────────────

@dataclass
class AgentState:
    agent_id:   str
    name:       str
    status:     AgentStatus = AgentStatus.IDLE
    progress:   float = 0.0          # 0.0 – 1.0
    result:     Optional[Any] = None
    error:      Optional[str] = None
    started_at: Optional[float] = None
    ended_at:   Optional[float] = None
    metadata:   Dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.ended_at or time.time()
        return round(end - self.started_at, 3)

    def to_dict(self) -> dict:
        return {
            "agent_id":   self.agent_id,
            "name":       self.name,
            "status":     self.status.value,
            "progress":   self.progress,
            "result":     self.result,
            "error":      self.error,
            "elapsed":    self.elapsed,
            "metadata":   self.metadata,
        }


@dataclass
class Event:
    event_id:   str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type:       EventType = EventType.STATE_SNAPSHOT
    agent_id:   Optional[str] = None
    payload:    Dict[str, Any] = field(default_factory=dict)
    timestamp:  float = field(default_factory=time.time)


# ──────────────────────────────────────────
# Event Bus
# ──────────────────────────────────────────

class EventBus:
    """Lightweight async pub/sub event bus."""

    def __init__(self):
        self._listeners: Dict[EventType, List[Callable]] = defaultdict(list)
        self._history:   List[Event] = []

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        self._listeners[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        self._listeners[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        self._history.append(event)
        handlers = self._listeners.get(event.type, [])
        await asyncio.gather(
            *(self._call(h, event) for h in handlers),
            return_exceptions=True,
        )

    @staticmethod
    async def _call(handler: Callable, event: Event) -> None:
        if asyncio.iscoroutinefunction(handler):
            await handler(event)
        else:
            handler(event)

    @property
    def history(self) -> List[Event]:
        return list(self._history)


# ──────────────────────────────────────────
# State Manager
# ──────────────────────────────────────────

class StateManager:
    """
    Central state manager for all agents.

    Usage
    -----
    sm = StateManager()
    sm.register_agent("agent-1", "DataFetcher")

    # inside an agent coroutine:
    await sm.start_agent("agent-1")
    await sm.update_agent("agent-1", progress=0.5, metadata={"rows": 120})
    await sm.complete_agent("agent-1", result={"rows": 240})
    """

    def __init__(self):
        self.bus:    EventBus = EventBus()
        self._agents: Dict[str, AgentState] = {}

    # ── Registration ──────────────────────

    def register_agent(self, agent_id: str, name: str, **metadata) -> AgentState:
        state = AgentState(agent_id=agent_id, name=name, metadata=metadata)
        self._agents[agent_id] = state
        return state

    # ── Lifecycle transitions ─────────────

    async def start_agent(self, agent_id: str) -> AgentState:
        state = self._get(agent_id)
        state.status     = AgentStatus.RUNNING
        state.started_at = time.time()
        state.progress   = 0.0
        await self.bus.publish(Event(
            type=EventType.AGENT_STARTED,
            agent_id=agent_id,
            payload=state.to_dict(),
        ))
        return state

    async def update_agent(
        self,
        agent_id: str,
        progress: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> AgentState:
        state = self._get(agent_id)
        if progress is not None:
            state.progress = max(0.0, min(1.0, progress))
        if metadata:
            state.metadata.update(metadata)
        await self.bus.publish(Event(
            type=EventType.AGENT_UPDATED,
            agent_id=agent_id,
            payload=state.to_dict(),
        ))
        return state

    async def complete_agent(
        self, agent_id: str, result: Any = None
    ) -> AgentState:
        state = self._get(agent_id)
        state.status   = AgentStatus.COMPLETED
        state.progress = 1.0
        state.result   = result
        state.ended_at = time.time()
        await self.bus.publish(Event(
            type=EventType.AGENT_COMPLETED,
            agent_id=agent_id,
            payload=state.to_dict(),
        ))
        return state

    async def fail_agent(
        self, agent_id: str, error: str
    ) -> AgentState:
        state = self._get(agent_id)
        state.status   = AgentStatus.FAILED
        state.error    = error
        state.ended_at = time.time()
        await self.bus.publish(Event(
            type=EventType.AGENT_FAILED,
            agent_id=agent_id,
            payload=state.to_dict(),
        ))
        return state

    # ── Queries ───────────────────────────

    def snapshot(self) -> Dict[str, dict]:
        return {aid: s.to_dict() for aid, s in self._agents.items()}

    def get_state(self, agent_id: str) -> AgentState:
        return self._get(agent_id)

    def agents_by_status(self, status: AgentStatus) -> List[AgentState]:
        return [s for s in self._agents.values() if s.status == status]

    # ── Internal ──────────────────────────

    def _get(self, agent_id: str) -> AgentState:
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not registered.")
        return self._agents[agent_id]
