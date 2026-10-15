"""Actions: programming commands (learn, endpoints, ...), shade, counter."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.service import async_extract_entity_ids

from .const import DOMAIN, SUBENTRY_CHANNEL
from .core.sequences import Command
from .counter import MAX_COUNTER
from .entity import subentry_mask
from .runtime import JaroliftConfigEntry, ShutterState

ATTR_CONFIRM = "confirm"
ATTR_POSITION = "position"
ATTR_VALUE = "value"
ATTR_CONFIG_ENTRY = "config_entry_id"

SERVICE_LEARN = "learn"
SERVICE_UNLEARN = "unlearn"
SERVICE_SET_ENDPOINT = "set_endpoint"
SERVICE_DELETE_ENDPOINT = "delete_endpoint"
SERVICE_SET_SHADE = "set_shade"
SERVICE_SHADE = "shade"
SERVICE_SET_COUNTER = "set_counter"

_CONFIRM = {vol.Required(ATTR_CONFIRM): vol.All(cv.boolean, vol.IsTrue())}
_POSITION = {vol.Required(ATTR_POSITION): vol.In(["up", "down"])}

_ENDPOINT = {
    (SERVICE_SET_ENDPOINT, "up"): Command.SET_END_UP,
    (SERVICE_SET_ENDPOINT, "down"): Command.SET_END_DOWN,
    (SERVICE_DELETE_ENDPOINT, "up"): Command.DELETE_END_UP,
    (SERVICE_DELETE_ENDPOINT, "down"): Command.DELETE_END_DOWN,
}


async def _targets(hass: HomeAssistant, call: ServiceCall, *, channels_only: bool):
    """Resolve the call target to (entry, mask, is_group) per Jarolift cover."""
    ent_reg = er.async_get(hass)
    out = []
    for entity_id in sorted(await async_extract_entity_ids(call)):
        reg = ent_reg.async_get(entity_id)
        if reg is None or reg.platform != DOMAIN or reg.domain != "cover" or not reg.config_subentry_id:
            continue
        entry: JaroliftConfigEntry | None = hass.config_entries.async_get_entry(reg.config_entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            continue
        subentry = entry.subentries[reg.config_subentry_id]
        is_group = subentry.subentry_type != SUBENTRY_CHANNEL
        if channels_only and is_group:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="channel_required",
                translation_placeholders={"entity_id": entity_id},
            )
        out.append((entry, subentry_mask(subentry), is_group))
    if not out:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_target")
    return out


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def program(call: ServiceCall) -> None:
        if call.service in (SERVICE_SET_ENDPOINT, SERVICE_DELETE_ENDPOINT):
            command = _ENDPOINT[(call.service, call.data[ATTR_POSITION])]
        else:
            command = {SERVICE_LEARN: Command.LEARN, SERVICE_UNLEARN: Command.UNLEARN,
                       SERVICE_SET_SHADE: Command.SET_SHADE}[call.service]
        for entry, mask, _ in await _targets(hass, call, channels_only=True):
            await entry.runtime_data.scheduler.async_send(command, mask)

    async def shade(call: ServiceCall) -> None:
        for entry, mask, is_group in await _targets(hass, call, channels_only=False):
            await entry.runtime_data.scheduler.async_send(Command.SHADE, mask, group=is_group)
            entry.runtime_data.async_set_state(mask, ShutterState.SHADE)

    async def set_counter(call: ServiceCall) -> None:
        entry: JaroliftConfigEntry | None = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY])
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_loaded")
        runtime = entry.runtime_data
        value = call.data[ATTR_VALUE]
        if value < runtime.counter.next:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="counter_backwards",
                translation_placeholders={"current": str(runtime.counter.next)},
            )
        await runtime.counter.async_set_next(value)
        runtime.async_counter_changed()

    target_schema = cv.make_entity_service_schema
    for name in (SERVICE_LEARN, SERVICE_UNLEARN):
        hass.services.async_register(DOMAIN, name, program, schema=target_schema(_CONFIRM))
    for name in (SERVICE_SET_ENDPOINT, SERVICE_DELETE_ENDPOINT):
        hass.services.async_register(DOMAIN, name, program, schema=target_schema({**_CONFIRM, **_POSITION}))
    hass.services.async_register(DOMAIN, SERVICE_SET_SHADE, program, schema=target_schema({}))
    hass.services.async_register(DOMAIN, SERVICE_SHADE, shade, schema=target_schema({}))
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_COUNTER,
        set_counter,
        schema=vol.Schema(
            {
                vol.Required(ATTR_CONFIG_ENTRY): cv.string,
                vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_COUNTER)),
                **_CONFIRM,
            }
        ),
    )
