"""Diagnostics. Keys and serial numbers are always redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_BASE_SERIAL, CONF_MASTER_LSB, CONF_MASTER_MSB, CONF_REMOTE_SERIAL
from .runtime import JaroliftConfigEntry

TO_REDACT = {CONF_MASTER_MSB, CONF_MASTER_LSB, CONF_BASE_SERIAL, CONF_REMOTE_SERIAL, "unique_id"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: JaroliftConfigEntry) -> dict[str, Any]:
    runtime = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "counter_next": runtime.counter.next,
        "bridge": {"service": runtime.bridge.service, "available": runtime.bridge.available},
        "queue_length": runtime.scheduler.queue_length,
        "last_received": _seen(runtime.receiver.last),
        "unknown_remotes_seen": len(runtime.receiver.recent_unknown),
    }


def _seen(seen) -> dict[str, Any] | None:
    if seen is None:
        return None
    # remote serial deliberately omitted
    return {"type": seen.event_type, "channel_mask": seen.channel_mask, "verified": seen.verified}
