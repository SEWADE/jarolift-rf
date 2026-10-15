"""Jarolift shutters (assumed state: the last command sent or received)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import SIGNAL_STATE
from .core.sequences import Command
from .entity import JaroliftEntity
from .runtime import JaroliftConfigEntry, ShutterState

ATTR_SHADE = "shade"


async def async_setup_entry(
    hass: HomeAssistant, entry: JaroliftConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    for subentry in entry.subentries.values():
        async_add_entities([JaroliftCover(entry, subentry)], config_subentry_id=subentry.subentry_id)


class JaroliftCover(JaroliftEntity, CoverEntity, RestoreEntity):
    _attr_name = None
    _attr_assumed_state = True
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP

    def __init__(self, entry: JaroliftConfigEntry, subentry) -> None:
        super().__init__(entry, subentry)
        self._attr_unique_id = f"{entry.entry_id}_{subentry.subentry_id}_cover"
        self._attr_is_closed: bool | None = None
        self._shade = False
        self._member_states: dict[int, ShutterState] = {}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_SHADE: self._shade}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            if last.state in ("open", "closed"):
                self._attr_is_closed = last.state == "closed"
            self._shade = bool(last.attributes.get(ATTR_SHADE, False))
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_STATE.format(self._runtime.entry_id), self._handle_state)
        )

    @callback
    def _handle_state(self, mask: int, state: ShutterState) -> None:
        if not mask & self._mask:
            return
        if self._is_group:
            for bit in range(16):
                if mask & self._mask & (1 << bit):
                    self._member_states[bit] = state
            states = set(self._member_states.values())
            if len(self._member_states) < self._mask.bit_count():
                states.add(state)
            self._attr_is_closed = states == {ShutterState.CLOSED}
            self._shade = states == {ShutterState.SHADE}
        else:
            self._attr_is_closed = state is ShutterState.CLOSED
            self._shade = state is ShutterState.SHADE
        self.async_write_ha_state()

    async def _send(self, command: Command, state: ShutterState | None) -> None:
        await self._runtime.scheduler.async_send(command, self._mask, group=self._is_group)
        if state is not None:
            self._runtime.async_set_state(self._mask, state)

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._send(Command.UP, ShutterState.OPEN)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._send(Command.DOWN, ShutterState.CLOSED)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._send(Command.STOP, None)

    async def async_shade(self) -> None:
        await self._send(Command.SHADE, ShutterState.SHADE)
