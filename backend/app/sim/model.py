"""Deterministic synthetic load model for the simulator.

Power is a pure function of (channel, time), so history and live values always agree.
"""

from __future__ import annotations

import hashlib
import math

CHANNELS = 18
MAINS = {1: [2, 3, 4, 5, 6], 7: [8, 9, 10, 11, 12]}
PHASE_C = range(13, 19)
# (base watts, daily swing watts, peak hour UTC)
BRANCH_PROFILE: dict[int, tuple[float, float, float]] = {
    2: (380, 0, 0),
    8: (380, 0, 0),  # waterfall pump, constant
    3: (0, 0, 0),
    9: (0, 0, 0),  # unused pair
    4: (60, 40, 20),
    10: (55, 35, 21),  # misc
    5: (600, 250, 18),
    11: (600, 250, 18),  # main pool pump
    6: (900, 850, 20),
    12: (900, 850, 20),  # AC condenser
}
UNMETERED_W = 450.0
VOLTAGE_A, VOLTAGE_B = 124.2, 123.8


def _noise(channel: int, minute: int) -> float:
    digest = hashlib.blake2b(f"{channel}:{minute}".encode(), digest_size=2).digest()
    return (int.from_bytes(digest, "big") / 65535.0 - 0.5) * 0.04  # +/- 2%


def branch_power(channel: int, ts: float) -> float:
    base, swing, peak = BRANCH_PROFILE.get(channel, (0.0, 0.0, 0.0))
    if base == 0 and swing == 0:
        return 0.0
    hour = (ts / 3600.0) % 24
    daily = swing * math.cos((hour - peak) / 24 * 2 * math.pi)
    return max(0.0, (base + daily) * (1 + _noise(channel, int(ts // 60))))


def power(channel: int, ts: float) -> float:
    if channel in PHASE_C:
        return 0.0
    if channel in MAINS:
        return UNMETERED_W + sum(branch_power(c, ts) for c in MAINS[channel])
    return branch_power(channel, ts)


def voltage(channel: int) -> float:
    if channel in PHASE_C:
        return 0.09
    return VOLTAGE_A if channel <= 6 else VOLTAGE_B


def minute_row(channel: int, minute_start: int) -> list[float]:
    """One ``Em.Data.Get`` row in HISTORY_KEYS order."""
    samples = [power(channel, minute_start + s) for s in (0, 20, 40)]
    avg = sum(samples) / len(samples)
    v = voltage(channel)
    amps = [p / v if v > 1 else 0.0 for p in samples]
    energy = avg / 1000.0 / 60.0
    return [
        round(energy, 4),
        0.0,
        round(v + 0.2, 3),
        round(v - 0.2, 3),
        round(v, 3),
        round(max(amps), 3),
        round(min(amps), 3),
        round(sum(amps) / 3, 3),
        round(max(samples), 3),
        round(min(samples), 3),
        round(avg, 3),
        0.0,
        0.0,
        0.0,
    ]


def energy_since(channel: int, start: int, end: int) -> float:
    """kWh between two unix times, summed per minute."""
    total = 0.0
    for minute in range(start - start % 60, end, 60):
        total += power(channel, minute) / 1000.0 / 60.0
    return total
