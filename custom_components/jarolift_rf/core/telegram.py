"""Jarolift telegram: 64-bit KeeLoq word + 8 group bits, rendered as raw pulses.

Pulses use the on-air convention of ESPHome ``remote_transmitter.transmit_raw``:
positive = carrier on (mark), negative = carrier off (space), in microseconds.

Timing and bit layout follow dewenni/ESP32-Jarolift-Controller v1.9.0
(``JaroliftController::radioTx``). That firmware drives GDO0 low for carrier on
(PATABLE[0] = on, PATABLE[1] = 0), so its LOW periods are marks here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from . import keeloq

MAX_BASE_SERIAL = 0xFFFFF  # only 28 serial bits go on air: (base << 8) | channel
NUM_CHANNELS = 16

LEAD_US = 1150
SYNC_PULSES = 13
SYNC_MARK_US = 400
SYNC_SPACE_US = 380
HEADER_EXTRA_SPACE_US = 3500
SHORT_US = 400
LONG_US = 800
REPEAT_GAP_US = 16000


class Button(IntEnum):
    """Function codes (upper nibble of the 64-bit word)."""

    LEARN_LEGACY = 0x1
    DOWN = 0x2
    STOP = 0x4
    UP = 0x8
    UP_DOWN = 0xA  # also the learn code in the current learn mode


def channel_serial(base_serial: int, channel: int) -> int:
    """Serial number of a channel (0-based): ``(base << 8) | channel``."""
    validate_base_serial(base_serial)
    if not 0 <= channel < NUM_CHANNELS:
        raise ValueError(f"channel must be 0..{NUM_CHANNELS - 1}")
    return (base_serial << 8) | channel


def validate_base_serial(base_serial: int) -> None:
    if not 0 <= base_serial <= MAX_BASE_SERIAL:
        raise ValueError("base serial must be 0..0xFFFFF (20 bit)")


def channel_disc(channel: int) -> tuple[int, int]:
    """Discrimination (low, high) byte for a single channel."""
    return mask_disc(1 << channel)


def mask_disc(mask: int) -> tuple[int, int]:
    """Discrimination (low, high) byte for a 16-bit channel mask."""
    if not 0 <= mask <= 0xFFFF:
        raise ValueError("mask must be 16 bit")
    return mask & 0xFF, (mask >> 8) & 0xFF


@dataclass(frozen=True)
class Telegram:
    button: int
    serial: int
    disc_low: int
    disc_high: int
    counter: int
    encrypted: int

    @property
    def word(self) -> int:
        """64-bit word as built by the reference firmware.

        The reference ORs a 32-bit serial into bits 32..63; with a valid base
        serial (<= 20 bit) bits 60..63 hold only the button code.
        """
        return ((self.button << 60) | (self.serial << 32) | self.encrypted) & (2**64 - 1)

    def bits(self) -> list[int]:
        """72 bits in transmit order: 64-bit word LSB first, then disc_high LSB first."""
        word = self.word
        return [(word >> i) & 1 for i in range(64)] + [(self.disc_high >> i) & 1 for i in range(8)]


def hop_plain(serial: int, disc_low: int, counter: int) -> int:
    """Unencrypted hopping code: disc_low | serial low byte | 16-bit counter."""
    if not 0 <= counter <= 0xFFFF:
        raise ValueError("counter must be 16 bit")
    return (disc_low << 24) | ((serial & 0xFF) << 16) | counter


def build(
    button: int,
    serial: int,
    disc_low: int,
    disc_high: int,
    counter: int,
    master_msb: int,
    master_lsb: int,
) -> Telegram:
    key_msb, key_lsb = keeloq.device_key(serial, master_msb, master_lsb)
    encrypted = keeloq.encrypt(hop_plain(serial, disc_low, counter), key_msb, key_lsb)
    return Telegram(button, serial, disc_low, disc_high, counter, encrypted)


def to_pulses(telegram: Telegram) -> list[int]:
    """One repetition as raw pulses, ending with the last bit's space.

    Repeat with ``REPEAT_GAP_US`` of silence between repetitions.
    """
    pulses = [LEAD_US + SYNC_MARK_US, -SYNC_SPACE_US]
    for _ in range(SYNC_PULSES - 1):
        pulses += [SYNC_MARK_US, -SYNC_SPACE_US]
    pulses[-1] -= HEADER_EXTRA_SPACE_US
    for bit in telegram.bits():
        pulses += [SHORT_US, -LONG_US] if bit else [LONG_US, -SHORT_US]
    return pulses


def airtime_us(pulses: list[int], repeats: int, gap_us: int = REPEAT_GAP_US) -> int:
    return repeats * (sum(abs(p) for p in pulses) + gap_us)
