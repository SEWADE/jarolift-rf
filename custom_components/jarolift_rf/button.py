"""Buttons: drive to shade position (channels and groups) and, disabled by default,
the programming commands of the original WebUI (channels only)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SUBENTRY_CHANNEL
from .core.sequences import Command
from .entity import JaroliftEntity, is_shutter
from .runtime import JaroliftConfigEntry, ShutterState


async def async_setup_entry(
    hass: HomeAssistant, entry: JaroliftConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    for subentry in entry.subentries.values():
        if not is_shutter(subentry):
            continue
        entities: list[ButtonEntity] = [ShadeButton(entry, subentry)]
        if subentry.subentry_type == SUBENTRY_CHANNEL:
            entities += [ProgramButton(entry, subentry, command) for command in PROGRAM_COMMANDS]
        async_add_entities(entities, config_subentry_id=subentry.subentry_id)


PROGRAM_COMMANDS = (
    Command.LEARN,
    Command.UNLEARN,
    Command.SET_SHADE,
    Command.SET_END_UP,
    Command.DELETE_END_UP,
    Command.SET_END_DOWN,
    Command.DELETE_END_DOWN,
)


class ShadeButton(JaroliftEntity, ButtonEntity):
    _attr_translation_key = "shade"

    def __init__(self, entry: JaroliftConfigEntry, subentry) -> None:
        super().__init__(entry, subentry)
        self._attr_unique_id = f"{entry.entry_id}_{subentry.subentry_id}_shade"

    async def async_press(self) -> None:
        await self._runtime.scheduler.async_send(Command.SHADE, self._mask, group=self._is_group)
        self._runtime.async_set_state(self._mask, ShutterState.SHADE)


class ProgramButton(JaroliftEntity, ButtonEntity):
    """Programming command; disabled by default so it cannot be pressed by accident or by Assist."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: JaroliftConfigEntry, subentry, command: Command) -> None:
        super().__init__(entry, subentry)
        self._command = command
        self._attr_translation_key = command.value
        self._attr_unique_id = f"{entry.entry_id}_{subentry.subentry_id}_{command.value}"

    async def async_press(self) -> None:
        await self._runtime.scheduler.async_send(self._command, self._mask)
