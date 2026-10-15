"""Persistent rolling-code counter with write-ahead reservation.

Counter values are reserved and fsync'ed *before* they are sent. A crash of
Home Assistant or the bridge can therefore only leave unused gaps, never send
a value twice. The counter only moves forward.

The storage key derives from a hash of the base serial (not the entry id), so
removing and re-adding the integration keeps the counter.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.file import WriteError, write_utf8_file_atomic

from .const import DOMAIN

# Own file instead of helpers.storage.Store: Store only logs write errors and
# defers writes while HA is stopping. A reservation must fail loudly instead.
STORAGE_VERSION = 1
MIN_COUNTER = 1
MAX_COUNTER = 0xFFFF


class CounterExhausted(HomeAssistantError):
    """The 16-bit counter would overflow."""


class CounterUnavailable(HomeAssistantError):
    """The counter cannot be persisted, so nothing may be sent."""


def storage_key(base_serial: int) -> str:
    digest = hashlib.sha256(f"{DOMAIN}:{base_serial}".encode()).hexdigest()[:16]
    return f"{DOMAIN}.counter_{digest}"


class CounterStore:
    def __init__(self, hass: HomeAssistant, base_serial: int) -> None:
        self._hass = hass
        self._path = Path(hass.config.path(".storage", storage_key(base_serial)))
        self._next: int | None = None
        self._lock = asyncio.Lock()

    @property
    def next(self) -> int:
        """Next value that has not been reserved yet."""
        assert self._next is not None
        return self._next

    async def async_load(self, minimum: int) -> None:
        """Load the counter; never go below ``minimum`` and never backwards."""
        data = await self._hass.async_add_executor_job(self._read)
        stored = int(data["next"]) if data else MIN_COUNTER
        self._next = max(stored, minimum, MIN_COUNTER)
        if data is None or self._next != stored:
            await self._async_save()

    async def async_reserve(self, count: int) -> int:
        """Reserve ``count`` consecutive values and persist before returning the first."""
        if count < 1:
            raise ValueError("count must be >= 1")
        async with self._lock:
            first = self.next
            if first + count - 1 > MAX_COUNTER:
                raise CounterExhausted(
                    translation_domain=DOMAIN, translation_key="counter_exhausted"
                )
            self._next = first + count
            await self._async_save()
            return first

    async def async_set_next(self, value: int) -> None:
        """Move the counter forward (never backwards)."""
        async with self._lock:
            if not self.next <= value <= MAX_COUNTER:
                raise ValueError("counter can only move forward")
            self._next = value
            await self._async_save()

    def _read(self) -> dict | None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        return raw["data"]

    def _write(self, value: int) -> None:
        payload = {"version": STORAGE_VERSION, "key": self._path.name, "data": {"next": value}}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        write_utf8_file_atomic(str(self._path), json.dumps(payload), private=True)  # fsync + rename

    async def _async_save(self) -> None:
        if self._hass.is_stopping:
            raise CounterUnavailable(translation_domain=DOMAIN, translation_key="stopping")
        try:
            await self._hass.async_add_executor_job(self._write, self._next)
        except (OSError, WriteError) as err:
            raise CounterUnavailable(
                translation_domain=DOMAIN, translation_key="counter_write_failed"
            ) from err
