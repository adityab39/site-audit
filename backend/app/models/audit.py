"""SQLAlchemy ORM models for the Site Audit AI application.

Cross-database compatibility
----------------------------
All column types are dialect-agnostic so the same model works with both
SQLite (local dev, zero setup) and PostgreSQL (Docker / production):

  Uuid        – native UUID on PostgreSQL,  CHAR(32) on SQLite
  JSON        – native JSON  on PostgreSQL,  TEXT     on SQLite
  LargeBinary – BYTEA        on PostgreSQL,  BLOB     on SQLite
  SAEnum      – native ENUM  on PostgreSQL,  VARCHAR  on SQLite

Tables
------
audit_results   – one row per audit job
category_scores – one row per scored category, linked to audit_results
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class AuditStatus(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditResult(Base):
    """One row per audit job.

    ``results`` is a JSON column with three nested keys::

        {
            "crawl":      { ... },
            "lighthouse": { ... },
            "analysis":   { ... }
        }

    ``screenshot`` stores the raw PNG bytes of the full-page screenshot
    in a separate column so the JSON ``results`` column stays compact.
    """

    __tablename__ = "audit_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="professional")
    status: Mapped[AuditStatus] = mapped_column(
        SAEnum(AuditStatus, name="auditstatus", create_type=True),
        nullable=False,
        default=AuditStatus.PENDING,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Denormalised quick-access columns (copied from results for fast queries)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Full collected data: crawl, lighthouse, and Claude analysis
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Full-page PNG screenshot (raw bytes, kept separate from JSON column)
    screenshot: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    category_scores: Mapped[list[CategoryScore]] = relationship(
        "CategoryScore",
        back_populates="audit_result",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<AuditResult id={self.id} url={self.url!r} "
            f"mode={self.mode!r} status={self.status}>"
        )


class CategoryScore(Base):
    """One row per scored category for a given audit."""

    __tablename__ = "category_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    audit_result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("audit_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    audit_result: Mapped[AuditResult] = relationship(
        "AuditResult",
        back_populates="category_scores",
    )

    def __repr__(self) -> str:
        return f"<CategoryScore category={self.category!r} score={self.score}>"
