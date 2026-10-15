"""Build the reference firmware code on the host and write test vectors.

Usage: python tests/reference/generate_vectors.py
Needs g++ (C++17). Output: tests/vectors/*.json (committed).

All keys and serials here are dummies. Never put real keys into this repo.
"""

from __future__ import annotations

import json
import random
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "vectors"
TX_PIN_LOW_IS_CARRIER = True  # see telegram.py docstring

# Dummy master keys / base serials (NOT real Jarolift keys)
KEYS = [(0x1A2B3C4D, 0x5E6F7081), (0x00000000, 0x00000001), (0xFFFFFFFF, 0xDEADBEEF)]
BASES = [0x12345, 0x00001, 0xFFFFF]
CHANNEL_CMDS = ["up", "down", "stop", "shade", "set_shade"]
GROUP_CMDS = ["up", "down", "stop", "shade"]
SERVICE_CMDS = [
    "learn",
    "unlearn",
    "set_endpoint_up",
    "delete_endpoint_up",
    "set_endpoint_down",
    "delete_endpoint_down",
]
GROUP_MASKS = [0x000F, 0x00F0, 0x0F0F, 0xFFFF, 0x8001, 0x0100]


def build(tmp: Path) -> tuple[Path, Path]:
    common = ["g++", "-std=c++17", "-O1", "-w", "-fpermissive", f"-I{HERE / 'upstream'}", f"-I{HERE / 'stubs'}"]
    harness = tmp / "harness"
    subprocess.run(
        [*common, str(HERE / "harness.cpp"), str(HERE / "upstream/JaroliftController.cpp"),
         str(HERE / "upstream/KeeloqLib.cpp"), "-o", str(harness)],
        check=True,
    )
    keeloq = tmp / "keeloq"
    subprocess.run(
        [*common, str(HERE / "keeloq_harness.cpp"), str(HERE / "upstream/KeeloqLib.cpp"), "-o", str(keeloq)],
        check=True,
    )
    return harness, keeloq


def cases() -> list[dict]:
    out: list[dict] = []

    def add(kind, cmd, arg, *, legacy=0, base=BASES[0], counter=0x1234, keys=KEYS[0]):
        out.append({"id": f"c{len(out)}", "kind": kind, "cmd": cmd, "arg": arg, "legacy": legacy,
                    "base": base, "counter": counter, "msb": keys[0], "lsb": keys[1]})

    for ch in range(16):
        for cmd in CHANNEL_CMDS:
            if cmd == "shade" and ch not in (0, 7, 8, 15):
                continue  # 20 repetitions: keep the vector file small
            add("ch", cmd, ch, counter=0x1000 + ch)
    for mask in GROUP_MASKS:
        for cmd in GROUP_CMDS:
            if cmd == "shade" and mask not in (0x00F0, 0xFFFF):
                continue
            add("grp", cmd, mask, counter=0x2000 + mask % 97)
    for ch in (0, 5, 9, 15):
        for cmd in SERVICE_CMDS:
            add("srv", cmd, ch, counter=0x3000 + ch)
        add("srv", "learn", ch, legacy=1, counter=0x3100 + ch)
    for base in BASES[1:]:
        for ch in (0, 15):
            add("ch", "up", ch, base=base, counter=1)
        add("grp", "down", 0x00F0, base=base, counter=0xFFFE)
    for keys in KEYS[1:]:
        for ch in (0, 3, 12):
            add("ch", "down", ch, keys=keys, counter=0x7FFF)
        add("grp", "stop", 0x0F0F, keys=keys, counter=0x0042)
    return out


def windows(events: list) -> dict:
    """Split recorded events into transmissions (as on-air pulses) and gaps."""
    frames, gaps_us = [], []
    prev_end = None
    i = 0
    while i < len(events):
        kind, t, _ = events[i]
        if kind != "tx":
            i += 1
            continue
        j = i + 1
        writes, end_of_tx = [], None
        while events[j][0] != "rx":
            k, tj, v = events[j]
            if k == "w":
                writes.append((tj, v))
            elif k == "d" and v == 16:
                end_of_tx = tj + 16000
            j += 1
        rx_t = events[j][1]
        runs: list[int] = []
        for (t0, lvl), (t1, _) in zip(writes, [*writes[1:], (rx_t, None)]):
            on = (lvl == 0) if TX_PIN_LOW_IS_CARRIER else (lvl == 1)
            d = (t1 - t0) * (1 if on else -1)
            if runs and (runs[-1] > 0) == (d > 0):
                runs[-1] += d
            elif d:
                runs.append(d)
        if prev_end is not None:
            gaps_us.append(writes[0][0] - prev_end)
        tail = runs.pop()  # last space incl. 16 ms (and any delay before enterRx)
        frames.append({"runs": runs, "tail_us": -tail, "end_us": end_of_tx - writes[0][0]})
        prev_end = end_of_tx
        i = j + 1
    return {"frames": frames, "gaps_us": gaps_us}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        harness, keeloq = build(Path(tmp))
        cs = cases()
        stdin = "".join(
            f"{c['id']} {c['kind']} {c['cmd']} {c['arg']} {c['legacy']} {c['base']} {c['counter']} {c['msb']} {c['lsb']}\n"
            for c in cs
        )
        res = subprocess.run([harness], input=stdin, capture_output=True, text=True, check=True).stdout
        by_id = {r["id"]: r for r in map(json.loads, res.splitlines())}
        vectors = []
        for c in cs:
            r = by_id[c["id"]]
            vectors.append({**c, "counter_after": r["counter_after"], **windows(r["events"])})
        (OUT / "reference_sequences.json").write_text(json.dumps(vectors, separators=(",", ":")) + "\n")

        rnd = random.Random(20261015)
        rows = [(rnd.getrandbits(32), rnd.getrandbits(32), rnd.getrandbits(32)) for _ in range(500)]
        rows += [(0, 0, 0), (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF), (0x01234567, 0x89ABCDEF, 0)]
        res = subprocess.run([keeloq], input="".join(f"{a} {b} {d}\n" for a, b, d in rows),
                             capture_output=True, text=True, check=True).stdout.split("\n")
        kv = [
            {"key_high": a, "key_low": b, "data": d, "encrypted": int(r.split()[0]), "decrypted": int(r.split()[1])}
            for (a, b, d), r in zip(rows, res)
        ]
        (OUT / "keeloq.json").write_text(json.dumps(kv, indent=0) + "\n")
    print(f"{len(vectors)} sequence vectors, {len(kv)} KeeLoq vectors -> {OUT}")


if __name__ == "__main__":
    main()
