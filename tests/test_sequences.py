import json
from pathlib import Path

import pytest

from core import sequences as sq
from core import telegram as tg

VECTORS = json.loads((Path(__file__).parent / "vectors" / "reference_sequences.json").read_text())


def _target(v):
    if v["kind"] == "grp":
        return sq.Target.group(v["base"], v["arg"])
    return sq.Target.channel(v["base"], v["arg"])


def _expand(frame: sq.Frame) -> list[int]:
    seq: list[int] = []
    for rep in range(frame.repeats):
        seq += frame.pulses
        if rep < frame.repeats - 1:
            seq[-1] -= frame.gap_us
    return seq


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: f"{v['id']}-{v['kind']}-{v['cmd']}-{v['arg']}")
def test_matches_reference(v):
    steps = sq.steps_for(sq.Command(v["cmd"]), legacy_learn=bool(v["legacy"]))
    rendered = sq.render(steps, _target(v), v["counter"], v["msb"], v["lsb"])
    frames = [r for r in rendered if isinstance(r, sq.Frame)]
    pauses = [r for r in rendered if isinstance(r, sq.Pause)]

    assert len(frames) == len(v["frames"])
    for frame, ref in zip(frames, v["frames"]):
        seq = _expand(frame)
        assert seq[:-1] == ref["runs"]
        assert ref["tail_us"] >= -seq[-1] + frame.gap_us
        assert tg.airtime_us(frame.pulses, frame.repeats, frame.gap_us) == ref["end_us"]
    assert [p.ms * 1000 for p in pauses] == v["gaps_us"]
    assert v["counter_after"] == v["counter"] + sq.counters_needed(steps)
    assert [f.counter for f in frames] == list(range(v["counter"], v["counter"] + len(frames)))


def test_base_serial_limit():
    with pytest.raises(ValueError):
        tg.channel_serial(0x100000, 0)


def test_empty_group_rejected():
    with pytest.raises(ValueError):
        sq.Target.group(0x12345, 0)


def test_group_commands_only_simple():
    assert sq.Command.SET_SHADE not in sq.GROUP_COMMANDS
