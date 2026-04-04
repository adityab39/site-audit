import uuid
from datetime import datetime
from typing import Any

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
    analysis_result: dict | None
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

    # Plain-text executive summary
    ai_summary: str | None

    # Full Claude analysis (overall_score, categories, priority_fixes, mode)
    overall_score: int | None = None
    analysis_result: dict | None = None

    category_scores: list[CategoryScoreSchema]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


# ---------------------------------------------------------------------------
# Lighthouse schemas
# ---------------------------------------------------------------------------


class LighthouseScores(BaseModel):
    """Per-category Lighthouse scores on a 0–100 scale."""

    performance_score: float | None = None
    accessibility_score: float | None = None
    best_practices_score: float | None = None
    seo_score: float | None = None


class CoreWebVitals(BaseModel):
    """Lab-measured Core Web Vitals and related timing metrics.

    Units
    -----
    largest_contentful_paint  seconds
    first_input_delay         milliseconds (max-potential-FID proxy)
    cumulative_layout_shift   unitless score
    first_contentful_paint    seconds
    time_to_interactive       seconds
    speed_index               seconds
    total_blocking_time       milliseconds
    """

    largest_contentful_paint: float | None = None
    first_input_delay: float | None = None
    cumulative_layout_shift: float | None = None
    first_contentful_paint: float | None = None
    time_to_interactive: float | None = None
    speed_index: float | None = None
    total_blocking_time: float | None = None


class PageStats(BaseModel):
    """Aggregate resource counts and byte totals for the audited page."""

    total_page_size_bytes: int | None = None
    total_requests: int | None = None
    number_of_scripts: int | None = None
    number_of_stylesheets: int | None = None
    number_of_images: int | None = None
    dom_size: int | None = None


class LargeImageItem(BaseModel):
    """A single oversized or poorly optimised image."""

    url: str
    total_bytes: int | None = None
    wasted_bytes: int | None = None


class Diagnostics(BaseModel):
    """Actionable performance and optimisation diagnostics."""

    render_blocking_resources: list[str] = []
    large_images: list[LargeImageItem] = []
    unused_javascript_bytes: int | None = None
    unused_css_bytes: int | None = None


class LighthouseResultSchema(BaseModel):
    """Full structured result returned by the Lighthouse service."""

    url: str
    lighthouse_version: str | None = None
    fetch_time: str | None = None
    error: str | None = None
    scores: LighthouseScores = LighthouseScores()
    core_web_vitals: CoreWebVitals = CoreWebVitals()
    page_stats: PageStats = PageStats()
    diagnostics: Diagnostics = Diagnostics()

    @classmethod
    def from_service_dict(cls, data: dict[str, Any]) -> "LighthouseResultSchema":
        """Construct from the raw dict returned by :func:`run_lighthouse`."""
        return cls(
            url=data.get("url", ""),
            lighthouse_version=data.get("lighthouse_version"),
            fetch_time=data.get("fetch_time"),
            error=data.get("error"),
            scores=LighthouseScores(**data.get("scores", {})),
            core_web_vitals=CoreWebVitals(**data.get("core_web_vitals", {})),
            page_stats=PageStats(**data.get("page_stats", {})),
            diagnostics=Diagnostics(
                render_blocking_resources=data.get("diagnostics", {}).get(
                    "render_blocking_resources", []
                ),
                large_images=[
                    LargeImageItem(**img)
                    for img in data.get("diagnostics", {}).get("large_images", [])
                ],
                unused_javascript_bytes=data.get("diagnostics", {}).get(
                    "unused_javascript_bytes"
                ),
                unused_css_bytes=data.get("diagnostics", {}).get("unused_css_bytes"),
            ),
        )


# ---------------------------------------------------------------------------
# Health check schema
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str
