"""agentsdk/graph/bus.py

Inter-agent message bus — async pub/sub with request/reply and a
BusAwareAgent that can delegate work to peers mid-ReAct-loop.

Import chain (no circular dependencies):
    bus.py → agentsdk.agent       → agentsdk.llm → agentsdk.messages
           → agentsdk.llm
           → agentsdk.messages
           → agentsdk.tools.base
           → agentsdk.tools.registry
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentsdk.agent import Agent, AgentConfig, AgentResult
from agentsdk.llm import LLMProvider
from agentsdk.messages import Memory, MessageHistory
from agentsdk.tools.base import BaseTool, FunctionTool, ToolSchema
from agentsdk.tools.registry import ToolRegistry


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# BusMessage
# ---------------------------------------------------------------------------


class BusMessage(BaseModel):
    """A single message travelling over the :class:`MessageBus`."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    """Unique message ID — used as correlation key for request/reply."""

    from_agent: str
    to_agent: str | None = None
    """``None`` means broadcast to all topic subscribers."""

    topic: str
    """Logical channel, e.g. ``"task"``, ``"result"``, ``"error"``."""

    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=_utcnow)
    reply_to: str | None = None
    """Set to the original message's ``id`` when this is a response."""


# ---------------------------------------------------------------------------
# MessageBus
# ---------------------------------------------------------------------------


class MessageBus:
    """Async pub/sub message bus for inter-agent communication.

    Each agent gets a dedicated inbox queue (direct messages) and can also
    subscribe to named topic queues (broadcast / fan-out).

    Example::

        bus = MessageBus()
        bus.register("agent_a")
        bus.register("agent_b")
        await bus.send("agent_a", "agent_b", "task", {"content": "Hello"})
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[BusMessage]]] = {}
        self._agent_queues: dict[str, asyncio.Queue[BusMessage]] = {}
        self._history: list[BusMessage] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, agent_id: str) -> None:
        """Create a dedicated inbox queue for *agent_id* (idempotent)."""
        if agent_id not in self._agent_queues:
            self._agent_queues[agent_id] = asyncio.Queue()

    def subscribe(self, topic: str) -> asyncio.Queue[BusMessage]:
        """Return a new queue that receives every message published to *topic*."""
        q: asyncio.Queue[BusMessage] = asyncio.Queue()
        self._subscribers.setdefault(topic, []).append(q)
        return q

    # ------------------------------------------------------------------
    # Core messaging
    # ------------------------------------------------------------------

    async def publish(self, msg: BusMessage) -> None:
        """Route *msg* to the target agent's inbox and all topic subscribers."""
        self._history.append(msg)

        # Direct delivery to the named agent.
        if msg.to_agent and msg.to_agent in self._agent_queues:
            await self._agent_queues[msg.to_agent].put(msg)

        # Fan-out to topic subscribers.
        for q in self._subscribers.get(msg.topic, []):
            await q.put(msg)

    async def send(
        self,
        from_agent: str,
        to_agent: str | None,
        topic: str,
        payload: dict[str, Any],
        reply_to: str | None = None,
    ) -> BusMessage:
        """Build and publish a :class:`BusMessage`; return it."""
        msg = BusMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            topic=topic,
            payload=payload,
            reply_to=reply_to,
        )
        await self.publish(msg)
        return msg

    async def request(
        self,
        from_agent: str,
        to_agent: str,
        topic: str,
        payload: dict[str, Any],
        timeout: float = 30.0,
    ) -> BusMessage:
        """Send a message and wait for a reply whose ``reply_to`` matches the sent ``id``.

        Non-matching messages that arrive while waiting are buffered and
        put back on the queue after the reply is received (or on timeout).

        Raises
        ------
        asyncio.TimeoutError
            If no matching reply arrives within *timeout* seconds.
        """
        msg = await self.send(from_agent, to_agent, topic, payload)
        queue = self._agent_queues[from_agent]
        buffer: list[BusMessage] = []

        async def _wait() -> BusMessage:
            while True:
                item = await queue.get()
                if item.reply_to == msg.id:
                    # Restore buffered messages before returning.
                    for buffered in buffer:
                        await queue.put(buffered)
                    return item
                buffer.append(item)

        try:
            return await asyncio.wait_for(_wait(), timeout=timeout)
        except asyncio.TimeoutError:
            for buffered in buffer:
                await queue.put(buffered)
            raise

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def get_history(self, agent_id: str | None = None) -> list[BusMessage]:
        """Return all messages, optionally filtered to those involving *agent_id*."""
        if agent_id is None:
            return list(self._history)
        return [
            m for m in self._history
            if m.from_agent == agent_id or m.to_agent == agent_id
        ]

    def drain(self, agent_id: str) -> list[BusMessage]:
        """Pull all pending messages from *agent_id*'s inbox without blocking."""
        queue = self._agent_queues.get(agent_id)
        if queue is None:
            return []
        messages: list[BusMessage] = []
        while not queue.empty():
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages


# ---------------------------------------------------------------------------
# BusAwareAgent
# ---------------------------------------------------------------------------


