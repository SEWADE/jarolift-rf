"""Jarolift RF: Jarolift (KeeLoq) shutters via a stateless ESPHome radio bridge."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

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

PLATFORMS = [Platform.BUTTON, Platform.COVER, Platform.SENSOR]


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
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JaroliftConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: JaroliftConfigEntry) -> None:
    """Options or subentries changed."""
    await hass.config_entries.async_reload(entry.entry_id)
