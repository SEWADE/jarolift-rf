import json

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.jarolift_rf.const import (
    CONF_BASE_SERIAL,
    CONF_CHANNEL,
    CONF_CHANNELS,
    CONF_MASTER_LSB,
    CONF_MASTER_MSB,
    DOMAIN,
)

from .conftest import BRIDGE, DUMMY_LSB, DUMMY_MSB, DUMMY_SERIAL, ORIGINAL_CONFIG


async def test_abort_without_bridge(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_bridge"


async def test_import_original_config(hass: HomeAssistant, bridge) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"bridge_service": BRIDGE, "config_json": json.dumps(ORIGINAL_CONFIG), "counter_start": 1234},
    )
    assert result["step_id"] == "import_summary"
    assert "Wohnzimmer: 5, 6, 7, 8" in result["description_placeholders"]["derived"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data[CONF_MASTER_MSB] == DUMMY_MSB
    assert entry.data[CONF_MASTER_LSB] == DUMMY_LSB
    assert entry.data[CONF_BASE_SERIAL] == DUMMY_SERIAL
    assert "config_json" not in entry.data  # wifi passwords etc. are never stored
    subs = list(entry.subentries.values())
    channels = {s.data[CONF_CHANNEL]: s.title for s in subs if s.subentry_type == "channel"}
    groups = {s.title: s.data[CONF_CHANNELS] for s in subs if s.subentry_type == "group"}
    assert channels[1] == "Küche - Esstisch klein" and len(channels) == 8
    assert groups == {"Küche": [1, 2, 3, 4], "Wohnzimmer": [5, 6, 7, 8]}


async def test_manual_hex_and_validation(hass: HomeAssistant, bridge) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"bridge_service": BRIDGE, "master_msb": "0x1", "master_lsb": "2", "base_serial": "0x100000",
         "counter_start": 1},
    )
    assert result["errors"] == {"base_serial": "invalid_serial"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"bridge_service": BRIDGE, "master_msb": "0x1", "master_lsb": "2", "base_serial": "0xFFFFF",
         "counter_start": 1},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].data[CONF_BASE_SERIAL] == 0xFFFFF
    assert result["result"].data[CONF_MASTER_MSB] == 1
