"""SQLAlchemy ORM models for the Site Audit AI application.

Tables
------
audit_results   – one row per audit job; stores all collected data as JSONB
category_scores – one row per scored category, linked to an audit_results row

NOTE: columns were consolidated in this version. If you have an existing
      database, drop and recreate the container (dev) or run an Alembic
      migration (production).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Float, Integer, LargeBinary, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

    ``results`` is a JSONB column with three nested keys:

    .. code-block:: json

        {
            "crawl":      { ... },
            "lighthouse": { ... },
            "analysis":   { ... }
        }

    ``screenshot`` stores the raw PNG bytes of the full-page screenshot
    captured by Playwright. It is kept in a separate ``BYTEA`` column so
    that the JSONB ``results`` column stays compact and query-friendly.
    """

    __tablename__ = "audit_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
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

    # Human-readable error message if the pipeline failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quick-access columns (denormalised from results for efficient querying)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Full collected data — crawl, lighthouse, and Claude analysis
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Full-page PNG screenshot (raw bytes stored separately for JSONB efficiency)
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

    # Per-category scores (one row each for easy structured access)
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
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    audit_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("audit_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    audit_result: Mapped[AuditResult] = relationship(
        "AuditResult",
        back_populates="category_scores",
    )

    def __repr__(self) -> str:
        return f"<CategoryScore category={self.category!r} score={self.score}>"
