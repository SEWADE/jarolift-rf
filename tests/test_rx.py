import json
from pathlib import Path
import random

import pytest

from core import rx
from core import sequences as sq
from core import telegram as tg

VECTORS = json.loads((Path(__file__).parent / "vectors" / "reference_sequences.json").read_text())
SIMPLE = [v for v in VECTORS if v["cmd"] in ("up", "down", "stop")]


def _first_repetition(runs: list[int]) -> list[int]:
    """Reference waveform up to the gap after the first repetition (receiver idle cuts there)."""
    for i, value in enumerate(runs):
        if value <= -10000:
            return runs[:i]  # last bit's space merges into the idle gap and is not reported
    return runs


@pytest.mark.parametrize("v", SIMPLE, ids=lambda v: f"{v['id']}-{v['kind']}-{v['cmd']}-{v['arg']}")
def test_decodes_reference_waveform(v):
    target = sq.Target.group(v["base"], v["arg"]) if v["kind"] == "grp" else sq.Target.channel(v["base"], v["arg"])
    telegram = rx.decode_pulses(_first_repetition(v["frames"][0]["runs"]))
    assert telegram is not None
    assert telegram.serial == target.serial
    result = rx.authenticate(telegram, v["msb"], v["lsb"])
    assert result.valid
    assert result.counter == v["counter"]
    assert result.channel_mask == target.disc_low | (target.disc_high << 8)
    assert telegram.button == {"up": 0x8, "down": 0x2, "stop": 0x4}[v["cmd"]]


def _telegram_pulses(counter=0x1234, channel=3):
    t = tg.build(tg.Button.UP, tg.channel_serial(0x0ABCD, channel), *tg.channel_disc(channel), counter, 1, 2)
    return t, tg.to_pulses(t)


def test_robust_against_jitter_noise_and_truncation():
    rnd = random.Random(1)
    t, pulses = _telegram_pulses()
    for _ in range(200):
        noisy = [p + rnd.randint(-120, 120) for p in pulses[rnd.randint(0, 20):-1]]
        noisy = [rnd.choice([300, 150, 900]) * rnd.choice([1, -1]) for _ in range(rnd.randint(0, 9))] + noisy
        got = rx.decode_pulses(noisy)
        assert got is not None and got.serial == t.serial and got.encrypted == t.encrypted


def test_noise_and_incomplete_frames_are_rejected():
    rnd = random.Random(2)
    for _ in range(500):
        noise = [rnd.randint(100, 5000) * (1 if i % 2 == 0 else -1) for i in range(rnd.randint(10, 300))]
        got = rx.decode_pulses(noise)
        if got is not None:  # an accidental structural match must still fail authentication
            assert not rx.authenticate(got, 1, 2).valid
    _, pulses = _telegram_pulses()
    assert rx.decode_pulses(pulses[:100]) is None


def test_wrong_keys_not_verified():
    t, pulses = _telegram_pulses()
    assert not rx.authenticate(rx.decode_pulses(pulses), 3, 4).valid