class BusAwareAgent(Agent):
    """An Agent that participates in a MessageBus.

    Extra capabilities over the base Agent:

    - Drains its inbox before each ReAct loop so incoming messages appear
      as context in the conversation history.
    - Can delegate work to peer agents via ``delegate()`` or through
      the auto-registered ``ask_agent`` tool (callable by the LLM).

    Args:
        config: AgentConfig for this agent.
        llm: Any LLMProvider implementation.
        tools: Optional flat list of BaseTool instances.
        memory: Optional Memory backend (legacy; prefer session_manager).
        registry: Optional ToolRegistry.
        bus: The shared MessageBus instance this agent joins.
        node_id: Unique agent ID used to address messages on the bus.

    Example::

        bus = MessageBus()
        agent = BusAwareAgent(config=config, llm=llm, bus=bus, node_id="agent_a")
    """

    def __init__(
        self,
        config: AgentConfig,
        llm: LLMProvider,
        tools: list[BaseTool] | None = None,
        memory: Memory | None = None,
        registry: ToolRegistry | None = None,
        bus: MessageBus | None = None,
        node_id: str | None = None,
    ) -> None:
        super().__init__(config, llm, tools, memory, registry)
        self.bus = bus
        self.node_id = node_id

        if bus is not None and node_id is not None:
            bus.register(node_id)
            ask_tool = self._make_ask_agent_tool()
            self._tools.append(ask_tool)
            self._tool_map[ask_tool.schema.name] = ask_tool

    # ------------------------------------------------------------------
    # Hook: drain bus into history before the ReAct loop
    # ------------------------------------------------------------------

    async def _pre_run_hook(self, history: MessageHistory) -> None:
        """Inject any pending bus messages as HumanMessage entries."""
        if not (self.bus and self.node_id):
            return
        for msg in self.bus.drain(self.node_id):
            content = (
                f"[Incoming from {msg.from_agent}]: "
                f"{msg.payload.get('content', '')}"
            )
            history.add_human(content)

    # ------------------------------------------------------------------
    # Delegation
    # ------------------------------------------------------------------

    async def delegate(self, to_agent: str, task: str) -> str:
        """Send *task* to *to_agent* and block until a ``"result"`` reply arrives.

        Uses :meth:`MessageBus.request` with the default 30-second timeout.
        """
        if not (self.bus and self.node_id):
            raise RuntimeError(
                f"Agent '{self.config.name}' has no bus — cannot delegate."
            )
        reply = await self.bus.request(
            from_agent=self.node_id,
            to_agent=to_agent,
            topic="task",
            payload={"content": task},
        )
        return reply.payload.get("content", "")

    # ------------------------------------------------------------------
    # ask_agent tool factory
    # ------------------------------------------------------------------

    def _make_ask_agent_tool(self) -> FunctionTool:
        """Build the ``ask_agent`` tool that captures this agent's ``delegate``."""
        agent_self = self

        async def ask_agent(agent_id: str, question: str) -> str:
            """Delegate a question to another agent by ID and return its answer."""
            return await agent_self.delegate(agent_id, question)

        return FunctionTool(
            fn=ask_agent,
            tool_schema=ToolSchema(
                name="ask_agent",
                description=(
                    "Delegate a question to another agent by ID and return its answer."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "question": {"type": "string"},
                    },
                    "required": ["agent_id", "question"],
                },
            ),
        )


# ---------------------------------------------------------------------------
# BusRunner
# ---------------------------------------------------------------------------


class BusRunner:
    """Runs a group of :class:`BusAwareAgent` instances concurrently.

    The entry agent handles the initial user input.  All other agents are
    kept alive as listeners — they process ``"task"`` messages from the bus
    and publish ``"result"`` or ``"error"`` replies.
    """

    def __init__(
        self,
        bus: MessageBus,
        agents: dict[str, BusAwareAgent],
    ) -> None:
        self._bus = bus
        self._agents = agents

    async def run(self, entry_agent_id: str, initial_input: str) -> str:
        """Start all agents, run the entry agent, cancel listeners on completion.

        Parameters
        ----------
        entry_agent_id:
            Key in ``agents`` that handles the initial user input.
        initial_input:
            The user message sent to the entry agent.

        Returns
        -------
        str
            The entry agent's final output string.
        """
        if entry_agent_id not in self._agents:
            raise ValueError(
                f"Entry agent '{entry_agent_id}' not in the agents dict."
            )

        # Ensure every agent is registered on the bus.
        for agent_id in self._agents:
            self._bus.register(agent_id)

        # Spawn a persistent listener for every non-entry agent.
        listener_tasks: list[asyncio.Task] = [
            asyncio.create_task(self._agent_listener(agent_id, agent))
            for agent_id, agent in self._agents.items()
            if agent_id != entry_agent_id
        ]

        try:
            result: AgentResult = await self._agents[entry_agent_id].run(
                initial_input
            )
            return result.output
        finally:
            for task in listener_tasks:
                task.cancel()
            await asyncio.gather(*listener_tasks, return_exceptions=True)

    async def _agent_listener(
        self, agent_id: str, agent: BusAwareAgent
    ) -> None:
        """Process ``"task"`` messages from the inbox and publish replies."""
        queue = self._bus._agent_queues[agent_id]
        try:
            while True:
                msg = await queue.get()
                if msg.topic != "task":
                    continue  # non-task messages handled by drain()
                try:
                    result = await agent.run(msg.payload.get("content", ""))
                    await self._bus.send(
                        from_agent=agent_id,
                        to_agent=msg.from_agent,
                        topic="result",
                        payload={"content": result.output},
                        reply_to=msg.id,
                    )
                except Exception as exc:  # noqa: BLE001
                    await self._bus.send(
                        from_agent=agent_id,
                        to_agent=msg.from_agent,
                        topic="error",
                        payload={"content": str(exc)},
                        reply_to=msg.id,
                    )
        except asyncio.CancelledError:
            pass  # clean shutdown requested by BusRunner.run()
