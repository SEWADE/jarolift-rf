"""'Drive to shade position' button per channel and group."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .core.sequences import Command
from .entity import JaroliftEntity
from .runtime import JaroliftConfigEntry, ShutterState


async def async_setup_entry(
    hass: HomeAssistant, entry: JaroliftConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    for subentry in entry.subentries.values():
        async_add_entities([ShadeButton(entry, subentry)], config_subentry_id=subentry.subentry_id)


class ShadeButton(JaroliftEntity, ButtonEntity):
    _attr_translation_key = "shade"

    def __init__(self, entry: JaroliftConfigEntry, subentry) -> None:
        super().__init__(entry, subentry)
        self._attr_unique_id = f"{entry.entry_id}_{subentry.subentry_id}_shade"

    async def async_press(self) -> None:
        await self._runtime.scheduler.async_send(Command.SHADE, self._mask, group=self._is_group)
        self._runtime.async_set_state(self._mask, ShutterState.SHADE)
