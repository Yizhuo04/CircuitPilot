"""Portable SQL tables. JSON uses JSONB on PostgreSQL; resource versions are immutable."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class CircuitVersion(Base):
    __tablename__ = "circuit_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    digest: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(16))
    netlist_json: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class BoardRecord(Base):
    __tablename__ = "board_models"
    __table_args__ = (UniqueConstraint("model_id", "revision"),)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(64))
    revision: Mapped[str] = mapped_column(String(64))
    geometry_json: Mapped[dict[str, Any]] = mapped_column(JSONType)


class PlanRecord(Base):
    __tablename__ = "assembly_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    circuit_version_id: Mapped[str] = mapped_column(
        ForeignKey("circuit_versions.id", ondelete="CASCADE"), index=True
    )
    board_model_id: Mapped[str] = mapped_column(String(64))
    board_revision: Mapped[str] = mapped_column(String(64))
    planner_version: Mapped[str] = mapped_column(String(40))
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class StepRecord(Base):
    __tablename__ = "assembly_steps"
    __table_args__ = (UniqueConstraint("plan_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("assembly_plans.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    instruction_json: Mapped[dict[str, Any]] = mapped_column(JSONType)


class ImageRecord(Base):
    __tablename__ = "images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    consent_for_training: Mapped[bool] = mapped_column(Boolean, default=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class UploadTicket(Base):
    __tablename__ = "upload_tickets"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    consent_for_training: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    __table_args__ = (Index("ix_verification_jobs", "status", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("assembly_plans.id", ondelete="CASCADE"), index=True
    )
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONType)
    results_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    model_version: Mapped[str] = mapped_column(String(64), default="manual-homography-1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Annotation(Base):
    __tablename__ = "ml_annotations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"), index=True)
    labels_json: Mapped[dict[str, Any]] = mapped_column(JSONType)
    review_status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PilotSession(Base):
    __tablename__ = "pilot_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    condition: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    help_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(String(2000), default="")
