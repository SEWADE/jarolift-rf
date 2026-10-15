from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jarolift_rf.const import DOMAIN, RX_EVENT
from custom_components.jarolift_rf.core import telegram as tg

from .conftest import BRIDGE, DUMMY_LSB, DUMMY_MSB, DUMMY_SERIAL

REMOTE_BASE = 0x0A1B2  # dummy remote serial >> 8


def _entry() -> MockConfigEntry:
    subs = [
        ConfigSubentryData(subentry_type="channel", title=n, data={"channel": c}, unique_id=f"channel_{c}")
        for c, n in [(1, "Room A - Window 1"), (2, "Room A - Window 2")]
    ]
    subs.append(ConfigSubentryData(subentry_type="remote", title="Remote A",
                                   data={"remote_serial": REMOTE_BASE, "channels": [1, 2]}, unique_id="r"))
    return MockConfigEntry(
        domain=DOMAIN, title="Jarolift",
        data={"bridge_service": BRIDGE, "master_msb": DUMMY_MSB, "master_lsb": DUMMY_LSB,
              "base_serial": DUMMY_SERIAL, "counter_start": 1},
        options={"tx_enabled": False}, subentries_data=subs,
    )


def _pulses(base: int, button: tg.Button, counter: int, channel: int = 0) -> str:
    t = tg.build(button, (base << 8) | channel, *tg.channel_disc(channel), counter, DUMMY_MSB, DUMMY_LSB)
    return ",".join(map(str, tg.to_pulses(t)[:-1]))


async def _setup(hass: HomeAssistant):
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_known_remote_event_and_state(hass: HomeAssistant, bridge) -> None:
    await _setup(hass)
    events = []
    hass.bus.async_listen("jarolift_rf_remote", lambda e: events.append(e.data))
    for _ in range(3):  # one press = several repetitions with the same counter
        hass.bus.async_fire(RX_EVENT, {"pulses": _pulses(REMOTE_BASE, tg.Button.DOWN, 77)})
    await hass.async_block_till_done()
    state = hass.states.get("event.jarolift_remote_a")
    assert state.attributes["event_type"] == "down"
    assert state.attributes["verified"] is True
    assert len(events) == 1 and events[0]["remote"] == "Remote A"
    assert hass.states.get("cover.jarolift_room_a_window_1").state == "closed"
    assert bridge.calls == []  # receiving never transmits


async def test_long_stop_press_is_shade(hass: HomeAssistant, bridge) -> None:
    await _setup(hass)
    for _ in range(12):
        hass.bus.async_fire(RX_EVENT, {"pulses": _pulses(REMOTE_BASE, tg.Button.STOP, 90)})
    await hass.async_block_till_done()
    assert hass.states.get("event.jarolift_remote_a").attributes["event_type"] == "shade"
    assert hass.states.get("cover.jarolift_room_a_window_1").attributes["shade"] is True


async def test_unknown_remote_can_be_added(hass: HomeAssistant, bridge) -> None:
    entry = await _setup(hass)
    hass.bus.async_fire(RX_EVENT, {"pulses": _pulses(0x0C0DE, tg.Button.UP, 5)})
    await hass.async_block_till_done()
    result = await hass.config_entries.subentries.async_init((entry.entry_id, "remote"), context={"source": "user"})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Remote B", "source": str(0x0C0DE), "channels": ["2"]})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    sub = next(s for s in entry.subentries.values() if s.title == "Remote B")
    assert sub.data == {"remote_serial": 0x0C0DE, "channels": [2]}


async def test_own_serial_received_raises_issue(hass: HomeAssistant, bridge) -> None:
    entry = await _setup(hass)
    hass.bus.async_fire(RX_EVENT, {"pulses": _pulses(DUMMY_SERIAL, tg.Button.UP, 3)})
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"foreign_sender_{entry.entry_id}")


async def test_garbage_is_ignored(hass: HomeAssistant, bridge) -> None:
    await _setup(hass)
    hass.bus.async_fire(RX_EVENT, {"pulses": "1,2,x"})
    hass.bus.async_fire(RX_EVENT, {"pulses": "400,-400," * 100})
    await hass.async_block_till_done()
    assert hass.states.get("event.jarolift_remote_a").state == "unknown"
