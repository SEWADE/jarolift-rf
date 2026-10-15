"""Fixtures for Home Assistant tests (pytest-homeassistant-custom-component)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from custom_components.jarolift_rf.counter import storage_key

BRIDGE = "jarolift_bridge_send_raw"
DUMMY_MSB = 0x1A2B3C4D
DUMMY_LSB = 0x5E6F7081
DUMMY_SERIAL = 0x12345

# Same structure as the original controller's config.json, dummy values only.
ORIGINAL_CONFIG = {
    "version": 2,
    "wifi": {"ssid": "x", "password": "secret"},
    "jaro": {
        "masterMSB": DUMMY_MSB,
        "masterLSB": DUMMY_LSB,
        "serial": DUMMY_SERIAL,
        "learn_mode": True,
        "ch_enable": [True] * 8 + [False] * 8,
        "ch_name": [
            "Room A - Window 1", "Room A - Window 2", "Room A - Door", "Room A - Side",
            "Room B - Window", "Room B - Left", "Room B - Right", "Room B - Door",
            "", "", "", "", "", "", "", "",
        ],
        "grp_enable": [True, True, False, False, False, False],
        "grp_name": ["Room A", "Room B", "", "", "", ""],
        "grp_mask": [15, 0, 0, 0, 0, 0],
        "remote_enable": [True] + [False] * 15,
        "remote_name": ["Remote X"] + [""] * 15,
        "remote_mask": [15] + [0] * 15,
        "remote_serial": [0x0B0B0] + [0] * 15,
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def isolated_config_dir(hass: HomeAssistant, tmp_path: Path) -> None:
    """The counter file lives in .storage; never share it between tests."""
    hass.config.config_dir = str(tmp_path)


class FakeBridge:
    """Stands in for the ESPHome action; records calls and the persisted counter."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[dict[str, Any]] = []
        self.persisted_next: list[int] = []
        self.fail: str | None = None

    async def handle(self, call: ServiceCall) -> None:
        path = Path(self.hass.config.path(".storage", storage_key(DUMMY_SERIAL)))
        self.persisted_next.append(json.loads(path.read_text())["data"]["next"])
        self.calls.append(dict(call.data))
        if self.fail:
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(self.fail)


@pytest.fixture
def bridge(hass: HomeAssistant) -> FakeBridge:
    fake = FakeBridge(hass)
    hass.services.async_register("esphome", BRIDGE, fake.handle, supports_response=SupportsResponse.NONE)
    return fake
