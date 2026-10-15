"""Radio bridge adapters. The bridge only transmits raw pulses; it holds no state."""

from __future__ import annotations

import asyncio
from typing import Protocol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import BRIDGE_ACTION_SUFFIX, DOMAIN, ESPHOME_DOMAIN
from .core.sequences import Frame
from .core.telegram import airtime_us

TIMEOUT_MARGIN_S = 5.0


class BridgeError(HomeAssistantError):
    """Transmission failed or was not confirmed."""


class Bridge(Protocol):
    @property
    def available(self) -> bool: ...

    async def async_send(self, frame: Frame, power_dbm: int) -> None: ...


def find_esphome_bridges(hass: HomeAssistant) -> list[str]:
    """ESPHome actions that look like a Jarolift bridge (``<node>_send_raw``)."""
    services = hass.services.async_services_for_domain(ESPHOME_DOMAIN)
    return sorted(name for name in services if name.endswith(BRIDGE_ACTION_SUFFIX))


class EsphomeBridge:
    """Calls the user-defined ESPHome API action ``send_raw`` (supports_response: status).

    With ``status`` the ESPHome integration waits for the device's ``api.respond``
    and raises if it reports an error or times out.
    """

    def __init__(self, hass: HomeAssistant, service: str) -> None:
        self._hass = hass
        self.service = service

    @property
    def available(self) -> bool:
        return self._hass.services.has_service(ESPHOME_DOMAIN, self.service)

    async def async_send(self, frame: Frame, power_dbm: int) -> None:
        if not self.available:
            raise BridgeError(translation_domain=DOMAIN, translation_key="bridge_unavailable")
        timeout = airtime_us(frame.pulses, frame.repeats, frame.gap_us) / 1e6 + TIMEOUT_MARGIN_S
        try:
            async with asyncio.timeout(timeout):
                await self._hass.services.async_call(
                    ESPHOME_DOMAIN,
                    self.service,
                    {
                        "pulses": frame.pulses,
                        "repeat": frame.repeats,
                        "gap_us": frame.gap_us,
                        "power_dbm": power_dbm,
                    },
                    blocking=True,
                )
        except TimeoutError as err:
            raise BridgeError(translation_domain=DOMAIN, translation_key="bridge_timeout") from err
        except HomeAssistantError as err:
            raise BridgeError(
                translation_domain=DOMAIN,
                translation_key="bridge_failed",
                translation_placeholders={"error": str(err)},
            ) from err
