import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class AuditStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditResult(Base):
    __tablename__ = "audit_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    status: Mapped[AuditStatus] = mapped_column(
        SAEnum(AuditStatus, name="auditstatus"),
        nullable=False,
        default=AuditStatus.PENDING,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Raw data collected during the audit
    crawl_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    lighthouse_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Full structured Claude analysis result
    # Contains: overall_score, summary, categories, priority_fixes, mode
    # NOTE: if adding this column to an existing DB, run an Alembic migration
    # or recreate the database container (fine for local dev).
    analysis_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Top-level AI summary (plain text copy of analysis_result.summary)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship to per-category scores
    category_scores: Mapped[list["CategoryScore"]] = relationship(
        "CategoryScore",
        back_populates="audit_result",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AuditResult id={self.id} url={self.url!r} status={self.status}>"


class CategoryScore(Base):
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

    audit_result: Mapped["AuditResult"] = relationship(
        "AuditResult",
        back_populates="category_scores",
    )

    def __repr__(self) -> str:
        return f"<CategoryScore category={self.category!r} score={self.score}>"
