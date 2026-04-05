"""API route definitions for Site Audit AI.

Endpoints
---------
GET  /health                  – liveness / dependency health check
POST /api/audit               – submit a URL for auditing (returns job_id immediately)
GET  /api/audit/history       – last 20 completed audits (most-recent first)
GET  /api/audit/{job_id}      – poll job status and retrieve results
DELETE /api/audit/{job_id}    – remove an audit record

IMPORTANT: /api/audit/history MUST be registered before /api/audit/{job_id}
so FastAPI does not attempt UUID coercion on the literal string "history".
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal, get_db, get_redis
from app.models.audit import AuditResult, AuditStatus, CategoryScore
from app.schemas.audit import (
    AuditCreateResponse,
    AuditHistoryItem,
    AuditHistoryResponse,
    AuditRequest,
    AuditResultResponse,
    CategoryScoreSchema,
    HealthResponse,
)
from app.services.analyzer import analyze_website
from app.services.crawler import crawl_website
from app.services.lighthouse import run_lighthouse

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

# Redis TTL for completed audit results (24 hours)
_RESULT_TTL_S: int = 86_400


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _url_hash(url: str) -> str:
    """Stable, fixed-length key component for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()


def _result_cache_key(job_id: uuid.UUID) -> str:
    return f"audit:result:{job_id}"


def _url_cache_key(url: str) -> str:
    return f"audit:url:{_url_hash(url)}"


def _extract_screenshot(crawl_data: dict[str, Any]) -> bytes | None:
    """Decode the base-64 screenshot from crawl data into raw bytes."""
    b64: str | None = crawl_data.get("screenshot")
    if not b64:
        return None
    try:
        return base64.b64decode(b64)
    except Exception as exc:
        logger.warning("Failed to decode screenshot: %s", exc)
        return None


def _score_label(score: float) -> str:
    if score >= 8:
        return "Good"
    if score >= 5:
        return "Needs Improvement"
    return "Poor"


def _audit_to_response(audit: AuditResult) -> AuditResultResponse:
    """Convert an ORM AuditResult row into the API response schema."""
    return AuditResultResponse(
        job_id=audit.id,
        url=audit.url,
        mode=audit.mode,
        status=audit.status,
        error_message=audit.error_message,
        ai_summary=audit.ai_summary,
        overall_score=audit.overall_score,
        results=audit.results,
        category_scores=[
            CategoryScoreSchema(
                id=cs.id,
                category=cs.category,
                score=cs.score,
                label=cs.label,
                details=cs.details,
            )
            for cs in audit.category_scores
        ],
        created_at=audit.created_at,
        started_at=audit.started_at,
        completed_at=audit.completed_at,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Application health check",
)
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> HealthResponse:
    """Return liveness status for the API, database, and Redis."""
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
# POST /api/audit
# ---------------------------------------------------------------------------


