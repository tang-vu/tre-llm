"""Hardware probe resilience."""

from tre_llm.hardware import collect, fingerprint
from tre_llm.schemas import HardwareSnapshot


def test_collect_never_crashes():
    snap = collect()
    assert snap.os
    assert snap.cpu.logical_cores is None or snap.cpu.logical_cores > 0
    assert snap.collected_at


def test_fingerprint_stable():
    snap = collect()
    assert fingerprint(snap) == fingerprint(snap)


def test_missing_values_stay_unknown():
    snap = HardwareSnapshot(collected_at="t", os="linux")
    assert snap.ram_total_mb is None  # not a fake zero
    assert snap.gpus == []
