"""Playwright-based web crawling service.

Public API
----------
crawl_website(url)  – crawl a single URL and return rich structured data
run_crawl(url, max_pages)  – thin wrapper used by the background pipeline
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, Page, Response, async_playwright

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OVERALL_TIMEOUT_S: float = 60.0
PAGE_LOAD_TIMEOUT_MS: int = 30_000  # Playwright uses milliseconds
JS_SETTLE_MS: int = 3_000           # wait after DOMContentLoaded for JS to render

_CTA_KEYWORDS: frozenset[str] = frozenset(
    {
        "sign up", "signup", "get started", "start free", "start now", "try free",
        "try now", "try it free", "buy now", "buy", "purchase", "order now",
        "subscribe", "subscribe now", "join now", "join", "register",
        "create account", "open account", "get access", "request demo",
        "book a demo", "schedule demo", "contact us", "contact", "get in touch",
        "learn more", "see pricing", "view pricing", "get quote", "free trial",
        "download", "download now", "install", "add to cart", "checkout",
        "claim offer", "get offer", "claim", "apply now", "apply",
    }
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class CrawlError(Exception):
    """Raised when a page cannot be crawled."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def crawl_website(url: str) -> dict[str, Any]:
    """Crawl *url* with a headless Chromium browser and return structured data.

    The returned dictionary contains five top-level sections:

    * ``metadata``  – title, description, OG tags, canonical, favicon …
    * ``content``   – headings, paragraphs, links, images, word count …
    * ``technical`` – SSL, language, charset, viewport, all meta tags …
    * ``design``    – colours, font families, responsive meta …
    * ``cta``       – buttons and detected call-to-action elements
    * ``screenshot``– base-64-encoded PNG of the full page (or ``None``)
    * ``error``     – set only when a recoverable error occurred

    An unrecoverable launch failure re-raises; page-level errors are
    captured in the ``error`` key so the caller can store them gracefully.
    """
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
        )
        try:
            return await asyncio.wait_for(
                _extract(browser, url),
                timeout=OVERALL_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("Overall 60-second timeout hit for %s", url)
            return _error_result(url, "Crawl timed out after 60 seconds")
        except CrawlError as exc:
            logger.warning("Crawl error for %s: %s", url, exc)
            return _error_result(url, str(exc))
        except Exception as exc:
            logger.exception("Unexpected crawl failure for %s", url)
            return _error_result(url, f"Unexpected error: {exc}")
        finally:
            await browser.close()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def _extract(browser: Browser, url: str) -> dict[str, Any]:
    """Open one page, navigate, extract all data sections, close page."""
    page: Page = await browser.new_page(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (compatible; SiteAuditBot/1.0; "
            "+https://github.com/site-audit-ai)"
        ),
    )
    # Partial data collected before any timeout — returned instead of failing.
    partial: dict[str, Any] = {}
    response: Response | None = None

    try:
        # Use domcontentloaded instead of networkidle — networkidle hangs
        # on sites with persistent connections, analytics, or websockets.
        response = await page.goto(
            url,
            timeout=PAGE_LOAD_TIMEOUT_MS,
            wait_until="domcontentloaded",
        )
        if response is None:
            raise CrawlError(f"No response received for {url}")
        if response.status >= 400:
            raise CrawlError(f"HTTP {response.status} received for {url}")

        # Give JavaScript time to render after the DOM is ready.
        await page.wait_for_timeout(JS_SETTLE_MS)

        # Run all extraction tasks concurrently where possible.
        try:
            (
                metadata,
                content,
                technical,
                design,
                cta,
            ) = await asyncio.gather(
                _extract_metadata(page, url),
                _extract_content(page, url),
                _extract_technical(page, url),
                _extract_design(page),
                _extract_cta(page),
            )
            partial = {
                "metadata": metadata,
                "content": content,
                "technical": technical,
                "design": design,
                "cta": cta,
            }
        except Exception as extract_exc:
            # Extraction partially failed — log and continue with whatever
            # was collected; screenshot is still attempted below.
            logger.warning("Partial extraction error for %s: %s", url, extract_exc)

        screenshot_b64 = await _take_screenshot(page)

        return {
            "url": url,
            "status_code": response.status if response else None,
            "metadata": partial.get("metadata", {}),
            "content": partial.get("content", {}),
            "technical": partial.get("technical", {"has_ssl": url.startswith("https://")}),
            "design": partial.get("design", {}),
            "cta": partial.get("cta", {}),
            "screenshot": screenshot_b64,
            "error": None,
        }

    except CrawlError:
        raise  # re-raise so crawl_website() handles it as a named error

    except Exception as exc:
        # Any other page-level error (including playwright TimeoutError from
        # goto): log it and return whatever partial data was collected.
        logger.warning("Page error for %s (%s) — returning partial data", url, exc)
        screenshot_b64 = await _take_screenshot(page)
        return {
            "url": url,
            "status_code": response.status if response else None,
            "metadata": partial.get("metadata", {}),
            "content": partial.get("content", {}),
            "technical": partial.get("technical", {"has_ssl": url.startswith("https://")}),
            "design": partial.get("design", {}),
            "cta": partial.get("cta", {}),
            "screenshot": screenshot_b64,
            "error": str(exc),
        }

    finally:
        await page.close()


# ---------------------------------------------------------------------------
# Section: Metadata
# ---------------------------------------------------------------------------


async def _extract_metadata(page: Page, url: str) -> dict[str, Any]:
    """Extract page metadata: title, description, OG tags, canonical, favicon."""
    title: str = await page.title()

    meta_description = await _attr(page, 'meta[name="description"]', "content")
    meta_keywords = await _attr(page, 'meta[name="keywords"]', "content")
    canonical_url = await _attr(page, 'link[rel="canonical"]', "href")

    og_tags: dict[str, str] = await page.evaluate(
        """() => {
            const result = {};
            document.querySelectorAll('meta[property^="og:"]').forEach(el => {
                const prop = el.getAttribute('property');
                const content = el.getAttribute('content');
                if (prop && content) result[prop] = content;
            });
            return result;
        }"""
    )

    favicon_url: str | None = await page.evaluate(
        """() => {
            const selectors = [
                'link[rel="icon"]',
                'link[rel="shortcut icon"]',
                'link[rel="apple-touch-icon"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) return el.href || el.getAttribute('href');
            }
            return null;
        }"""
    )

    return {
        "title": title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords,
        "og_tags": og_tags,
        "canonical_url": canonical_url,
        "favicon_url": favicon_url,
    }


# ---------------------------------------------------------------------------
# Section: Content
# ---------------------------------------------------------------------------


async def _extract_content(page: Page, base_url: str) -> dict[str, Any]:
    """Extract headings, paragraphs, links, images, and word count."""
    origin = _origin(base_url)

    h1_tags = await _heading_texts(page, "h1")
    h2_tags = await _heading_texts(page, "h2")
    h3_tags = await _heading_texts(page, "h3")
    heading_hierarchy = await _heading_hierarchy(page)

    paragraphs: list[str] = await page.evaluate(
        """() =>
            Array.from(document.querySelectorAll('p'))
                .map(p => p.innerText.trim())
                .filter(t => t.length > 0)
        """
    )

    raw_links: list[dict[str, Any]] = await page.evaluate(
        f"""(origin) => {{
            return Array.from(document.querySelectorAll('a[href]')).map(a => {{
                const href = a.href || '';
                const text = (a.innerText || a.textContent || '').trim();
                const isExternal = href.startsWith('http') && !href.startsWith(origin);
                return {{ href, text, is_external: isExternal }};
            }}).filter(l => l.href && !l.href.startsWith('javascript:'));
        }}""",
        origin,
    )
    # Deduplicate by href, preserve order
    seen_hrefs: set[str] = set()
    links: list[dict[str, Any]] = []
    for link in raw_links:
        if link["href"] not in seen_hrefs:
            seen_hrefs.add(link["href"])
            links.append(link)

    images: list[dict[str, Any]] = await page.evaluate(
        """() =>
            Array.from(document.querySelectorAll('img')).map(img => ({
                src: img.src || img.getAttribute('src') || '',
                alt: img.getAttribute('alt') ?? '',
                width: img.naturalWidth || img.width || null,
                height: img.naturalHeight || img.height || null,
            }))
        """
    )

    word_count: int = await page.evaluate(
        """() => {
            const text = document.body?.innerText || '';
            return text.trim().split(/\s+/).filter(w => w.length > 0).length;
        }"""
    )

    return {
        "h1_tags": h1_tags,
        "h2_tags": h2_tags,
        "h3_tags": h3_tags,
        "heading_hierarchy": heading_hierarchy,
        "paragraphs": paragraphs,
        "links": links,
        "images": images,
        "word_count": word_count,
    }


async def _heading_texts(page: Page, tag: str) -> list[str]:
    return await page.evaluate(
        f"""() =>
            Array.from(document.querySelectorAll('{tag}'))
                .map(el => el.innerText.trim())
                .filter(t => t.length > 0)
        """
    )


async def _heading_hierarchy(page: Page) -> list[dict[str, str]]:
    """Return all headings h1–h6 in DOM order with their level and text."""
    return await page.evaluate(
        """() => {
            const nodes = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
            return Array.from(nodes).map(el => ({
                level: el.tagName.toLowerCase(),
                text: el.innerText.trim(),
            })).filter(h => h.text.length > 0);
        }"""
    )


# ---------------------------------------------------------------------------
# Section: Technical
# ---------------------------------------------------------------------------


async def _extract_technical(page: Page, url: str) -> dict[str, Any]:
    """Extract SSL status, language, charset, viewport, and all meta tags."""
    has_ssl: bool = url.startswith("https://")

    language: str | None = await page.evaluate(
        "() => document.documentElement.lang || null"
    )

    charset: str | None = await page.evaluate(
        """() => {
            const el = document.querySelector('meta[charset]');
            if (el) return el.getAttribute('charset');
            const httpEquiv = document.querySelector('meta[http-equiv="Content-Type"]');
            if (httpEquiv) {
                const match = (httpEquiv.getAttribute('content') || '').match(/charset=([^;]+)/i);
                return match ? match[1].trim() : null;
            }
            return null;
        }"""
    )

    viewport_meta: bool = await page.evaluate(
        """() => !!document.querySelector('meta[name="viewport"]')"""
    )

    all_meta_tags: list[dict[str, str]] = await page.evaluate(
        """() =>
            Array.from(document.querySelectorAll('meta')).map(el => {
                const attrs = {};
                for (const attr of el.attributes) attrs[attr.name] = attr.value;
                return attrs;
            })
        """
    )

    return {
        "has_ssl": has_ssl,
        "language": language or None,
        "charset": charset,
        "viewport_meta": viewport_meta,
        "all_meta_tags": all_meta_tags,
    }


# ---------------------------------------------------------------------------
# Section: Design / Visual
# ---------------------------------------------------------------------------


async def _extract_design(page: Page) -> dict[str, Any]:
    """Extract colours, font families, and responsive design signals."""
    has_responsive_meta: bool = await page.evaluate(
        """() => {
            const vp = document.querySelector('meta[name="viewport"]');
            if (!vp) return false;
            const content = vp.getAttribute('content') || '';
            return content.includes('width=device-width');
        }"""
    )

    colors_used: list[str] = await page.evaluate(
        """() => {
            const colors = new Set();
            const colorProps = ['color', 'backgroundColor', 'borderColor',
                                'borderTopColor', 'outlineColor'];

            // From inline style attributes
            document.querySelectorAll('[style]').forEach(el => {
                const style = el.getAttribute('style') || '';
                const matches = style.match(
                    /#[0-9a-fA-F]{3,8}|rgb\\([^)]+\\)|rgba\\([^)]+\\)|hsl\\([^)]+\\)|hsla\\([^)]+\\)/g
                );
                if (matches) matches.forEach(c => colors.add(c));
            });

            // From computed styles of a representative sample of elements
            const sample = Array.from(
                document.querySelectorAll(
                    'body, header, nav, main, section, aside, footer, ' +
                    'h1, h2, h3, a, button, [class*="btn"], [class*="cta"], p'
                )
            ).slice(0, 80);

            sample.forEach(el => {
                const cs = window.getComputedStyle(el);
                colorProps.forEach(prop => {
                    const val = cs[prop];
                    if (val && val !== 'rgba(0, 0, 0, 0)' && val !== 'transparent') {
                        colors.add(val);
                    }
                });
            });

            // From linked stylesheets (same-origin only)
            try {
                Array.from(document.styleSheets).forEach(sheet => {
                    try {
                        Array.from(sheet.cssRules || []).forEach(rule => {
                            const text = rule.cssText || '';
                            const matches = text.match(
                                /#[0-9a-fA-F]{3,8}|rgb\\([^)]+\\)|rgba\\([^)]+\\)|hsl\\([^)]+\\)|hsla\\([^)]+\\)/g
                            );
                            if (matches) matches.forEach(c => colors.add(c));
                        });
                    } catch (_) { /* cross-origin sheet – skip */ }
                });
            } catch (_) {}

            return Array.from(colors).filter(Boolean).slice(0, 100);
        }"""
    )

    font_families: list[str] = await page.evaluate(
        """() => {
            const fonts = new Set();
            const sample = Array.from(
                document.querySelectorAll(
                    'body, h1, h2, h3, h4, p, a, button, span, li, td, th, label, input'
                )
            ).slice(0, 60);

            sample.forEach(el => {
                const ff = window.getComputedStyle(el).fontFamily;
                if (ff) {
                    ff.split(',').forEach(f => {
                        const clean = f.trim().replace(/['"]/g, '');
                        if (clean) fonts.add(clean);
                    });
                }
            });

            // Also scan @font-face rules in stylesheets
            try {
                Array.from(document.styleSheets).forEach(sheet => {
                    try {
                        Array.from(sheet.cssRules || []).forEach(rule => {
                            if (rule.type === CSSRule.FONT_FACE_RULE) {
                                const ff = rule.style?.getPropertyValue('font-family');
                                if (ff) fonts.add(ff.trim().replace(/['"]/g, ''));
                            }
                        });
                    } catch (_) {}
                });
            } catch (_) {}

            return Array.from(fonts).filter(Boolean);
        }"""
    )

    return {
        "colors_used": colors_used,
        "font_families": font_families,
        "has_responsive_meta": has_responsive_meta,
    }


# ---------------------------------------------------------------------------
# Section: CTA Detection
# ---------------------------------------------------------------------------


async def _extract_cta(page: Page) -> dict[str, Any]:
    """Extract button texts and identify call-to-action elements."""
    buttons: list[str] = await page.evaluate(
        """() =>
            Array.from(
                document.querySelectorAll('button, input[type="button"], input[type="submit"]')
            )
            .map(el => (el.innerText || el.value || '').trim())
            .filter(t => t.length > 0)
        """
    )

    # Candidate elements: <button>, <a>, <input type=submit|button>, role=button
    raw_candidates: list[dict[str, str]] = await page.evaluate(
        """() => {
            const selectors = [
                'button',
                'a[href]',
                'input[type="submit"]',
                'input[type="button"]',
                '[role="button"]',
            ];
            const elements = [];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                    if (text) elements.push({ tag: el.tagName.toLowerCase(), text });
                });
            });
            return elements;
        }"""
    )

    cta_elements: list[dict[str, str]] = [
        el for el in raw_candidates
        if _is_cta(el["text"])
    ]

    return {
        "buttons": list(dict.fromkeys(buttons)),   # deduplicated
        "cta_elements": cta_elements,
    }


def _is_cta(text: str) -> bool:
    """Return True if *text* matches any known CTA keyword."""
    normalised = text.lower().strip()
    if normalised in _CTA_KEYWORDS:
        return True
    return any(kw in normalised for kw in _CTA_KEYWORDS)


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------


async def _take_screenshot(page: Page) -> str | None:
    """Capture a full-page screenshot and return it as a base-64 PNG string."""
    try:
        raw: bytes = await page.screenshot(full_page=True, type="png")
        return base64.b64encode(raw).decode("ascii")
    except Exception as exc:
        logger.warning("Screenshot failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


async def _attr(page: Page, selector: str, attribute: str) -> str | None:
    """Return *attribute* of the first element matching *selector*, or None."""
    try:
        return await page.get_attribute(selector, attribute)
    except Exception:
        return None


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _error_result(url: str, message: str) -> dict[str, Any]:
    return {
        "url": url,
        "status_code": None,
        "metadata": {},
        "content": {},
        "technical": {"has_ssl": url.startswith("https://")},
        "design": {},
        "cta": {},
        "screenshot": None,
        "error": message,
    }


# ---------------------------------------------------------------------------
# Pipeline-facing wrapper (keeps routes.py untouched)
# ---------------------------------------------------------------------------


async def run_crawl(url: str, max_pages: int) -> dict[str, Any]:
    """Convenience wrapper called by the background audit pipeline.

    Currently crawls only the seed URL. Multi-page support can be added
    here later without touching the pipeline.
    """
    return await crawl_website(url)
