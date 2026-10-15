"""Command sequences (which telegrams, how often, which pauses).

Mirrors the ``cmd*`` methods of dewenni/ESP32-Jarolift-Controller v1.9.0.
Every ``Tx`` step consumes one counter value. Pauses reproduce the effective
gap of the reference firmware, measured from the end of a transmission
(including its trailing 16 ms) to the start of the next one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from . import telegram as tg
from .telegram import Button

REPEATS_NORMAL = 2
REPEATS_SHADE = 20

# Reference: enterRx (2 ms) + setDeviceCounter (100 ms) + delay(300) + enterTx (2 ms)
PAUSE_STEP_MS = 404
# Reference learn: enterRx (2) + setDeviceCounter (100) + delay(1000) + enterTx (2)
PAUSE_LEARN_MS = 1104


class Command(StrEnum):
    UP = "up"
    DOWN = "down"
    STOP = "stop"
    SHADE = "shade"
    SET_SHADE = "set_shade"
    LEARN = "learn"
    UNLEARN = "unlearn"
    SET_END_UP = "set_endpoint_up"
    DELETE_END_UP = "delete_endpoint_up"
    SET_END_DOWN = "set_endpoint_down"
    DELETE_END_DOWN = "delete_endpoint_down"


GROUP_COMMANDS = frozenset({Command.UP, Command.DOWN, Command.STOP, Command.SHADE})


@dataclass(frozen=True)
class Tx:
    button: Button
    repeats: int


@dataclass(frozen=True)
class Pause:
    ms: int


Step = Tx | Pause


def _programming(first: Button, stops: int, last: Button, repeats: int) -> list[Step]:
    steps: list[Step] = [Tx(first, repeats)]
    for _ in range(stops):
        steps += [Pause(PAUSE_STEP_MS), Tx(Button.STOP, repeats)]
    steps += [Pause(PAUSE_STEP_MS), Tx(last, repeats)]
    return steps


def steps_for(command: Command, *, legacy_learn: bool = False) -> list[Step]:
    match command:
        case Command.UP:
            return [Tx(Button.UP, REPEATS_NORMAL)]
        case Command.DOWN:
            return [Tx(Button.DOWN, REPEATS_NORMAL)]
        case Command.STOP:
            return [Tx(Button.STOP, REPEATS_NORMAL)]
        case Command.SHADE:
            return [Tx(Button.STOP, REPEATS_SHADE)]
        case Command.SET_SHADE:
            steps: list[Step] = [Tx(Button.STOP, 1)]
            for _ in range(3):
                steps += [Pause(PAUSE_STEP_MS), Tx(Button.STOP, 1)]
            return steps
        case Command.LEARN:
            if legacy_learn:
                return [Tx(Button.LEARN_LEGACY, REPEATS_NORMAL)]
            return [Tx(Button.UP_DOWN, REPEATS_NORMAL), Pause(PAUSE_LEARN_MS), Tx(Button.STOP, REPEATS_NORMAL)]
        case Command.UNLEARN:
            return _programming(Button.UP_DOWN, 6, Button.UP, REPEATS_NORMAL)
        case Command.SET_END_UP:
            return _programming(Button.UP_DOWN, 2, Button.UP, 1)
        case Command.DELETE_END_UP:
            return _programming(Button.UP_DOWN, 4, Button.UP, 1)
        case Command.SET_END_DOWN:
            return _programming(Button.UP_DOWN, 2, Button.DOWN, 1)
        case Command.DELETE_END_DOWN:
            return _programming(Button.UP_DOWN, 4, Button.DOWN, 1)
    raise ValueError(command)


def counters_needed(steps: list[Step]) -> int:
    return sum(isinstance(s, Tx) for s in steps)


@dataclass(frozen=True)
class Frame:
    """One radio transmission, ready for the bridge."""

    pulses: list[int]
    repeats: int
    gap_us: int
    counter: int
    button: Button


Rendered = Frame | Pause


@dataclass(frozen=True)
class Target:
    """Serial and discrimination bytes for a channel or a group mask."""

    serial: int
    disc_low: int
    disc_high: int

    @classmethod
    def channel(cls, base_serial: int, channel: int) -> Target:
        return cls(tg.channel_serial(base_serial, channel), *tg.channel_disc(channel))

    @classmethod
    def group(cls, base_serial: int, mask: int) -> Target:
        if mask == 0:
            raise ValueError("group mask must not be empty")
        # The reference sends group telegrams with the serial of channel 1.
        return cls(tg.channel_serial(base_serial, 0), *tg.mask_disc(mask))


def render(
    steps: list[Step],
    target: Target,
    first_counter: int,
    master_msb: int,
    master_lsb: int,
) -> list[Rendered]:
    """Render steps with consecutive counters starting at ``first_counter``.

    The caller must have reserved ``counters_needed(steps)`` values.
    """
    out: list[Rendered] = []
    counter = first_counter
    for step in steps:
        if isinstance(step, Pause):
            out.append(step)
            continue
        t = tg.build(step.button, target.serial, target.disc_low, target.disc_high, counter, master_msb, master_lsb)
        out.append(Frame(tg.to_pulses(t), step.repeats, tg.REPEAT_GAP_US, counter, step.button))
        counter += 1
    return out
