"""Runtime objects of a config entry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .bridge import EsphomeBridge
from .const import SIGNAL_COUNTER, SIGNAL_STATE
from .counter import CounterStore
from .scheduler import TxScheduler


class ShutterState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    SHADE = "shade"


@dataclass
class JaroliftRuntime:
    hass: HomeAssistant
    entry_id: str
    bridge: EsphomeBridge
    counter: CounterStore
    scheduler: TxScheduler
    hub_device_id: str = ""

    @callback
    def async_set_state(self, mask: int, state: ShutterState) -> None:
        """Assumed state of all channels in ``mask`` changed (sent or remote)."""
        async_dispatcher_send(self.hass, SIGNAL_STATE.format(self.entry_id), mask, state)

    @callback
    def async_counter_changed(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_COUNTER.format(self.entry_id))


type JaroliftConfigEntry = ConfigEntry[JaroliftRuntime]
