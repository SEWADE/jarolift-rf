"""Jarolift RF: Jarolift (KeeLoq) shutters via a stateless ESPHome radio bridge."""

from __future__ import annotations

import re

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .bridge import EsphomeBridge
from .const import (
    CONF_BASE_SERIAL,
    CONF_BRIDGE_SERVICE,
    CONF_COUNTER_START,
    CONF_MASTER_LSB,
    CONF_MASTER_MSB,
    DEFAULT_BUNDLE_MS,
    DEFAULT_TX_POWER,
    DOMAIN,
    OPT_BUNDLE_MS,
    OPT_LEGACY_LEARN,
    OPT_TX_ENABLED,
    OPT_TX_POWER,
)
from .counter import CounterStore
from .runtime import JaroliftConfigEntry, JaroliftRuntime
from .scheduler import TxScheduler, TxSettings
from .services import async_setup_services

PLATFORMS = [Platform.BUTTON, Platform.COVER, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: JaroliftConfigEntry) -> bool:
    data = entry.data
    counter = CounterStore(hass, data[CONF_BASE_SERIAL])
    await counter.async_load(minimum=data[CONF_COUNTER_START])
    bridge = EsphomeBridge(hass, data[CONF_BRIDGE_SERVICE])

    def settings() -> TxSettings:
        opts = entry.options
        return TxSettings(
            enabled=opts.get(OPT_TX_ENABLED, False),
            power_dbm=opts.get(OPT_TX_POWER, DEFAULT_TX_POWER),
            bundle_ms=opts.get(OPT_BUNDLE_MS, DEFAULT_BUNDLE_MS),
            legacy_learn=opts.get(OPT_LEGACY_LEARN, False),
        )

    runtime: JaroliftRuntime
    scheduler = TxScheduler(
        hass,
        bridge,
        counter,
        base_serial=data[CONF_BASE_SERIAL],
        master_msb=data[CONF_MASTER_MSB],
        master_lsb=data[CONF_MASTER_LSB],
        settings=settings,
        on_counter=lambda: runtime.async_counter_changed(),
    )
    runtime = JaroliftRuntime(hass, entry.entry_id, bridge, counter, scheduler)
    entry.runtime_data = runtime

    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Jarolift",
        model="KeeLoq RF (ESPHome bridge)",
    )
    runtime.hub_device_id = hub.id

    scheduler.start(entry)
    entry.async_on_unload(scheduler.async_stop)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_restore_entity_ids(hass, entry)
    runtime.async_counter_changed()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


@callback
def _async_restore_entity_ids(hass: HomeAssistant, entry: JaroliftConfigEntry) -> None:
    """Give covers their intended id (e.g. ``cover.jarolift_kitchen``) once it is free.

    While the old MQTT controller's entities still exist, HA assigns ``..._2``.
    Only such auto-suffixed ids are changed, never ids the user chose.
    """
    ent_reg = er.async_get(hass)
    blocked: list[str] = []
    for reg in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        subentry = entry.subentries.get(reg.config_subentry_id or "")
        if reg.domain != "cover" or subentry is None:
            continue
        desired = f"cover.{slugify(f'Jarolift {subentry.title}')}"
        if reg.entity_id == desired or not re.fullmatch(re.escape(desired) + r"_\d+", reg.entity_id):
            continue
        other = ent_reg.async_get(desired)
        if other is None and hass.states.get(desired) is None:
            ent_reg.async_update_entity(reg.entity_id, new_entity_id=desired)
        else:
            blocked.append(f"{desired} ({other.platform if other else 'state'}) -> {reg.entity_id}")
    issue_id = f"entity_id_blocked_{entry.entry_id}"
    if blocked:
        ir.async_create_issue(
            hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
            translation_key="entity_id_blocked", translation_placeholders={"entities": "\n".join(blocked)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


async def async_unload_entry(hass: HomeAssistant, entry: JaroliftConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: JaroliftConfigEntry) -> None:
    """Options or subentries changed."""
    await hass.config_entries.async_reload(entry.entry_id)
