import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.engine import utcnow


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Profile(Record, Base):
    __tablename__ = "profiles"
    name: Mapped[str] = mapped_column(String(200), default="My profile")
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class Source(Record, Base):
    __tablename__ = "sources"
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(String(30), default="json")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class Opportunity(Record, Base):
    __tablename__ = "opportunities"
    title: Mapped[str] = mapped_column(String(300))
    official_url: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    case_number: Mapped[str | None] = mapped_column(String(200))
    case_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    administrator: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(30), default="other")
    summary: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_payout: Mapped[float | None] = mapped_column(Numeric(12, 2))
    proof_required: Mapped[bool | None] = mapped_column(Boolean)
    rules: Mapped[list] = mapped_column(JSON, default=list)
    attestation_text: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_flags: Mapped[list] = mapped_column(JSON, default=list)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_notes: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"))


class Claim(Record, Base):
    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("profile_id", "opportunity_id"),)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"))
    status: Mapped[str] = mapped_column(String(40), default="prepared")
    packet: Mapped[dict] = mapped_column(JSON)
    packet_hash: Mapped[str] = mapped_column(String(64))
    approval: Mapped[dict | None] = mapped_column(JSON)
    confirmation: Mapped[dict | None] = mapped_column(JSON)
    expected_payment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_payout: Mapped[float | None] = mapped_column(Numeric(12, 2))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Audit(Record, Base):
    __tablename__ = "audit_log"
    action: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    actor: Mapped[str] = mapped_column(String(100), default="owner")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Evidence(Record, Base):
    __tablename__ = "evidence"
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"))
    reference: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)


class Notification(Record, Base):
    __tablename__ = "notifications"
    dedupe_key: Mapped[str] = mapped_column(String(250), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class SourceRun(Record, Base):
    __tablename__ = "source_runs"
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    status: Mapped[str] = mapped_column(String(30))
    imported: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
