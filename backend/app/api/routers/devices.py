"""Device registry (DEV-001 to DEV-017) and channel settings (CIR-001)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth import audit
from app.auth.deps import SessionDep, client_ip, ensure_site, require
from app.auth.permissions import P
from app.auth.principal import Principal
from app.core.config import get_settings
from app.core.errors import ApiError, envelope, not_found
from app.db.base import utcnow, uuid7
from app.db.models import Channel, Device, DeviceEvent, Site
from app.devices import service as device_service
from app.devices.credentials import KEY_VERSION, encrypt_password
from app.devices.netguard import AddressNotAllowedError
from app.devices.rpc import DeviceAuthError, DeviceRpcError
from app.panels import service as panel_service

router = APIRouter(tags=["devices"])
PASSWORD_MAX = 32  # device UI limit (API spec §2)


class ProbeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(min_length=1, max_length=300)
    password: str | None = Field(default=None, max_length=PASSWORD_MAX)


class DeviceIn(ProbeIn):
    site_id: uuid.UUID
    display_name: str | None = Field(default=None, max_length=120)


class DevicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    site_id: uuid.UUID | None = None
    enabled: bool | None = None


class CredentialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str | None = Field(default=None, min_length=1, max_length=PASSWORD_MAX)


class ChannelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, pattern=r"^(grid_main|solar|battery|branch|unused)$")
    phase_label: str | None = Field(default=None, max_length=16)
    visible: bool | None = None


def channel_out(c: Channel) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "channel_no": c.channel_no,
        "name": c.name,
        "device_label": c.device_label,
        "display_name": c.display_name,
        "role": c.role,
        "phase_label": c.phase_label,
        "ct_factor": c.ct_factor,
        "visible": c.visible,
        "panel_id": str(c.panel_id) if c.panel_id else None,
        "panel_slot": c.panel_slot,
        "breaker_poles": c.breaker_poles,
        "breaker_pole": c.breaker_pole,
        "breaker_amps": c.breaker_amps,
    }


def device_out(d: Device, detail: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(d.id),
        "site_id": str(d.site_id),
        "dev_id": d.dev_id,
        "name": d.display_name or d.device_name or d.dev_id,
        "display_name": d.display_name,
        "device_name": d.device_name,
        "base_url": d.base_url,
        "model": d.model,
        "fw_ver": d.fw_ver,
        "hw_ver": d.hw_ver,
        "auth_enabled": d.auth_enabled,
        "has_password": d.credential_ciphertext is not None,
        "password_updated_at": d.credential_updated_at.isoformat()
        if d.credential_updated_at
        else None,
        "enabled": d.enabled,
        "online": d.online,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "last_minute_ts": d.last_minute_ts.isoformat() if d.last_minute_ts else None,
        "version": d.version,
    }
    status = d.status_json or {}
    out["wifi_rssi"] = (status.get("wifi") or {}).get("rssi")
    out["uptime_s"] = (status.get("sys") or {}).get("uptime")
    if detail:
        out["channels"] = [channel_out(c) for c in d.channels]
        out["status"] = {k: v for k, v in status.items() if k.startswith("em:")}
    return out


def _device_error(exc: Exception) -> ApiError:
    if isinstance(exc, AddressNotAllowedError):
        return ApiError(422, "address_not_allowed", str(exc))
    if isinstance(exc, DeviceAuthError):
        return ApiError(422, "device_auth_failed", str(exc))
    if isinstance(exc, DeviceRpcError):
        return ApiError(502, "device_error", str(exc))
    return ApiError(422, "device_unsupported", str(exc))


async def _load(session: SessionDep, principal: Principal, perm: P, device_id: uuid.UUID) -> Device:
    device = await session.get(Device, device_id)
    if device is None or device.archived_at is not None:
        raise not_found("device")
    ensure_site(principal, perm, device.site_id, "device")
    return device


@router.post("/devices/probe")
async def probe_device(
    body: ProbeIn, _p: Principal = Depends(require(P.DEVICE_MANAGE))
) -> dict[str, Any]:
    try:
        result = await device_service.probe(body.address, body.password)
    except (ValueError, DeviceRpcError) as exc:
        raise _device_error(exc) from exc
    info = result.info
    return envelope(
        {
            "base_url": result.base_url,
            "dev_id": info.get("dev_id"),
            "name": info.get("name"),
            "model": info.get("model"),
            "fw_ver": info.get("fw_ver"),
            "auth_enabled": bool(info.get("auth_en")),
        }
    )


@router.get("/devices")
async def list_devices(
    session: SessionDep,
    site_id: uuid.UUID | None = None,
    principal: Principal = Depends(require(P.DEVICE_READ)),
) -> dict[str, Any]:
    stmt = select(Device).where(Device.archived_at.is_(None)).order_by(Device.id)
    scope = principal.sites_with(P.DEVICE_READ)
    if scope is not None:
        stmt = stmt.where(Device.site_id.in_(scope))
    if site_id is not None:
        stmt = stmt.where(Device.site_id == site_id)
    return envelope([device_out(d, detail=True) for d in await session.scalars(stmt)])


@router.post("/devices", status_code=201)
async def create_device(
    body: DeviceIn,
    request: Request,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> dict[str, Any]:
    if await session.get(Site, body.site_id) is None:
        raise not_found("site")
    ensure_site(principal, P.DEVICE_MANAGE, body.site_id, "site")
    if body.password and not principal.has(P.DEVICE_CREDENTIAL, body.site_id):
        raise ApiError(403, "forbidden", "requires device:credential")
    try:
        result = await device_service.probe(body.address, body.password)
    except (ValueError, DeviceRpcError) as exc:
        raise _device_error(exc) from exc
    dev_id = str(result.info["dev_id"])
    existing = await session.scalar(select(Device).where(Device.dev_id == dev_id))
    if existing is not None:  # DEV-003
        raise ApiError(
            409,
            "duplicate_device",
            f"device {dev_id} is already registered (id {existing.id}); update its address instead",
        )
    device = Device(
        id=uuid7(),
        site_id=body.site_id,
        dev_id=dev_id,
        display_name=body.display_name,
        device_name=result.info.get("name"),
        base_url=result.base_url,
        model=str(result.info.get("model")),
        fw_ver=result.info.get("fw_ver"),
        hw_ver=result.info.get("hw_ver"),
        mac=result.info.get("mac"),
        auth_enabled=bool(result.info.get("auth_en")),
        channels=[],
    )
    if body.password:
        _set_password(device, body.password)
    session.add(device)
    await session.flush()
    await _try_sync(session, device)
    await audit.record(
        session,
        "device.create",
        principal=principal,
        source_ip=client_ip(request),
        resource_type="device",
        resource_id=device.id,
        site_id=device.site_id,
        detail={"dev_id": dev_id, "base_url": device.base_url},
    )
    await session.commit()
    return envelope(device_out(device, detail=True))


def _set_password(device: Device, password: str | None) -> None:
    if password is None:
        device.credential_ciphertext = None
        device.credential_key_version = None
    else:
        key = get_settings().device_cred_key
        device.credential_ciphertext = encrypt_password(key, device.id, password)
        device.credential_key_version = KEY_VERSION
    device.credential_updated_at = utcnow()


async def _try_sync(session: SessionDep, device: Device) -> dict[str, int] | None:
    try:
        async with await device_service.client_for(device) as client:
            return await device_service.sync_device(session, device, client)
    except (ValueError, DeviceRpcError) as exc:
        session.add(
            DeviceEvent(device_id=device.id, kind="sync_failed", detail={"error": str(exc)[:300]})
        )
        return None


@router.get("/devices/{device_id}")
async def get_device(
    device_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_READ)),
) -> dict[str, Any]:
    return envelope(device_out(await _load(session, principal, P.DEVICE_READ, device_id), True))


@router.patch("/devices/{device_id}")
async def update_device(
    device_id: uuid.UUID,
    body: DevicePatch,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> dict[str, Any]:
    device = await _load(session, principal, P.DEVICE_MANAGE, device_id)
    changes = body.model_dump(exclude_unset=True)
    if "address" in changes:
        try:
            result = await device_service.probe(
                changes.pop("address"), device_service.device_password(device)
            )
        except (ValueError, DeviceRpcError) as exc:
            raise _device_error(exc) from exc
        if result.info.get("dev_id") != device.dev_id:  # DEV-005 identity match
            raise ApiError(409, "identity_mismatch", "a different device answers at that address")
        device.base_url = result.base_url
    if "site_id" in changes:
        ensure_site(principal, P.DEVICE_MANAGE, changes["site_id"], "site")
        if changes["site_id"] != device.site_id:
            for channel in device.channels:  # panels belong to the old site
                panel_service.clear(channel)
    for key, value in changes.items():
        setattr(device, key, value)
    device.version += 1
    await audit.record(
        session,
        "device.update",
        principal=principal,
        resource_type="device",
        resource_id=device.id,
        site_id=device.site_id,
        detail={k: str(v) for k, v in body.model_dump(exclude_unset=True).items()},
    )
    await session.commit()
    return envelope(device_out(device, detail=True))


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    device_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> None:
    """Archive the device and stop collection; history is kept (DEV-009)."""
    device = await _load(session, principal, P.DEVICE_MANAGE, device_id)
    device.archived_at = utcnow()
    device.enabled = False
    await audit.record(
        session,
        "device.delete",
        principal=principal,
        resource_type="device",
        resource_id=device.id,
        site_id=device.site_id,
    )
    await session.commit()


@router.put("/devices/{device_id}/credential", status_code=204)
async def set_credential(
    device_id: uuid.UUID,
    body: CredentialIn,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_CREDENTIAL)),
) -> None:
    device = await _load(session, principal, P.DEVICE_CREDENTIAL, device_id)
    _set_password(device, body.password)
    await audit.record(
        session,
        "device.credential",
        principal=principal,
        resource_type="device",
        resource_id=device.id,
        site_id=device.site_id,
        detail={"cleared": body.password is None},
    )
    await session.commit()


@router.post("/devices/{device_id}/test")
async def test_device(
    device_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> dict[str, Any]:
    device = await _load(session, principal, P.DEVICE_MANAGE, device_id)
    started = time.perf_counter()
    try:
        async with await device_service.client_for(device) as client:
            info = await client.device_info()
            await client.status()
    except (ValueError, DeviceRpcError) as exc:
        return envelope({"ok": False, "error": _device_error(exc).message})
    latency_ms = round((time.perf_counter() - started) * 1000)
    same = info.get("dev_id") == device.dev_id
    return envelope(
        {
            "ok": same,
            "identity_match": same,
            "latency_ms": latency_ms,
            "auth_enabled": bool(info.get("auth_en")),
        }
    )


@router.post("/devices/{device_id}/sync")
async def sync_device(
    device_id: uuid.UUID,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> dict[str, Any]:
    device = await _load(session, principal, P.DEVICE_MANAGE, device_id)
    result = await _try_sync(session, device)
    await session.commit()
    if result is None:
        raise ApiError(502, "device_error", "sync failed; see device events")
    return envelope(result)


@router.get("/devices/{device_id}/events")
async def device_events(
    device_id: uuid.UUID,
    session: SessionDep,
    limit: int = 100,
    principal: Principal = Depends(require(P.DEVICE_READ)),
) -> dict[str, Any]:
    await _load(session, principal, P.DEVICE_READ, device_id)
    rows = await session.scalars(
        select(DeviceEvent)
        .where(DeviceEvent.device_id == device_id)
        .order_by(DeviceEvent.ts.desc())
        .limit(min(max(limit, 1), 500))
    )
    return envelope([{"ts": e.ts.isoformat(), "kind": e.kind, "detail": e.detail} for e in rows])


@router.patch("/channels/{channel_id}")
async def update_channel(
    channel_id: uuid.UUID,
    body: ChannelPatch,
    session: SessionDep,
    principal: Principal = Depends(require(P.DEVICE_MANAGE)),
) -> dict[str, Any]:
    channel = await session.get(Channel, channel_id)
    if channel is None:
        raise not_found("channel")
    device = await _load(session, principal, P.DEVICE_MANAGE, channel.device_id)
    changes = device_service.channel_changes(channel.role, body.model_dump(exclude_unset=True))
    for key, value in changes.items():
        setattr(channel, key, value)
    await audit.record(
        session,
        "channel.update",
        principal=principal,
        resource_type="channel",
        resource_id=channel.id,
        site_id=device.site_id,
        detail=changes,
    )
    await session.commit()
    return envelope(channel_out(channel))
