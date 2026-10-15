"""Shared entity helpers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_CHANNEL, CONF_CHANNELS, DOMAIN, SUBENTRY_CHANNEL, SUBENTRY_GROUP, SUBENTRY_REMOTE
from .runtime import JaroliftConfigEntry, JaroliftRuntime


def subentry_mask(subentry: ConfigSubentry) -> int:
    """Channel bit mask of a channel or group subentry (channels are 1-based in config)."""
    if subentry.subentry_type == SUBENTRY_CHANNEL:
        return 1 << (subentry.data[CONF_CHANNEL] - 1)
    mask = 0
    for ch in subentry.data.get(CONF_CHANNELS, []):
        mask |= 1 << (int(ch) - 1)
    return mask


class JaroliftEntity(Entity):
    """Entity of one channel or group; each has its own device named 'Jarolift <title>'.

    With has_entity_name and no entity name this yields entity ids like
    ``cover.jarolift_<channel_name>`` - the same scheme as the old MQTT controller.
    """

    _attr_has_entity_name = True

    def __init__(self, entry: JaroliftConfigEntry, subentry: ConfigSubentry) -> None:
        self._runtime: JaroliftRuntime = entry.runtime_data
        self._subentry = subentry
        self._is_group = subentry.subentry_type != SUBENTRY_CHANNEL
        self._mask = subentry_mask(subentry)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{subentry.subentry_id}")},
            name=f"Jarolift {subentry.title}",
            manufacturer="Jarolift",
            model={SUBENTRY_GROUP: "Gruppe", SUBENTRY_REMOTE: "Fernbedienung"}.get(
                subentry.subentry_type, f"Kanal {subentry.data.get(CONF_CHANNEL)}"
            ),
            via_device_id=self._runtime.hub_device_id,
        )


def is_shutter(subentry: ConfigSubentry) -> bool:
    return subentry.subentry_type in (SUBENTRY_CHANNEL, SUBENTRY_GROUP)
