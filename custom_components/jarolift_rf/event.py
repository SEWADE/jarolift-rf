"""Remote control events (original Jarolift remotes received by the bridge)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SIGNAL_REMOTE, SUBENTRY_REMOTE
from .entity import JaroliftEntity
from .receiver import EVENT_TYPES
from .runtime import JaroliftConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: JaroliftConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_REMOTE:
            async_add_entities([RemoteEvent(entry, subentry)], config_subentry_id=subentry.subentry_id)


class RemoteEvent(JaroliftEntity, EventEntity):
    _attr_name = None
    _attr_translation_key = "remote"
    _attr_event_types = EVENT_TYPES

    def __init__(self, entry: JaroliftConfigEntry, subentry) -> None:
        super().__init__(entry, subentry)
        self._attr_unique_id = f"{entry.entry_id}_{subentry.subentry_id}_event"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_REMOTE.format(self._runtime.entry_id), self._handle)
        )

    @callback
    def _handle(self, subentry_id: str, event_type: str, attributes: dict[str, Any]) -> None:
        if subentry_id == self._subentry.subentry_id:
            self._trigger_event(event_type, attributes)
            self.async_write_ha_state()
