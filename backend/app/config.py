from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Site Audit AI"
    app_version: str = "0.1.0"
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/site_audit"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600

    # Anthropic / Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 4096

    # Playwright
    playwright_timeout_ms: int = 30_000
    max_crawl_pages: int = 10

    # Lighthouse
    lighthouse_binary: str = "lighthouse"
    lighthouse_timeout_ms: int = 60_000
    # Path to the Chrome/Chromium binary Lighthouse should use.
    # Defaults to the system chromium installed in the Docker image.
    # Set to empty string to let Lighthouse auto-detect.
    lighthouse_chrome_path: str = "/usr/bin/chromium"

    # Worker / job settings
    job_expiry_seconds: int = 86_400  # 24 hours


@lru_cache
def get_settings() -> Settings:
    return Settings()
