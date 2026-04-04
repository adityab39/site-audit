"""Lighthouse performance auditing service.

Runs the Lighthouse CLI as an async subprocess, parses the JSON report,
and returns a flat, strongly-typed dict that maps 1-to-1 with
:class:`~app.schemas.audit.LighthouseResultSchema`.

Public API
----------
run_lighthouse(url) – the only function consumed by the pipeline
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMEOUT_S: float = 60.0

_CATEGORIES: tuple[str, ...] = (
    "performance",
    "accessibility",
    "best-practices",
    "seo",
)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_lighthouse(url: str) -> dict[str, Any]:
    """Run Lighthouse against *url* and return structured metrics.

    The returned dict always has the same shape whether the run succeeded
    or failed; on failure every metric field is ``None`` and ``error``
    explains what went wrong.

    Extracted data
    --------------
    scores          – per-category 0-100 floats
    core_web_vitals – LCP, FID, CLS, FCP, TTI, Speed Index, TBT
    page_stats      – byte totals, request counts, DOM size
    diagnostics     – render-blocking URLs, large images, unused bytes
    """
    cmd = _build_cmd(url)
    logger.info("Running Lighthouse: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=TIMEOUT_S,
        )
    except FileNotFoundError:
        msg = (
            f"Lighthouse binary not found ({settings.lighthouse_binary!r}). "
            "Install it with: npm install -g lighthouse"
        )
        logger.warning(msg)
        return _error_result(url, msg)
    except asyncio.TimeoutError:
        msg = f"Lighthouse timed out after {TIMEOUT_S:.0f}s for {url}"
        logger.warning(msg)
        # Best-effort: kill the orphaned subprocess
        try:
            proc.kill()
        except Exception:
            pass
        return _error_result(url, msg)
    except Exception as exc:
        logger.exception("Unexpected error launching Lighthouse: %s", exc)
        return _error_result(url, f"Unexpected error: {exc}")

    # Non-zero exit — Lighthouse could not load the page or crashed
    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace").strip()
        # Still try to parse stdout — Lighthouse sometimes writes JSON even on
        # non-zero exit (e.g. when a category audit fails but others succeed)
        report = _try_parse(stdout)
        if report:
            logger.warning(
                "Lighthouse exited %d but produced partial JSON; extracting.",
                proc.returncode,
            )
            return _extract(url, report)

        msg = stderr_text or f"Lighthouse exited with code {proc.returncode}"
        logger.warning("Lighthouse failed for %s: %s", url, msg)
        return _error_result(url, msg)

    report = _try_parse(stdout)
    if report is None:
        msg = "Lighthouse produced no parseable JSON output"
        logger.warning("%s for %s", msg, url)
        return _error_result(url, msg)

    return _extract(url, report)


# ---------------------------------------------------------------------------
# Command builder
# ---------------------------------------------------------------------------


def _build_cmd(url: str) -> list[str]:
    chrome_flags = "--headless --no-sandbox --disable-gpu --disable-dev-shm-usage"
    cmd: list[str] = [
        settings.lighthouse_binary,
        url,
        "--output=json",
        "--output-path=stdout",   # stream JSON to stdout; avoids temp-file issues
        f'--chrome-flags={chrome_flags}',
        f"--only-categories={','.join(_CATEGORIES)}",
        "--quiet",                # suppress progress output on stderr
    ]
    if settings.lighthouse_chrome_path:
        cmd.append(f"--chrome-path={settings.lighthouse_chrome_path}")
    return cmd


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------


def _try_parse(raw_bytes: bytes) -> dict | None:
    """Attempt to parse *raw_bytes* as JSON; return None on failure."""
    text = raw_bytes.decode(errors="replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Lighthouse sometimes prepends a warning line — try to find the JSON
        brace = text.find("{")
        if brace == -1:
            return None
        try:
            return json.loads(text[brace:])
        except json.JSONDecodeError:
            return None


def _extract(url: str, report: dict) -> dict[str, Any]:
    """Map the raw Lighthouse report dict to our flat result schema."""
    audits: dict[str, Any] = report.get("audits", {})

    return {
        "url": url,
        "lighthouse_version": report.get("lighthouseVersion"),
        "fetch_time": report.get("fetchTime"),
        "error": None,
        "scores": _extract_scores(report),
        "core_web_vitals": _extract_cwv(audits),
        "page_stats": _extract_page_stats(audits),
        "diagnostics": _extract_diagnostics(audits),
    }


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------


def _extract_scores(report: dict) -> dict[str, float | None]:
    categories = report.get("categories", {})

    def score(key: str) -> float | None:
        raw = categories.get(key, {}).get("score")
        return round(raw * 100, 1) if raw is not None else None

    return {
        "performance_score": score("performance"),
        "accessibility_score": score("accessibility"),
        "best_practices_score": score("best-practices"),
        "seo_score": score("seo"),
    }


# ---------------------------------------------------------------------------
# Core Web Vitals
# ---------------------------------------------------------------------------


def _extract_cwv(audits: dict) -> dict[str, float | None]:
    def numeric(key: str) -> float | None:
        return audits.get(key, {}).get("numericValue")

    def ms_to_s(v: float | None) -> float | None:
        return round(v / 1000, 3) if v is not None else None

    lcp_ms = numeric("largest-contentful-paint")
    fcp_ms = numeric("first-contentful-paint")
    tti_ms = numeric("interactive")
    si_ms  = numeric("speed-index")
    tbt_ms = numeric("total-blocking-time")
    cls    = numeric("cumulative-layout-shift")

    # FID is a field metric (not measured in Lighthouse lab runs); include
    # max-potential-fid as the closest lab proxy when available
    fid_ms = numeric("max-potential-fid") or numeric("first-input-delay")

    return {
        "largest_contentful_paint": ms_to_s(lcp_ms),
        "first_input_delay": round(fid_ms, 1) if fid_ms is not None else None,
        "cumulative_layout_shift": round(cls, 4) if cls is not None else None,
        "first_contentful_paint": ms_to_s(fcp_ms),
        "time_to_interactive": ms_to_s(tti_ms),
        "speed_index": ms_to_s(si_ms),
        "total_blocking_time": round(tbt_ms, 1) if tbt_ms is not None else None,
    }


# ---------------------------------------------------------------------------
# Page stats
# ---------------------------------------------------------------------------


def _extract_page_stats(audits: dict) -> dict[str, int | None]:
    """Extract request counts and byte totals from the resource-summary audit."""
    items: list[dict] = (
        audits.get("resource-summary", {})
        .get("details", {})
        .get("items", [])
    )

    totals: dict[str, dict] = {item.get("resourceType", ""): item for item in items}

    def count(rtype: str) -> int | None:
        item = totals.get(rtype)
        return int(item["requestCount"]) if item else None

    def size(rtype: str) -> int | None:
        item = totals.get(rtype)
        return int(item["transferSize"]) if item else None

    dom_size_val = audits.get("dom-size", {}).get("numericValue")

    return {
        "total_page_size_bytes": size("total"),
        "total_requests": count("total"),
        "number_of_scripts": count("script"),
        "number_of_stylesheets": count("stylesheet"),
        "number_of_images": count("image"),
        "dom_size": int(dom_size_val) if dom_size_val is not None else None,
    }


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def _extract_diagnostics(audits: dict) -> dict[str, Any]:
    render_blocking = _render_blocking_urls(audits)
    large_images = _large_images(audits)
    unused_js = _savings_bytes(audits, "unused-javascript")
    unused_css = _savings_bytes(audits, "unused-css-rules")

    return {
        "render_blocking_resources": render_blocking,
        "large_images": large_images,
        "unused_javascript_bytes": unused_js,
        "unused_css_bytes": unused_css,
    }


def _render_blocking_urls(audits: dict) -> list[str]:
    items: list[dict] = (
        audits.get("render-blocking-resources", {})
        .get("details", {})
        .get("items", [])
    )
    urls: list[str] = []
    for item in items:
        url = item.get("url") or item.get("label") or ""
        if url:
            urls.append(url)
    return urls


def _large_images(audits: dict) -> list[dict[str, Any]]:
    """
    Pull oversized/unoptimised image items from the two most relevant audits.
    ``uses-responsive-images`` targets images sent at a larger resolution than
    needed; ``uses-optimized-images`` targets images that could be compressed.
    """
    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    for audit_key in ("uses-responsive-images", "uses-optimized-images"):
        items: list[dict] = (
            audits.get(audit_key, {})
            .get("details", {})
            .get("items", [])
        )
        for item in items:
            # Lighthouse may use 'url' or nested 'node.snippet'
            img_url: str = item.get("url") or item.get("label") or ""
            if not img_url or img_url in seen:
                continue
            seen.add(img_url)
            results.append(
                {
                    "url": img_url,
                    "total_bytes": item.get("totalBytes"),
                    "wasted_bytes": item.get("wastedBytes"),
                }
            )
    return results


def _savings_bytes(audits: dict, key: str) -> int | None:
    details = audits.get(key, {}).get("details", {})
    # Lighthouse ≥ 10 uses overallSavingsBytes
    val = details.get("overallSavingsBytes")
    if val is None:
        # Fallback: sum wastedBytes across items
        items: list[dict] = details.get("items", [])
        if items:
            val = sum(i.get("wastedBytes", 0) for i in items)
    return int(val) if val is not None else None


# ---------------------------------------------------------------------------
# Error fallback
# ---------------------------------------------------------------------------


def _error_result(url: str, message: str) -> dict[str, Any]:
    null_scores = {
        "performance_score": None,
        "accessibility_score": None,
        "best_practices_score": None,
        "seo_score": None,
    }
    null_cwv = {
        "largest_contentful_paint": None,
        "first_input_delay": None,
        "cumulative_layout_shift": None,
        "first_contentful_paint": None,
        "time_to_interactive": None,
        "speed_index": None,
        "total_blocking_time": None,
    }
    null_stats = {
        "total_page_size_bytes": None,
        "total_requests": None,
        "number_of_scripts": None,
        "number_of_stylesheets": None,
        "number_of_images": None,
        "dom_size": None,
    }
    null_diagnostics = {
        "render_blocking_resources": [],
        "large_images": [],
        "unused_javascript_bytes": None,
        "unused_css_bytes": None,
    }
    return {
        "url": url,
        "lighthouse_version": None,
        "fetch_time": None,
        "error": message,
        "scores": null_scores,
        "core_web_vitals": null_cwv,
        "page_stats": null_stats,
        "diagnostics": null_diagnostics,
    }
