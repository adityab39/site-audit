"""Site Audit AI – FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, close_redis, engine, get_redis
from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle startup and shutdown events."""
    logger.info("━" * 60)
    logger.info("  %s  v%s  starting up", settings.app_name, settings.app_version)
    logger.info("━" * 60)

    # Create all database tables if they do not exist.
    # For existing databases with schema changes, use Alembic migrations.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✓ Database tables verified / created")

    # Warm up Redis connection and confirm reachability
    redis = await get_redis()
    await redis.ping()
    logger.info("✓ Redis connection established")

    logger.info("✓ CORS origins: %s", settings.allowed_origins)
    logger.info("✓ Claude model: %s", settings.claude_model)
    logger.info("━" * 60)

    yield

    logger.info("Shutting down %s…", settings.app_name)
    await close_redis()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AI-powered website auditing tool – crawl, analyse, and score any public URL "
            "using Playwright, Lighthouse, and Claude."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    return app


app = create_app()
