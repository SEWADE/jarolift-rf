"""Diagnostic sensor: next rolling-code counter value."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SIGNAL_COUNTER
from .runtime import JaroliftConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: JaroliftConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([CounterSensor(entry)])


class CounterSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "next_counter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry: JaroliftConfigEntry) -> None:
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_next_counter"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> int:
        return self._runtime.counter.next

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_COUNTER.format(self._runtime.entry_id), self.async_write_ha_state
            )
        )
