"""Receiving: raw pulses from the bridge -> remote events and assumed states."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import TYPE_CHECKING

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    BUS_EVENT_REMOTE,
    CONF_CHANNELS,
    CONF_REMOTE_SERIAL,
    DOMAIN,
    SIGNAL_REMOTE,
    SUBENTRY_REMOTE,
)
from .core import rx
from .core.telegram import Button
from .runtime import ShutterState

if TYPE_CHECKING:
    from .runtime import JaroliftConfigEntry

_LOGGER = logging.getLogger(__name__)

SAME_PRESS_S = 2.0  # repetitions of one press carry the same counter
SHADE_AFTER_STOP_FRAMES = 10  # long STOP press = shade (as in the reference firmware)
RECENT_UNKNOWN = 8

EVENT_TYPES = ["up", "down", "stop", "shade", "up_down", "learn", "other"]
_BUTTON_EVENT = {Button.UP: "up", Button.DOWN: "down", Button.STOP: "stop",
                 Button.UP_DOWN: "up_down", Button.LEARN_LEGACY: "learn"}


@dataclass
class SeenRemote:
    remote_serial: int  # serial >> 8, as "remote_serial" in the original config.json
    event_type: str
    channel_mask: int
    verified: bool
    seen: float


@dataclass
class _Press:
    key: tuple[int, int, int]
    first: float
    frames: int = 1
    shade_sent: bool = False


class RemoteReceiver:
    def __init__(self, hass: HomeAssistant, entry: JaroliftConfigEntry, base_serial: int, keys: tuple[int, int]):
        self._hass = hass
        self._entry = entry
        self._base_serial = base_serial
        self._keys = keys
        self._press: _Press | None = None
        self.recent_unknown: dict[int, SeenRemote] = {}
        self.last: SeenRemote | None = None

    @callback
    def handle_raw_event(self, event: Event) -> None:
        try:
            pulses = [int(p) for p in str(event.data.get("pulses", "")).split(",") if p]
        except ValueError:
            return
        telegram = rx.decode_pulses(pulses)
        if telegram is None:
            return
        result = rx.authenticate(telegram, *self._keys)
        now = time.monotonic()
        key = (telegram.serial, result.counter, telegram.button)
        press = self._press
        if press and press.key == key and now - press.first < SAME_PRESS_S + press.frames * 0.12:
            press.frames += 1
            if (telegram.button == Button.STOP and press.frames >= SHADE_AFTER_STOP_FRAMES
                    and not press.shade_sent):
                press.shade_sent = True
                self._emit(result, "shade", now)
            return
        self._press = _Press(key, now)
        self._emit(result, _BUTTON_EVENT.get(telegram.button, "other"), now)

    def _emit(self, result: rx.RxResult, event_type: str, now: float) -> None:
        remote_serial = result.telegram.serial >> 8
        seen = SeenRemote(remote_serial, event_type, result.channel_mask, result.valid, now)
        self.last = seen
        if remote_serial == self._base_serial:
            # Another sender uses our serial (e.g. the old controller still running): counters will clash.
            ir.async_create_issue(
                self._hass, DOMAIN, f"foreign_sender_{self._entry.entry_id}", is_fixable=False,
                severity=ir.IssueSeverity.ERROR, translation_key="foreign_sender",
            )
            return
        remote = next(
            (s for s in self._entry.subentries.values()
             if s.subentry_type == SUBENTRY_REMOTE and s.data[CONF_REMOTE_SERIAL] == remote_serial),
            None,
        )
        _LOGGER.debug("Received %s (verified=%s, known=%s)", event_type, result.valid, remote is not None)
        self._hass.bus.async_fire(
            BUS_EVENT_REMOTE,
            {"remote": remote.title if remote else None, "type": event_type,
             "channel_mask": result.channel_mask, "verified": result.valid},
        )
        if remote is None:
            self.recent_unknown.pop(remote_serial, None)
            self.recent_unknown[remote_serial] = seen
            while len(self.recent_unknown) > RECENT_UNKNOWN:
                self.recent_unknown.pop(next(iter(self.recent_unknown)))
            return
        async_dispatcher_send(
            self._hass, SIGNAL_REMOTE.format(self._entry.entry_id), remote.subentry_id, event_type,
            {"channel_mask": result.channel_mask, "verified": result.valid},
        )
        state = {"up": ShutterState.OPEN, "down": ShutterState.CLOSED, "shade": ShutterState.SHADE}.get(event_type)
        mask = 0
        for ch in remote.data.get(CONF_CHANNELS, []):
            mask |= 1 << (int(ch) - 1)
        if state and mask:
            self._entry.runtime_data.async_set_state(mask, state)
