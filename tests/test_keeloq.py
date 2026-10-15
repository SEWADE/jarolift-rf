import json
from pathlib import Path

import pytest

from core import keeloq

VECTORS = json.loads((Path(__file__).parent / "vectors" / "keeloq.json").read_text())


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: f"{v['key_high']:08x}{v['key_low']:08x}-{v['data']:08x}")
def test_matches_reference(v):
    assert keeloq.encrypt(v["data"], v["key_high"], v["key_low"]) == v["encrypted"]
    assert keeloq.decrypt(v["data"], v["key_high"], v["key_low"]) == v["decrypted"]


@pytest.mark.parametrize("v", VECTORS[:50])
def test_roundtrip(v):
    enc = keeloq.encrypt(v["data"], v["key_high"], v["key_low"])
    assert keeloq.decrypt(enc, v["key_high"], v["key_low"]) == v["data"]
