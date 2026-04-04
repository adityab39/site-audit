"""API route definitions for Site Audit AI."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis
from app.config import get_settings
from app.database import get_db, get_redis
from app.models.audit import AuditResult, AuditStatus, CategoryScore
from app.schemas.audit import (
    AuditCreateResponse,
    AuditRequest,
    AuditStatusResponse,
    HealthResponse,
)
from app.services.analyzer import run_analysis
from app.services.crawler import run_crawl
from app.services.lighthouse import run_lighthouse

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> HealthResponse:
    """Return the liveness status of the application and its dependencies."""
    db_status = "ok"
    redis_status = "ok"

    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        db_status = "unavailable"

    try:
        await redis.ping()
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        redis_status = "unavailable"

    return HealthResponse(
        status="ok" if db_status == "ok" and redis_status == "ok" else "degraded",
        version=settings.app_version,
        database=db_status,
        redis=redis_status,
    )


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/api/audit",
    response_model=AuditCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Audit"],
)
async def create_audit(
    payload: AuditRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> AuditCreateResponse:
    """
    Submit a URL for auditing.

    Returns a ``job_id`` that can be polled via ``GET /api/audit/{job_id}``.
    The audit runs asynchronously in the background.
    """
    audit = AuditResult(
        url=str(payload.url),
        status=AuditStatus.PENDING,
    )
    db.add(audit)
    await db.flush()
    job_id = audit.id
    await db.commit()

    background_tasks.add_task(
        _run_audit_pipeline,
        job_id=job_id,
        url=str(payload.url),
        max_pages=payload.max_pages,
        include_lighthouse=payload.include_lighthouse,
    )

    return AuditCreateResponse(
        job_id=job_id,
        status=AuditStatus.PENDING,
        message="Audit job accepted and queued.",
    )


@router.get(
    "/api/audit/{job_id}",
    response_model=AuditStatusResponse,
    tags=["Audit"],
)
async def get_audit(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AuditStatusResponse:
    """
    Retrieve the status and (when complete) the results of an audit job.
    """
    cache_key = f"audit:{job_id}"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        return AuditStatusResponse(**data)

    audit: AuditResult | None = await db.get(AuditResult, job_id)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit job {job_id} not found.",
        )

    analysis: dict = audit.analysis_result or {}
    response = AuditStatusResponse(
        job_id=audit.id,
        url=audit.url,
        status=audit.status,
        error_message=audit.error_message,
        ai_summary=audit.ai_summary,
        overall_score=analysis.get("overall_score"),
        analysis_result=audit.analysis_result,
        category_scores=[
            {
                "id": score.id,
                "category": score.category,
                "score": score.score,
                "label": score.label,
                "details": score.details,
            }
            for score in audit.category_scores
        ],
        created_at=audit.created_at,
        started_at=audit.started_at,
        completed_at=audit.completed_at,
    )

    # Cache completed / failed jobs so the DB isn't hammered
    if audit.status in (AuditStatus.COMPLETED, AuditStatus.FAILED):
        await redis.setex(
            cache_key,
            settings.cache_ttl_seconds,
            json.dumps(response.model_dump(), default=str),
        )

    return response


# ---------------------------------------------------------------------------
# Background audit pipeline
# ---------------------------------------------------------------------------


async def _run_audit_pipeline(
    job_id: uuid.UUID,
    url: str,
    max_pages: int,
    include_lighthouse: bool,
) -> None:
    """
    Full audit pipeline executed as a background task:
    1. Crawl the site with Playwright
    2. (Optionally) run Lighthouse
    3. Send data to Claude for analysis
    4. Persist results to the database
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        audit: AuditResult | None = await db.get(AuditResult, job_id)
        if audit is None:
            logger.error("Audit %s not found; aborting pipeline.", job_id)
            return

        audit.status = AuditStatus.RUNNING
        audit.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            crawl_data = await run_crawl(url, max_pages)
            # Store crawl data but exclude the screenshot blob to keep the DB row lean
            crawl_data_for_db = {k: v for k, v in crawl_data.items() if k != "screenshot"}
            audit.crawl_data = crawl_data_for_db

            lighthouse_data: dict | None = None
            if include_lighthouse:
                lighthouse_result = await run_lighthouse(url)
                if not lighthouse_result.get("error"):
                    audit.lighthouse_data = lighthouse_result
                    lighthouse_data = lighthouse_result
                else:
                    logger.warning(
                        "Lighthouse error for %s: %s", url, lighthouse_result.get("error")
                    )

            analysis = await run_analysis(crawl_data, lighthouse_data)

            # Persist the full Claude analysis for rich API responses
            audit.analysis_result = analysis
            audit.ai_summary = analysis.get("summary", "")

            # Persist per-category scores as individual CategoryScore rows
            categories: dict = analysis.get("categories", {})
            for cat_key, cat_data in categories.items():
                score_val = float(cat_data.get("score", 0))
                # Scores are 0-10; derive label from that scale
                if score_val >= 8:
                    label = "Good"
                elif score_val >= 5:
                    label = "Needs Improvement"
                else:
                    label = "Poor"
                db.add(
                    CategoryScore(
                        audit_result_id=job_id,
                        category=cat_key,
                        score=score_val,
                        label=label,
                        details={"findings": cat_data.get("findings", [])},
                    )
                )

            audit.status = AuditStatus.COMPLETED
            audit.completed_at = datetime.now(timezone.utc)

        except Exception as exc:
            logger.exception("Audit pipeline failed for job %s: %s", job_id, exc)
            audit.status = AuditStatus.FAILED
            audit.error_message = str(exc)
            audit.completed_at = datetime.now(timezone.utc)

        await db.commit()
