"""Device operations shared by the API and the collector (DEV-*, CIR-003, DEV-010)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import utcnow
from app.db.models import Channel, Circuit, CircuitMember, Device, DeviceEvent
from app.devices import netguard
from app.devices.bitmask import mask_to_channels
from app.devices.credentials import decrypt_password
from app.devices.rpc import DeviceClient

log = logging.getLogger(__name__)

SUPPORTED_MODELS = {"em16p", "em06p"}
_CHANNEL_KEY = re.compile(r"^em:(\d{1,2})$")
_MERGE_KEY = re.compile(r"^emmerge:(\d+)$")
# Channels reading below this voltage have no phase reference (e.g. phase C in US split phase).
UNUSED_VOLTAGE_V = 5.0


@dataclass(frozen=True)
class ProbeResult:
    base_url: str
    info: dict[str, Any]


async def checked_client(raw_url: str, password: str | None = None) -> DeviceClient:
    """Normalize and SSRF-check an address, then return a client for it (SEC-040/041)."""
    settings = get_settings()
    base_url, host, _port = netguard.normalize_base_url(raw_url)
    await netguard.resolve_and_check(
        host, settings.device_allowed_cidrs, settings.device_blocked_cidrs
    )
    return DeviceClient(base_url=base_url, password=password, timeout=settings.device_timeout_s)


async def probe(raw_url: str, password: str | None = None) -> ProbeResult:
    """Call ``Refoss.DeviceInfo.Get`` and check the model (DEV-002)."""
    async with await checked_client(raw_url, password) as client:
        info = await client.device_info()
    model = str(info.get("model", "")).lower()
    if model not in SUPPORTED_MODELS or not info.get("dev_id"):
        raise ValueError(f"unsupported device model {model or 'unknown'!r}")
    return ProbeResult(client.base_url, info)


def device_password(device: Device) -> str | None:
    if device.credential_ciphertext is None:
        return None
    return decrypt_password(get_settings().device_cred_key, device.id, device.credential_ciphertext)


async def client_for(device: Device) -> DeviceClient:
    client = await checked_client(device.base_url, device_password(device))
    client.dev_id = device.dev_id
    return client


def channel_numbers(status: dict[str, Any]) -> list[int]:
    """Channel count comes from the status reply, not a hard-coded 18 (DEV-007)."""
    return sorted(int(m.group(1)) for key in status if (m := _CHANNEL_KEY.match(key)))


def phase_label(channel_no: int, total: int) -> str:
    """UI position label: A1..A6, B1..B6, C1..C6 for 18 channels (API spec §3.1)."""
    per_phase = 6 if total >= 18 else max(1, total // 3 or total)
    phase = "ABC"[min((channel_no - 1) // per_phase, 2)]
    return f"{phase}{(channel_no - 1) % per_phase + 1}"


async def sync_device(
    session: AsyncSession, device: Device, client: DeviceClient
) -> dict[str, int]:
    """Refresh identity, channels and device merges from the device (DEV-010).

    New channels get a role suggestion: ``unused`` when no voltage reference is seen (CIR-002).
    Local display names and roles set by users are never overwritten.
    """
    info = await client.device_info()
    status = await client.status()
    config = await client.config()
    merges = await client.merges()

    changes: dict[str, Any] = {}
    for attr, key in (
        ("device_name", "name"),
        ("fw_ver", "fw_ver"),
        ("hw_ver", "hw_ver"),
        ("mac", "mac"),
        ("auth_enabled", "auth_en"),
    ):
        value = info.get(key)
        if value is not None and getattr(device, attr) != value:
            changes[attr] = {"from": getattr(device, attr), "to": value}
            setattr(device, attr, value)

    numbers = channel_numbers(status)
    existing = {c.channel_no: c for c in device.channels}
    added = 0
    for no in numbers:
        cfg = config.get(f"em:{no}", {}) if isinstance(config, dict) else {}
        live = status.get(f"em:{no}", {})
        channel = existing.get(no)
        if channel is None:
            voltage = float(live.get("voltage") or 0)
            channel = Channel(
                device_id=device.id,
                channel_no=no,
                role="unused" if voltage < UNUSED_VOLTAGE_V else "branch",
                visible=voltage >= UNUSED_VOLTAGE_V,
                phase_label=phase_label(no, len(numbers)),
            )
            session.add(channel)
            device.channels.append(channel)
            existing[no] = channel
            added += 1
        channel.device_label = cfg.get("name") or channel.device_label
        channel.ct_factor = cfg.get("factor", channel.ct_factor)

    await session.flush()
    merge_count = await _sync_merges(session, device, merges, existing)
    if changes:
        session.add(DeviceEvent(device_id=device.id, kind="config_drift", detail=changes))
    return {"channels_added": added, "merges": merge_count, "identity_changes": len(changes)}


async def _sync_merges(
    session: AsyncSession,
    device: Device,
    merges: list[dict[str, Any]],
    channels: dict[int, Channel],
) -> int:
    """Mirror device merges as ``device_merge`` circuits (CIR-003)."""
    rows = await session.scalars(
        select(Circuit).where(Circuit.device_id == device.id, Circuit.kind == "device_merge")
    )
    current = {c.device_merge_mask: c for c in rows}
    seen: set[int] = set()
    for merge in merges:
        mask = int(merge.get("channels", 0))
        if mask <= 0:
            continue
        seen.add(mask)
        circuit = current.get(mask)
        if circuit is None:
            circuit = Circuit(
                site_id=device.site_id,
                kind="device_merge",
                device_id=device.id,
                device_merge_mask=mask,
                name=str(merge.get("name") or f"Merge {mask}"),
            )
            circuit.members = [
                CircuitMember(channel_id=channels[no].id, sign=1)
                for no in mask_to_channels(mask)
                if no in channels
            ]
            session.add(circuit)
        else:
            circuit.archived_at = None  # merge may have been re-created on the device
            if merge.get("name"):
                circuit.name = str(merge["name"])
    for existing_mask, existing in current.items():
        if existing_mask not in seen and existing.archived_at is None:
            existing.archived_at = utcnow()
    return len(seen)
