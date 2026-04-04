import uuid
from datetime import datetime

from pydantic import BaseModel, HttpUrl, field_validator

from app.models.audit import AuditStatus


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AuditRequest(BaseModel):
    url: HttpUrl
    max_pages: int = 10
    include_lighthouse: bool = True

    @field_validator("max_pages")
    @classmethod
    def validate_max_pages(cls, v: int) -> int:
        if v < 1 or v > 50:
            raise ValueError("max_pages must be between 1 and 50")
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CategoryScoreSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    category: str
    score: float
    label: str | None
    details: dict | None


class AuditResultSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    url: str
    status: AuditStatus
    error_message: str | None
    ai_summary: str | None
    crawl_data: dict | None
    lighthouse_data: dict | None
    category_scores: list[CategoryScoreSchema]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AuditCreateResponse(BaseModel):
    job_id: uuid.UUID
    status: AuditStatus
    message: str


class AuditStatusResponse(BaseModel):
    model_config = {"from_attributes": True}

    job_id: uuid.UUID
    url: str
    status: AuditStatus
    error_message: str | None
    ai_summary: str | None
    category_scores: list[CategoryScoreSchema]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


# ---------------------------------------------------------------------------
# Health check schema
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str
