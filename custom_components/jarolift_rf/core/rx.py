"""Decode received raw pulses into Jarolift telegrams and authenticate them.

Mirrors ``JaroliftController::processRxData`` of the reference firmware, but works on
on-air pulses (positive = carrier on) as delivered by ESPHome ``remote_receiver``:

    preamble (marks ~400) | header space ~3.9 ms | 72 bits, each mark + space

A bit is decided by its mark length (400 = '1', 800 = '0'), so the last bit decodes
even though its space merges into the idle gap and is not reported.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import keeloq

HEADER_MIN_US = 3000
HEADER_MAX_US = 4800
MARK_MIN_US = 200
MARK_SPLIT_US = 600
MARK_MAX_US = 1200
NUM_BITS = 72


@dataclass(frozen=True)
class RxTelegram:
    serial: int  # 28 bit
    button: int  # 4 bit
    encrypted: int  # 32 bit hopping code
    disc_high: int  # 8 group bits (unencrypted)


@dataclass(frozen=True)
class RxResult:
    telegram: RxTelegram
    valid: bool  # decrypted discrimination matches the serial (KeeLoq check)
    counter: int
    disc_low: int

    @property
    def channel_mask(self) -> int:
        """Channels of the sending remote (its own numbering), as in the reference."""
        return self.disc_low | (self.telegram.disc_high << 8)


def decode_pulses(pulses: list[int]) -> RxTelegram | None:
    """Find the header and read 72 bits. Returns None if no complete telegram is found."""
    for start, value in enumerate(pulses):
        if -HEADER_MAX_US <= value <= -HEADER_MIN_US:
            bits = _read_bits(pulses, start + 1)
            if bits is not None:
                return _to_telegram(bits)
    return None


def _read_bits(pulses: list[int], index: int) -> list[int] | None:
    bits: list[int] = []
    while len(bits) < NUM_BITS:
        if index >= len(pulses):
            return None
        mark = pulses[index]
        if not MARK_MIN_US <= mark <= MARK_MAX_US:
            return None
        bits.append(1 if mark < MARK_SPLIT_US else 0)
        if len(bits) < NUM_BITS:
            space = pulses[index + 1] if index + 1 < len(pulses) else 0
            if not -MARK_MAX_US <= space <= -MARK_MIN_US:
                return None
        index += 2
    return bits


def _to_telegram(bits: list[int]) -> RxTelegram:
    def field(first: int, count: int) -> int:
        return sum(bits[first + i] << i for i in range(count))

    return RxTelegram(
        serial=field(32, 28),
        button=field(60, 4),
        encrypted=field(0, 32),
        disc_high=field(64, 8),
    )


def authenticate(telegram: RxTelegram, master_msb: int, master_lsb: int) -> RxResult:
    key_msb, key_lsb = keeloq.device_key(telegram.serial, master_msb, master_lsb)
    plain = keeloq.decrypt(telegram.encrypted, key_msb, key_lsb)
    valid = (plain >> 16) & 0xFF == telegram.serial & 0xFF
    return RxResult(telegram, valid, plain & 0xFFFF, (plain >> 24) & 0xFF)
