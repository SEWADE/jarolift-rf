"""KeeLoq block cipher (32-bit block, 64-bit key, 528 rounds).

Port of KeeloqLib by Frank Kienast (2010) as used in
dewenni/ESP32-Jarolift-Controller. See NOTICE.md.
"""

from __future__ import annotations

_NLF = 0x3A5C742E
_MASK32 = 0xFFFFFFFF
_ROUNDS = 528


def _bit(value: int, n: int) -> int:
    return (value >> n) & 1


def _key_bit(key_high: int, key_low: int, n: int) -> int:
    return _bit(key_low, n) if n < 32 else _bit(key_high, n - 32)


def encrypt(data: int, key_high: int, key_low: int) -> int:
    """Encrypt a 32-bit block."""
    x = data & _MASK32
    for r in range(_ROUNDS):
        index = (
            _bit(x, 1)
            | _bit(x, 9) << 1
            | _bit(x, 20) << 2
            | _bit(x, 26) << 3
            | _bit(x, 31) << 4
        )
        bit = _bit(x, 0) ^ _bit(x, 16) ^ _bit(_NLF, index) ^ _key_bit(key_high, key_low, r & 63)
        x = (x >> 1) | (bit << 31)
    return x


def decrypt(data: int, key_high: int, key_low: int) -> int:
    """Decrypt a 32-bit block."""
    x = data & _MASK32
    for r in range(_ROUNDS):
        index = (
            _bit(x, 0)
            | _bit(x, 8) << 1
            | _bit(x, 19) << 2
            | _bit(x, 25) << 3
            | _bit(x, 30) << 4
        )
        bit = _bit(x, 31) ^ _bit(x, 15) ^ _bit(_NLF, index) ^ _key_bit(key_high, key_low, (15 - r) & 63)
        x = ((x << 1) & _MASK32) | bit
    return x


def device_key(serial: int, master_msb: int, master_lsb: int) -> tuple[int, int]:
    """Derive the per-serial device key (msb, lsb) by KeeLoq 'normal learning'."""
    lsb = decrypt(serial | 0x20000000, master_msb, master_lsb)
    msb = decrypt(serial | 0x60000000, master_msb, master_lsb)
    return msb, lsb
