"""webui/backend/scheduler.py

Cron-style and interval-based agent scheduler + webhook trigger.

Schedules are persisted as JSON files under ``.agentsdk/schedules/``.
Each schedule fires an ``agent.run()`` in an asyncio background task and
records the result in ``MetricsStore``.

Supported trigger types
-----------------------
* ``"interval"`` — runs every *N* seconds (``interval_seconds`` field)
* ``"cron"``     — runs when a 5-field cron string matches the current wall
                   clock minute (checked every 60 s)

Webhook trigger
---------------
Every schedule gets a unique ``webhook_token`` (URL-safe random string).
``POST /webhook/{token}`` fires the schedule immediately without waiting
for the next scheduled tick.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEDULES_DIR = Path(".agentsdk") / "schedules"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ScheduleConfig:
    """Persistent configuration for one schedule entry."""

    id: str
    name: str
    agent_name: str
    input_message: str
    username: str
    trigger_type: str       # "interval" | "cron"
    interval_seconds: int = 3600
    cron: str = "0 * * * *"   # hourly default
    enabled: bool = True
    webhook_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_run_at: str | None = None
    last_run_ok: bool | None = None
    last_output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    """In-process scheduler backed by asyncio tasks.

    No extra dependencies (no APScheduler, Celery, etc.).
    """

    def __init__(self, agent_manager: Any, metrics: Any) -> None:
        self._am = agent_manager
        self._metrics = metrics
        self._schedules: dict[str, ScheduleConfig] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)
        self._load_all()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, cfg: ScheduleConfig) -> ScheduleConfig:
        self._schedules[cfg.id] = cfg
        self._persist(cfg)
        if cfg.enabled:
            self._start_task(cfg)
        return cfg

    def get(self, schedule_id: str) -> ScheduleConfig | None:
        return self._schedules.get(schedule_id)

    def get_by_webhook_token(self, token: str) -> ScheduleConfig | None:
        for s in self._schedules.values():
            if s.webhook_token == token:
                return s
        return None

    def list_all(self, username: str | None = None) -> list[ScheduleConfig]:
        items = list(self._schedules.values())
        if username:
            items = [s for s in items if s.username == username]
        return sorted(items, key=lambda s: s.created_at)

    def remove(self, schedule_id: str) -> bool:
        cfg = self._schedules.pop(schedule_id, None)
        if cfg is None:
            return False
        self._cancel_task(schedule_id)
        (SCHEDULES_DIR / f"{schedule_id}.json").unlink(missing_ok=True)
        return True

    def set_enabled(self, schedule_id: str, enabled: bool) -> ScheduleConfig:
        cfg = self._schedules[schedule_id]
        cfg.enabled = enabled
        self._persist(cfg)
        if enabled:
            self._start_task(cfg)
        else:
            self._cancel_task(schedule_id)
        return cfg

    # ------------------------------------------------------------------
    # Run now (webhook / manual trigger)
    # ------------------------------------------------------------------

    async def trigger_now(self, schedule_id: str) -> dict[str, Any]:
        """Fire the schedule immediately, regardless of its trigger schedule."""
        cfg = self._schedules.get(schedule_id)
        if cfg is None:
            raise KeyError(f"Schedule '{schedule_id}' not found")
        return await self._run_once(cfg)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_all(self) -> None:
        """Start background tasks for all enabled schedules (call at lifespan startup)."""
        for cfg in self._schedules.values():
            if cfg.enabled:
                self._start_task(cfg)

    def stop_all(self) -> None:
        """Cancel all running tasks (call at lifespan shutdown)."""
        for sid in list(self._tasks.keys()):
            self._cancel_task(sid)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_once(self, cfg: ScheduleConfig) -> dict[str, Any]:
        from metrics_store import build_record  # local import avoids circular deps

        session_key = f"{cfg.username}__sched_{cfg.id}"
        agent = self._am.get_or_create(session_key, cfg.agent_name)

        started_at = time.monotonic()
        started_wall = datetime.now(timezone.utc)
        result = None
        error: str | None = None

        try:
            result = await agent.run(cfg.input_message, session_id=session_key)
            cfg.last_run_ok = True
            cfg.last_output = result.output[:500] if result.output else None
        except Exception as exc:
            error = str(exc)
            cfg.last_run_ok = False
            logger.warning("Schedule '%s' run failed: %s", cfg.id, exc)

        cfg.last_run_at = datetime.now(timezone.utc).isoformat()
        self._persist(cfg)

        self._metrics.record(build_record(
            username=cfg.username,
            session_id=f"sched_{cfg.id}",
            agent_name=cfg.agent_name,
            started_at=started_at,
            started_wall=started_wall,
            result=result,
            error=error,
        ))

        return {
            "schedule_id": cfg.id,
            "ran_at": cfg.last_run_at,
            "success": cfg.last_run_ok,
            "error": error,
            "output": cfg.last_output,
        }

    def _start_task(self, cfg: ScheduleConfig) -> None:
        if cfg.id in self._tasks:
            return
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        task = loop.create_task(self._loop(cfg), name=f"sched-{cfg.id}")
        self._tasks[cfg.id] = task
        logger.info("Scheduler: started task for '%s' (%s)", cfg.id, cfg.trigger_type)

    def _cancel_task(self, schedule_id: str) -> None:
        task = self._tasks.pop(schedule_id, None)
        if task and not task.done():
            task.cancel()
            logger.info("Scheduler: cancelled task for '%s'", schedule_id)

    async def _loop(self, cfg: ScheduleConfig) -> None:
        """Asyncio loop that fires the schedule on its trigger."""
        while True:
            try:
                if cfg.trigger_type == "interval":
                    await asyncio.sleep(max(cfg.interval_seconds, 10))
                else:  # cron — check every 60 s
                    await asyncio.sleep(60)
                    if not _cron_matches(cfg.cron):
                        continue

                if cfg.enabled:
                    await self._run_once(cfg)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Scheduler loop error for '%s': %s", cfg.id, exc)
                await asyncio.sleep(10)

    def _persist(self, cfg: ScheduleConfig) -> None:
        path = SCHEDULES_DIR / f"{cfg.id}.json"
        path.write_text(json.dumps(cfg.to_dict(), indent=2))

    def _load_all(self) -> None:
        for path in SCHEDULES_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                cfg = ScheduleConfig(**data)
                self._schedules[cfg.id] = cfg
                logger.debug("Scheduler: loaded schedule '%s' from disk", cfg.id)
            except Exception as exc:
                logger.warning("Failed to load schedule from %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Minimal cron matcher (5-field: minute hour day month weekday)
# ---------------------------------------------------------------------------

def _cron_matches(cron_expr: str) -> bool:
    """Return True if *cron_expr* matches the current wall-clock minute."""
    try:
        fields = cron_expr.strip().split()
        if len(fields) != 5:
            return False
        now = datetime.now()
        current = [now.minute, now.hour, now.day, now.month, now.weekday()]
        for value, f in zip(current, fields):
            if f == "*":
                continue
            if "/" in f:
                _, step = f.split("/", 1)
                if value % int(step) != 0:
                    return False
            elif "," in f:
                allowed = [int(x) for x in f.split(",")]
                if value not in allowed:
                    return False
            elif "-" in f:
                lo, hi = f.split("-", 1)
                if not (int(lo) <= value <= int(hi)):
                    return False
            elif int(f) != value:
                return False
        return True
    except Exception:
        return False
