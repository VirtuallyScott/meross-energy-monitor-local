"""Sites, devices, channels and circuits (SRD 03 §2)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, utcnow, uuid7

CHANNEL_ROLES = ("grid_main", "solar", "battery", "branch", "unused")
_PLACEHOLDER_NAME = re.compile(r"^em_channel_\d+$")


class Site(Timestamped, Base):
    __tablename__ = "site"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(120))
    time_zone: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    address: Mapped[str | None] = mapped_column(Text)
    grid_circuit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    solar_circuit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    load_circuit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Device(Timestamped, Base):
    __tablename__ = "device"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"))
    dev_id: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    device_name: Mapped[str | None] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(300))
    model: Mapped[str] = mapped_column(String(32))
    fw_ver: Mapped[str | None] = mapped_column(String(32))
    hw_ver: Mapped[str | None] = mapped_column(String(32))
    mac: Mapped[str | None] = mapped_column(String(32))
    auth_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    credential_key_version: Mapped[int | None] = mapped_column(SmallInteger)
    credential_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_minute_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    channels: Mapped[list[Channel]] = relationship(
        back_populates="device", order_by="Channel.channel_no", lazy="selectin"
    )


class Channel(Base):
    __tablename__ = "channel"
    __table_args__ = (
        UniqueConstraint("device_id", "channel_no", name="uq_channel_device_no"),
        CheckConstraint(f"role in {CHANNEL_ROLES!r}", name="role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("device.id", ondelete="CASCADE"))
    channel_no: Mapped[int] = mapped_column(SmallInteger)
    device_label: Mapped[str | None] = mapped_column(String(120))
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), default="branch")
    phase_label: Mapped[str | None] = mapped_column(String(16))
    ct_factor: Mapped[float | None] = mapped_column(Float)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)

    device: Mapped[Device] = relationship(back_populates="channels")

    @property
    def name(self) -> str:
        """Local name, else the device's name, else the UI position label (A3, B4...).

        Unnamed channels report a placeholder like ``em_channel_3``; the device UI shows
        its position instead, so we do the same.
        """
        label = self.device_label
        if label and _PLACEHOLDER_NAME.match(label):
            label = None
        return self.display_name or label or self.phase_label or f"Channel {self.channel_no}"


class Circuit(Timestamped, Base):
    __tablename__ = "circuit"
    __table_args__ = (CheckConstraint("kind in ('device_merge','virtual')", name="kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16))
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("device.id", ondelete="CASCADE"))
    device_merge_mask: Mapped[int | None] = mapped_column(BigInteger)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    members: Mapped[list[CircuitMember]] = relationship(
        back_populates="circuit", cascade="all, delete-orphan", lazy="selectin"
    )


class CircuitMember(Base):
    __tablename__ = "circuit_member"
    __table_args__ = (CheckConstraint("sign in (1, -1)", name="sign"),)

    circuit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("circuit.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channel.id", ondelete="CASCADE"), primary_key=True
    )
    sign: Mapped[int] = mapped_column(SmallInteger, default=1)

    circuit: Mapped[Circuit] = relationship(back_populates="members")


class DeviceEvent(Base):
    __tablename__ = "device_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("device.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class DataGap(Base):
    __tablename__ = "data_gap"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("channel.id", ondelete="CASCADE"))
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cause: Mapped[str] = mapped_column(String(40))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
