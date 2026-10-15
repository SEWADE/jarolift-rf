"""Serial transmit queue: one radio command at a time.

- STOP jumps ahead of other waiting commands.
- Simple commands (up/down/stop/shade) arriving within a short window are
  merged into one group telegram (e.g. an HA cover group calling each member).
- Commands older than COMMAND_MAX_AGE_S are dropped; nothing is persisted, so
  nothing is replayed after a restart.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .bridge import Bridge
from .const import COMMAND_MAX_AGE_S, DOMAIN
from .core import sequences as sq
from .counter import CounterStore

_LOGGER = logging.getLogger(__name__)

BUNDLEABLE = frozenset({sq.Command.UP, sq.Command.DOWN, sq.Command.STOP, sq.Command.SHADE})


class CommandDropped(HomeAssistantError):
    """Command was too old or the queue was shut down."""


@dataclass(frozen=True)
class TxSettings:
    enabled: bool
    power_dbm: int
    bundle_ms: int
    legacy_learn: bool


@dataclass
class _Job:
    command: sq.Command
    mask: int
    group: bool
    future: asyncio.Future[None]
    created: float = field(default_factory=time.monotonic)


class TxScheduler:
    def __init__(
        self,
        hass: HomeAssistant,
        bridge: Bridge,
        counter: CounterStore,
        *,
        base_serial: int,
        master_msb: int,
        master_lsb: int,
        settings: Callable[[], TxSettings],
        on_counter: Callable[[], None] = lambda: None,
    ) -> None:
        self._hass = hass
        self._bridge = bridge
        self._counter = counter
        self._base_serial = base_serial
        self._keys = (master_msb, master_lsb)
        self._settings = settings
        self._on_counter = on_counter
        self._pending: list[_Job] = []
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task | None = None

    @property
    def queue_length(self) -> int:
        return len(self._pending)

    def start(self, entry: ConfigEntry) -> None:
        self._task = entry.async_create_background_task(self._hass, self._run(), f"{DOMAIN} tx queue")

    async def async_stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for job in self._pending:
            _fail(job, CommandDropped(translation_domain=DOMAIN, translation_key="queue_stopped"))
        self._pending.clear()

    async def async_send(self, command: sq.Command, mask: int, *, group: bool = False) -> None:
        """Queue a command for a channel mask and wait until it was transmitted."""
        if not self._settings().enabled:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="tx_disabled")
        if not 0 < mask <= 0xFFFF:
            raise ValueError("mask must be 1..0xFFFF")
        if group and command not in sq.GROUP_COMMANDS:
            raise ValueError(f"{command} is not available for groups")
        if not group and mask.bit_count() != 1:
            raise ValueError("channel commands need exactly one channel")
        job = _Job(command, mask, group, self._hass.loop.create_future())
        if command is sq.Command.STOP:
            pos = next((i for i, j in enumerate(self._pending) if j.command is not sq.Command.STOP), len(self._pending))
            self._pending.insert(pos, job)
        else:
            self._pending.append(job)
        self._wakeup.set()
        await job.future

    async def _run(self) -> None:
        while True:
            await self._wakeup.wait()
            self._wakeup.clear()
            while self._pending:
                job = self._pending.pop(0)
                if time.monotonic() - job.created > COMMAND_MAX_AGE_S:
                    _fail(job, CommandDropped(translation_domain=DOMAIN, translation_key="command_too_old"))
                    continue
                jobs = [job]
                settings = self._settings()
                if job.command in BUNDLEABLE and settings.bundle_ms > 0:
                    await asyncio.sleep(settings.bundle_ms / 1000)
                    same = [j for j in self._pending if j.command is job.command]
                    for j in same:
                        self._pending.remove(j)
                    jobs += same
                try:
                    await self._execute(jobs, settings)
                except Exception as err:  # noqa: BLE001 - every caller gets the error
                    for j in jobs:
                        _fail(j, err)
                else:
                    for j in jobs:
                        if not j.future.done():
                            j.future.set_result(None)

    async def _execute(self, jobs: list[_Job], settings: TxSettings) -> None:
        command = jobs[0].command
        mask = 0
        for j in jobs:
            mask |= j.mask
        as_channel = not any(j.group for j in jobs) and mask.bit_count() == 1
        if as_channel:
            target = sq.Target.channel(self._base_serial, mask.bit_length() - 1)
        else:
            target = sq.Target.group(self._base_serial, mask)
        steps = sq.steps_for(command, legacy_learn=settings.legacy_learn)
        needed = sq.counters_needed(steps)
        first = await self._counter.async_reserve(needed)  # persisted before sending
        self._on_counter()
        _LOGGER.debug(
            "Sending %s to mask 0x%04X (%s), counters %d..%d",
            command, mask, "channel" if as_channel else "group", first, first + needed - 1,
        )
        for item in sq.render(steps, target, first, *self._keys):
            if isinstance(item, sq.Pause):
                await asyncio.sleep(item.ms / 1000)
            else:
                await self._bridge.async_send(item, settings.power_dbm)


def _fail(job: _Job, err: Exception) -> None:
    if not job.future.done():
        job.future.set_exception(err)