@router.post(
    "/api/audit",
    response_model=AuditCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Audit"],
    summary="Submit a URL for auditing",
    responses={
        202: {"description": "Job accepted; poll GET /api/audit/{job_id} for results."},
        400: {"description": "Invalid URL format."},
    },
)
async def create_audit(
    payload: AuditRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AuditCreateResponse:
    """Accept a URL, kick off a background audit, return a job ID.

    **Cache behaviour** – if the same URL was successfully audited within the
    last 24 hours the existing ``job_id`` is returned immediately
    (``cached: true``) without launching a new pipeline run.
    """
    url = str(payload.url)
    mode = "professional"

    # ── 1. Check URL-level cache ──────────────────────────────────────────────
    url_key = _url_cache_key(url)
    cached_job_id: str | None = await redis.get(url_key)
    if cached_job_id:
        logger.info("Cache hit for %s → job %s", url, cached_job_id)
        return AuditCreateResponse(
            job_id=uuid.UUID(cached_job_id),
            status=AuditStatus.COMPLETED,
            cached=True,
        )

    # ── 2. Persist a new job row ──────────────────────────────────────────────
    audit = AuditResult(url=url, mode=mode, status=AuditStatus.PENDING)
    db.add(audit)
    await db.flush()
    job_id: uuid.UUID = audit.id
    await db.commit()

    # ── 3. Enqueue background pipeline ───────────────────────────────────────
    background_tasks.add_task(_run_audit, job_id=job_id, url=url)
    logger.info("Audit job %s queued for %s", job_id, url)

    return AuditCreateResponse(job_id=job_id, status=AuditStatus.PENDING)


# ---------------------------------------------------------------------------
# GET /api/audit/history   ← MUST be before /{job_id}
# ---------------------------------------------------------------------------


@router.get(
    "/api/audit/history",
    response_model=AuditHistoryResponse,
    tags=["Audit"],
    summary="List recent audits",
)
async def get_audit_history(
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
) -> AuditHistoryResponse:
    """Return the *limit* most-recent audit jobs (default 20, max 100).

    Each entry includes the URL, mode, status, overall score, and timestamps
    — enough to render a history list without fetching full results.
    """
    limit = min(max(limit, 1), 100)

    total_count: int = await db.scalar(
        select(func.count()).select_from(AuditResult)
    ) or 0

    result = await db.execute(
        select(AuditResult)
        .order_by(desc(AuditResult.created_at))
        .limit(limit)
    )
    audits = result.scalars().all()

    return AuditHistoryResponse(
        audits=[
            AuditHistoryItem(
                job_id=a.id,
                url=a.url,
                mode=a.mode,
                status=a.status,
                overall_score=a.overall_score,
                ai_summary=a.ai_summary,
                created_at=a.created_at,
                completed_at=a.completed_at,
            )
            for a in audits
        ],
        total=total_count,
    )


# ---------------------------------------------------------------------------
# GET /api/audit/{job_id}
# ---------------------------------------------------------------------------


@router.get(
    "/api/audit/{job_id}",
    response_model=AuditResultResponse,
    tags=["Audit"],
    summary="Get audit status and results",
    responses={
        200: {"description": "Audit record found."},
        404: {"description": "Audit job not found."},
    },
)
async def get_audit(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> AuditResultResponse:
    """Return the current status and (when complete) full results for a job.

    Completed and failed jobs are Redis-cached for 24 hours to minimise
    database load during repeated polling.
    """
    # ── 1. Redis cache ────────────────────────────────────────────────────────
    result_key = _result_cache_key(job_id)
    cached = await redis.get(result_key)
    if cached:
        return AuditResultResponse(**json.loads(cached))

    # ── 2. Database lookup ────────────────────────────────────────────────────
    audit: AuditResult | None = await db.get(AuditResult, job_id)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit job '{job_id}' not found.",
        )

    response = _audit_to_response(audit)

    # ── 3. Cache terminal states ──────────────────────────────────────────────
    if audit.status in (AuditStatus.COMPLETED, AuditStatus.FAILED):
        await redis.setex(
            result_key,
            _RESULT_TTL_S,
            json.dumps(response.model_dump(), default=str),
        )

    return response


# ---------------------------------------------------------------------------
# DELETE /api/audit/{job_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/api/audit/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Audit"],
    summary="Delete an audit record",
    responses={
        204: {"description": "Audit deleted successfully."},
        404: {"description": "Audit job not found."},
    },
)
async def delete_audit(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> Response:
    """Permanently delete an audit record and its cached entries."""
    audit: AuditResult | None = await db.get(AuditResult, job_id)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit job '{job_id}' not found.",
        )

    # Remove URL→job_id cache so the URL can be re-audited immediately
    url_key = _url_cache_key(audit.url)
    result_key = _result_cache_key(job_id)
    await redis.delete(url_key, result_key)

    await db.delete(audit)
    await db.commit()
    logger.info("Audit %s deleted.", job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Background audit pipeline
# ---------------------------------------------------------------------------


async def _run_audit(job_id: uuid.UUID, url: str) -> None:
    """Full three-stage audit pipeline executed as a FastAPI background task.

    Stages
    ------
    1. Crawl      — Playwright extracts page metadata, content, CTAs, screenshot
    2. Lighthouse — CLI subprocess collects performance + Core Web Vitals
    3. Analyse    — Claude evaluates all data across 6 categories

    On success the results are written to the database and cached in Redis.
    On any unhandled exception the job is marked ``failed`` with the error
    message stored for diagnostics.
    """
    async with AsyncSessionLocal() as db:
        audit: AuditResult | None = await db.get(AuditResult, job_id)
        if audit is None:
            logger.error("Pipeline: audit %s not found; aborting.", job_id)
            return

        audit.status = AuditStatus.PROCESSING
        audit.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            # ── Stage 1: Crawl ────────────────────────────────────────────────
            logger.info("[%s] Stage 1/3 – crawling %s", job_id, url)
            crawl_data = await crawl_website(url)

            screenshot_bytes = _extract_screenshot(crawl_data)
            # Strip screenshot bytes from what goes into the results JSON column
            crawl_for_results = {k: v for k, v in crawl_data.items() if k != "screenshot"}

            crawl_error   = crawl_data.get("error")
            crawl_partial = crawl_data.get("partial", False)

            if crawl_error and not crawl_partial:
                # Page was completely unreachable — nothing to analyse
                raise RuntimeError(f"Crawl failed: {crawl_error}")
            elif crawl_error:
                # Timeout or page-level error but the server responded;
                # continue with whatever data was collected
                logger.warning(
                    "[%s] Crawl returned partial data (%s) — continuing to Lighthouse + Claude",
                    job_id, crawl_error,
                )

            # ── Stage 2: Lighthouse ───────────────────────────────────────────
            logger.info("[%s] Stage 2/3 – running Lighthouse", job_id)
            lighthouse_result = await run_lighthouse(url)
            lighthouse_for_results: dict[str, Any] | None = (
                lighthouse_result if not lighthouse_result.get("error") else None
            )
            if lighthouse_result.get("error"):
                logger.warning("[%s] Lighthouse error (non-fatal): %s", job_id, lighthouse_result["error"])

            # ── Stage 3: Claude analysis ──────────────────────────────────────
            logger.info("[%s] Stage 3/3 – running Claude analysis", job_id)
            analysis = await analyze_website(crawl_data, lighthouse_for_results)

            # ── Persist results ───────────────────────────────────────────────
            audit.results = {
                "crawl": crawl_for_results,
                "lighthouse": lighthouse_for_results,
                "analysis": analysis,
            }
            audit.screenshot = screenshot_bytes
            audit.ai_summary = analysis.get("summary", "")
            audit.overall_score = analysis.get("overall_score")
            audit.status = AuditStatus.COMPLETED
            audit.completed_at = datetime.now(timezone.utc)

            # Persist per-category scores
            categories: dict[str, dict] = analysis.get("categories", {})
            for cat_key, cat_data in categories.items():
                score_val = float(cat_data.get("score", 0))
                db.add(
                    CategoryScore(
                        audit_result_id=job_id,
                        category=cat_key,
                        score=score_val,
                        label=_score_label(score_val),
                        details={"findings": cat_data.get("findings", [])},
                    )
                )

            await db.commit()
            # Reload to get category_scores populated via selectin
            await db.refresh(audit)

            logger.info(
                "[%s] Audit completed – overall score: %s/100",
                job_id,
                audit.overall_score,
            )

            # ── Cache results in Redis ─────────────────────────────────────────
            redis = await get_redis()
            response_payload = _audit_to_response(audit).model_dump()

            # Cache by job_id (for GET /api/audit/{job_id})
            await redis.setex(
                _result_cache_key(job_id),
                _RESULT_TTL_S,
                json.dumps(response_payload, default=str),
            )
            # Cache URL→job_id mapping (for POST deduplication)
            await redis.setex(
                _url_cache_key(url),
                _RESULT_TTL_S,
                str(job_id),
            )

        except Exception as exc:
            logger.exception("[%s] Audit pipeline failed: %s", job_id, exc)
            audit.status = AuditStatus.FAILED
            audit.error_message = str(exc)
            audit.completed_at = datetime.now(timezone.utc)
            await db.commit()
