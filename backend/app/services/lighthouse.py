"""Lighthouse performance auditing service via CLI subprocess."""

import asyncio
import json
import logging
import tempfile
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Lighthouse categories we care about
_CATEGORIES = ("performance", "accessibility", "best-practices", "seo")

# Subset of Lighthouse audits to include in the stored payload
_AUDIT_KEYS = (
    "first-contentful-paint",
    "largest-contentful-paint",
    "total-blocking-time",
    "cumulative-layout-shift",
    "speed-index",
    "interactive",
    "server-response-time",
    "uses-optimized-images",
    "render-blocking-resources",
    "unused-javascript",
    "unused-css-rules",
)


class LighthouseService:
    async def audit(self, url: str) -> dict:
        """
        Run Lighthouse against *url* via the CLI and return a structured dict
        with category scores and selected audit details.

        Returns an empty dict with an ``error`` key if Lighthouse is not
        available or the run fails.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.json"
            cmd = self._build_command(url, str(output_path))

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=settings.lighthouse_timeout_ms / 1000,
                )

                if proc.returncode != 0:
                    error_msg = stderr.decode(errors="replace").strip()
                    logger.warning("Lighthouse exited %d: %s", proc.returncode, error_msg)
                    return {"error": error_msg or "Lighthouse run failed"}

                if not output_path.exists():
                    return {"error": "Lighthouse did not produce output"}

                raw: dict = json.loads(output_path.read_text())
                return self._extract(raw)

            except FileNotFoundError:
                logger.warning(
                    "Lighthouse binary not found at %r. Skipping.", settings.lighthouse_binary
                )
                return {"error": "Lighthouse binary not found"}
            except asyncio.TimeoutError:
                logger.warning("Lighthouse timed out for %s", url)
                return {"error": "Lighthouse timed out"}
            except Exception as exc:
                logger.exception("Unexpected Lighthouse error: %s", exc)
                return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_command(self, url: str, output_path: str) -> list[str]:
        return [
            settings.lighthouse_binary,
            url,
            "--output=json",
            f"--output-path={output_path}",
            "--chrome-flags=--headless --no-sandbox --disable-gpu",
            f"--only-categories={','.join(_CATEGORIES)}",
            "--quiet",
        ]

    def _extract(self, raw: dict) -> dict:
        categories: dict[str, dict] = {}
        for key, cat in raw.get("categories", {}).items():
            categories[key] = {
                "title": cat.get("title"),
                "score": cat.get("score"),
            }

        audits: dict[str, dict] = {}
        for key in _AUDIT_KEYS:
            audit = raw.get("audits", {}).get(key)
            if audit:
                audits[key] = {
                    "title": audit.get("title"),
                    "score": audit.get("score"),
                    "display_value": audit.get("displayValue"),
                    "description": audit.get("description"),
                }

        return {
            "fetch_time": raw.get("fetchTime"),
            "lighthouse_version": raw.get("lighthouseVersion"),
            "categories": categories,
            "audits": audits,
        }


async def run_lighthouse(url: str) -> dict:
    service = LighthouseService()
    return await service.audit(url)
