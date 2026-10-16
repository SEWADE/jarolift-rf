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


async def _start(hass: HomeAssistant, path: str):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": path})


async def test_import_original_config(hass: HomeAssistant, bridge) -> None:
    result = await _start(hass, "import_config")
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"bridge_service": BRIDGE, "config_json": json.dumps(ORIGINAL_CONFIG), "counter_start": 1234},
    )
    assert result["step_id"] == "import_summary"
    assert "Room B: 5, 6, 7, 8" in result["description_placeholders"]["derived"]
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
    remotes = {s.title: dict(s.data) for s in subs if s.subentry_type == "remote"}
    assert remotes == {"Remote X": {"remote_serial": 0x0B0B0, "channels": [1, 2, 3, 4]}}
    assert channels[1] == "Room A - Window 1" and len(channels) == 8
    assert groups == {"Room A": [1, 2, 3, 4], "Room B": [5, 6, 7, 8]}


async def test_manual_hex_and_validation(hass: HomeAssistant, bridge) -> None:
    result = await _start(hass, "manual")
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


async def test_manual_new_installation(hass: HomeAssistant, bridge) -> None:
    result = await _start(hass, "manual")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"bridge_service": BRIDGE, "master_msb": "11", "master_lsb": "22", "counter_start": 1,
         "channel_names": "Left\n\nRight", "legacy_learn": True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert 1 <= entry.data[CONF_BASE_SERIAL] <= 0xFFFFF  # generated
    assert entry.options["legacy_learn"] is True
    assert {s.data[CONF_CHANNEL]: s.title for s in entry.subentries.values()} == {1: "Left", 3: "Right"}


async def _loaded_entry(hass: HomeAssistant, bridge):
    result = await _start(hass, "manual")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"bridge_service": BRIDGE, "master_msb": "11", "master_lsb": "22", "base_serial": "0x12345",
         "counter_start": 300, "channel_names": "Left\nRight"},
    )
    await hass.async_block_till_done()
    return result["result"]


async def test_reconfigure_keeps_secrets_when_empty(hass: HomeAssistant, bridge) -> None:
    entry = await _loaded_entry(hass, bridge)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id})
    assert result["description_placeholders"]["serial"] == "0x12345"
    assert result["description_placeholders"]["counter"] == "300"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bridge_service": BRIDGE, "master_lsb": "0x99"})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()  # let the scheduled reload finish
    assert entry.data[CONF_MASTER_MSB] == 11 and entry.data[CONF_MASTER_LSB] == 0x99
    assert entry.data[CONF_BASE_SERIAL] == 0x12345


async def test_reconfigure_new_serial_needs_counter(hass: HomeAssistant, bridge) -> None:
    entry = await _loaded_entry(hass, bridge)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bridge_service": BRIDGE, "base_serial": "0x54321"})
    assert result["errors"] == {"counter_start": "counter_required"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bridge_service": BRIDGE, "base_serial": "0x54321", "counter_start": 1})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_BASE_SERIAL] == 0x54321
    assert entry.runtime_data.counter.next == 1


async def test_channel_number_can_be_changed(hass: HomeAssistant, bridge) -> None:
    entry = await _loaded_entry(hass, bridge)
    sub = next(s for s in entry.subentries.values() if s.title == "Right")
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "channel"), context={"source": "reconfigure", "subentry_id": sub.subentry_id})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Right new", "channel": "5"})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries[sub.subentry_id].data == {"channel": 5}
    assert entry.subentries[sub.subentry_id].title == "Right new"
