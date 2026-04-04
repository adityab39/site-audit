"""Playwright-based web crawling service."""

import asyncio
import logging
from urllib.parse import urljoin, urlparse

from playwright.async_api import Browser, Page, async_playwright

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class CrawlResult:
    def __init__(self) -> None:
        self.pages: list[dict] = []
        self.errors: list[dict] = []
        self.meta: dict = {}


class CrawlerService:
    async def crawl(self, url: str, max_pages: int | None = None) -> dict:
        """
        Crawl the given URL and up to *max_pages* linked pages on the same
        origin, collecting metadata, headings, links, and basic accessibility
        info from each page.
        """
        limit = max_pages or settings.max_crawl_pages
        result = CrawlResult()
        visited: set[str] = set()
        queue: list[str] = [url]
        origin = self._origin(url)

        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(headless=True)
            try:
                while queue and len(visited) < limit:
                    current_url = queue.pop(0)
                    if current_url in visited:
                        continue
                    visited.add(current_url)

                    page_data = await self._crawl_page(browser, current_url)
                    result.pages.append(page_data)

                    # Enqueue same-origin links discovered on this page
                    for link in page_data.get("links", []):
                        if (
                            self._origin(link) == origin
                            and link not in visited
                            and link not in queue
                        ):
                            queue.append(link)
            finally:
                await browser.close()

        result.meta = {
            "seed_url": url,
            "pages_crawled": len(result.pages),
            "errors": len(result.errors),
        }
        return {"pages": result.pages, "meta": result.meta, "errors": result.errors}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _crawl_page(self, browser: Browser, url: str) -> dict:
        page: Page = await browser.new_page()
        data: dict = {"url": url}
        try:
            response = await page.goto(
                url,
                timeout=settings.playwright_timeout_ms,
                wait_until="networkidle",
            )
            data["status_code"] = response.status if response else None

            data["title"] = await page.title()
            data["meta_description"] = await self._get_meta(page, "description")
            data["meta_robots"] = await self._get_meta(page, "robots")
            data["canonical"] = await self._get_canonical(page)
            data["headings"] = await self._get_headings(page)
            data["links"] = await self._get_links(page, url)
            data["images_missing_alt"] = await self._count_images_missing_alt(page)
            data["word_count"] = await self._get_word_count(page)
            data["load_time_ms"] = await self._get_load_time(page)
        except Exception as exc:
            logger.warning("Error crawling %s: %s", url, exc)
            data["error"] = str(exc)
        finally:
            await page.close()
        return data

    async def _get_meta(self, page: Page, name: str) -> str | None:
        try:
            return await page.get_attribute(f'meta[name="{name}"]', "content")
        except Exception:
            return None

    async def _get_canonical(self, page: Page) -> str | None:
        try:
            return await page.get_attribute('link[rel="canonical"]', "href")
        except Exception:
            return None

    async def _get_headings(self, page: Page) -> dict[str, list[str]]:
        headings: dict[str, list[str]] = {}
        for tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            elements = await page.query_selector_all(tag)
            texts = []
            for el in elements:
                text = await el.inner_text()
                texts.append(text.strip())
            headings[tag] = texts
        return headings

    async def _get_links(self, page: Page, base_url: str) -> list[str]:
        hrefs = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.href)",
        )
        resolved: list[str] = []
        for href in hrefs:
            try:
                full = urljoin(base_url, href).split("#")[0]
                parsed = urlparse(full)
                if parsed.scheme in ("http", "https") and parsed.netloc:
                    resolved.append(full)
            except Exception:
                pass
        return list(dict.fromkeys(resolved))  # deduplicate, preserve order

    async def _count_images_missing_alt(self, page: Page) -> int:
        count: int = await page.eval_on_selector_all(
            "img",
            "imgs => imgs.filter(i => !i.alt || i.alt.trim() === '').length",
        )
        return count

    async def _get_word_count(self, page: Page) -> int:
        try:
            text: str = await page.inner_text("body")
            return len(text.split())
        except Exception:
            return 0

    async def _get_load_time(self, page: Page) -> float | None:
        try:
            timing: dict = await page.evaluate(
                """() => {
                    const t = performance.timing;
                    return { load: t.loadEventEnd - t.navigationStart };
                }"""
            )
            return timing.get("load")
        except Exception:
            return None

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"


# Convenience coroutine used by background tasks
async def run_crawl(url: str, max_pages: int) -> dict:
    service = CrawlerService()
    return await service.crawl(url, max_pages=max_pages)
