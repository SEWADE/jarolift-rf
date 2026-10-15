import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.jarolift_rf.const import DOMAIN
from custom_components.jarolift_rf.core import sequences as sq

from .conftest import BRIDGE, DUMMY_LSB, DUMMY_MSB, DUMMY_SERIAL


def _entry(tx_enabled: bool = True, bundle_ms: int = 0) -> MockConfigEntry:
    subs = [
        ConfigSubentryData(subentry_type="channel", title=name, data={"channel": ch}, unique_id=f"channel_{ch}")
        for ch, name in [(1, "Küche - Esstisch klein"), (2, "Küche - Esstisch groß"), (5, "Wohnzimmer - Terrasse")]
    ]
    subs.append(ConfigSubentryData(subentry_type="group", title="Küche", data={"channels": [1, 2]}, unique_id=None))
    return MockConfigEntry(
        domain=DOMAIN,
        title="Jarolift",
        data={"bridge_service": BRIDGE, "master_msb": DUMMY_MSB, "master_lsb": DUMMY_LSB,
              "base_serial": DUMMY_SERIAL, "counter_start": 100},
        options={"tx_enabled": tx_enabled, "tx_power_dbm": 0, "bundle_ms": bundle_ms, "legacy_learn": False},
        subentries_data=subs,
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _expected(command: sq.Command, target: sq.Target, counter: int) -> list[sq.Frame]:
    rendered = sq.render(sq.steps_for(command), target, counter, DUMMY_MSB, DUMMY_LSB)
    return [r for r in rendered if isinstance(r, sq.Frame)]


async def test_entity_ids_match_old_controller(hass: HomeAssistant, bridge) -> None:
    await _setup(hass, _entry())
    for entity_id in ("cover.jarolift_kuche_esstisch_klein", "cover.jarolift_kuche_esstisch_gross",
                      "cover.jarolift_kuche", "cover.jarolift_wohnzimmer_terrasse"):
        assert hass.states.get(entity_id) is not None, entity_id


async def test_open_channel_sends_reference_telegram(hass: HomeAssistant, bridge) -> None:
    await _setup(hass, _entry())
    await hass.services.async_call("cover", "open_cover", {"entity_id": "cover.jarolift_kuche_esstisch_klein"},
                                   blocking=True)
    (frame,) = _expected(sq.Command.UP, sq.Target.channel(DUMMY_SERIAL, 0), 100)
    assert bridge.calls == [{"pulses": frame.pulses, "repeat": 2, "gap_us": 16000, "power_dbm": 0}]
    assert bridge.persisted_next == [101]  # reserved and written before sending
    assert hass.states.get("cover.jarolift_kuche_esstisch_klein").state == "open"


async def test_group_cover_sends_one_group_telegram(hass: HomeAssistant, bridge) -> None:
    await _setup(hass, _entry())
    await hass.services.async_call("cover", "close_cover", {"entity_id": "cover.jarolift_kuche"}, blocking=True)
    (frame,) = _expected(sq.Command.DOWN, sq.Target.group(DUMMY_SERIAL, 0b11), 100)
    assert [c["pulses"] for c in bridge.calls] == [frame.pulses]
    assert hass.states.get("cover.jarolift_kuche_esstisch_klein").state == "closed"
    assert hass.states.get("cover.jarolift_kuche_esstisch_gross").state == "closed"
    assert hass.states.get("cover.jarolift_kuche").state == "closed"


async def test_bundling_merges_parallel_commands(hass: HomeAssistant, bridge) -> None:
    await _setup(hass, _entry(bundle_ms=100))
    await hass.services.async_call(
        "cover", "open_cover",
        {"entity_id": ["cover.jarolift_kuche_esstisch_klein", "cover.jarolift_wohnzimmer_terrasse"]},
        blocking=True,
    )
    (frame,) = _expected(sq.Command.UP, sq.Target.group(DUMMY_SERIAL, 0b10001), 100)
    assert [c["pulses"] for c in bridge.calls] == [frame.pulses]


async def test_tx_disabled_sends_nothing(hass: HomeAssistant, bridge) -> None:
    await _setup(hass, _entry(tx_enabled=False))
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("cover", "open_cover", {"entity_id": "cover.jarolift_kuche"}, blocking=True)
    assert bridge.calls == []


async def test_bridge_error_consumes_counter(hass: HomeAssistant, bridge) -> None:
    entry = _entry()
    await _setup(hass, entry)
    bridge.fail = "boom"
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("cover", "open_cover", {"entity_id": "cover.jarolift_kuche"}, blocking=True)
    bridge.fail = None
    await hass.services.async_call("cover", "open_cover", {"entity_id": "cover.jarolift_kuche"}, blocking=True)
    assert bridge.persisted_next == [101, 102]  # never reuse a counter value
    assert entry.runtime_data.counter.next == 102


async def test_counter_survives_reload(hass: HomeAssistant, bridge) -> None:
    entry = _entry()
    await _setup(hass, entry)
    await hass.services.async_call("cover", "stop_cover", {"entity_id": "cover.jarolift_kuche"}, blocking=True)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.counter.next == 101


async def test_stop_jumps_queue(hass: HomeAssistant, bridge) -> None:
    await _setup(hass, _entry())
    gate = asyncio.Event()
    started = asyncio.Event()
    original = bridge.handle

    async def slow(call):
        await original(call)
        if len(bridge.calls) == 1:
            started.set()
            await gate.wait()

    hass.services.async_register("esphome", BRIDGE, slow)

    def call(service: str, entity_id: str):
        return hass.async_create_task(
            hass.services.async_call("cover", service, {"entity_id": entity_id}, blocking=True)
        )

    first = call("open_cover", "cover.jarolift_kuche_esstisch_klein")
    await started.wait()  # first command is on air
    rest = [call("close_cover", "cover.jarolift_kuche_esstisch_gross"),
            call("stop_cover", "cover.jarolift_wohnzimmer_terrasse")]
    await asyncio.sleep(0.05)
    gate.set()
    await asyncio.gather(first, *rest)
    assert [_button_of(c["pulses"]) for c in bridge.calls] == [0x8, 0x4, 0x2]


def _button_of(pulses: list[int]) -> int:
    data = pulses[26:26 + 128]
    bits = [1 if data[i] == 400 else 0 for i in range(0, 128, 2)]
    return sum(b << i for i, b in enumerate(bits[60:64]))
