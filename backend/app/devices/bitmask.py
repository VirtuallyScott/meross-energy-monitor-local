"""Channel bitmask helpers for device merged circuits (API spec §3.2)."""

from __future__ import annotations

from collections.abc import Iterable


def mask_to_channels(mask: int) -> list[int]:
    """Decode an ``emmerge`` bitmask into 1-based channel numbers."""
    if mask < 0:
        raise ValueError("mask must be non-negative")
    return [bit + 1 for bit in range(mask.bit_length()) if mask >> bit & 1]


def channels_to_mask(channels: Iterable[int]) -> int:
    """Encode 1-based channel numbers into an ``emmerge`` bitmask."""
    mask = 0
    for channel in channels:
        if channel < 1:
            raise ValueError(f"channel numbers are 1-based, got {channel}")
        mask |= 1 << (channel - 1)
    return mask
