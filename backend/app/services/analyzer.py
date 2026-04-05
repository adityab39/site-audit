"""Claude-powered website audit agent.

Combines crawl + Lighthouse data with an agentic tool-calling loop:
Claude decides which supplemental checks to run (robots.txt, SSL,
broken links, image sizes, sitemap), executes them in parallel, then
produces a structured JSON audit report.

Public API
----------
analyze_website(crawl_data, lighthouse_data)  → professional report
run_analysis(crawl_data, lighthouse_data)     → compat wrapper for pipeline
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Retry / agent constants
# ---------------------------------------------------------------------------

_MAX_API_RETRIES: int = 2
_RETRY_DELAY_S: float = 1.5
_MAX_TOOL_ROUNDS: int = 3      # how many tool-calling rounds before forcing final answer
_TOOL_HTTP_TIMEOUT: float = 10.0  # per-request timeout for tool HTTP calls

_RETRYABLE_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)

# ---------------------------------------------------------------------------
# Category keys (keep in sync with prompts and schemas)
# ---------------------------------------------------------------------------

CATEGORY_KEYS: tuple[str, ...] = (
    "copy_messaging",
    "seo_health",
    "performance",
    "design_ux",
    "trust_credibility",
    "accessibility",
)

CATEGORY_LABELS: dict[str, str] = {
    "copy_messaging":    "Copy & Messaging",
    "seo_health":        "SEO Health",
    "performance":       "Performance",
    "design_ux":         "Design & UX",
    "trust_credibility": "Trust & Credibility",
    "accessibility":     "Accessibility",
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are a senior website conversion-optimisation and UX expert with 15 years of
experience auditing SaaS, e-commerce, and marketing websites. You have deep expertise
in copywriting, SEO, Core Web Vitals, accessibility, and conversion rate optimisation.

You will receive structured data extracted from a website crawl and optional Lighthouse
performance metrics. You also have access to tools that let you gather additional
live data: robots.txt, SSL certificate details, broken links, image sizes, and sitemap.

Use the tools strategically — call them only when the information would meaningfully
change a finding. After gathering data (0–3 rounds of tool calls), produce the audit.

━━━ SCORING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score each category from 0 to 10 (integers preferred).
  9-10  Excellent   — best-in-class, nothing meaningful to fix
  7-8   Good        — minor improvements possible
  4-6   Needs Work  — several issues that should be addressed
  0-3   Poor        — critical problems actively harming results

━━━ CATEGORIES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. copy_messaging — Words, tone, and persuasion
   • Headline clarity: can a stranger understand the product in 5 seconds?
   • Value proposition: specific and compelling, or vague and generic?
   • CTA copy: action-oriented ("Start Free Trial") vs passive ("Submit")?
   • Tone consistency across headings and visible text
   • Jargon usage and readability for the target audience
   • Grammar and clarity

2. seo_health — On-page SEO signals
   • Meta title: present, 50-60 chars, includes primary keyword?
   • Meta description: present, 150-160 chars, compelling?
   • Heading hierarchy: H1 → H2 → H3, no levels skipped?
   • Image alt text coverage
   • Canonical URL presence
   • Open Graph tags for social sharing
   • Keyword relevance of visible content
   • robots.txt and sitemap (use tools to verify)

3. performance — Speed and technical efficiency
   Use Lighthouse data when available. Thresholds:
   • LCP: < 2.5 s Good, 2.5–4 s Needs Work, > 4 s Poor
   • TBT: < 200 ms Good, 200–600 ms Needs Work, > 600 ms Poor
   • CLS: < 0.1 Good, 0.1–0.25 Needs Work, > 0.25 Poor
   • FCP: < 1.8 s Good, 1.8–3 s Needs Work, > 3 s Poor
   Also evaluate: page size, request count, render-blocking resources, unused JS/CSS.
   Use check_image_sizes to find oversized images.

   IMPORTANT — Lighthouse has FOUR separate scores:
     • Lighthouse Performance Score (0-100) — speed; used for this "performance" category
     • Lighthouse Accessibility Score (0-100) — used for the "accessibility" category
     • Lighthouse SEO Score (0-100) — one signal in "seo_health"
     • Lighthouse Best Practices Score (0-100) — one signal in "trust_credibility"
   NEVER write "Lighthouse score" without specifying which category.
   NEVER quote specific Lighthouse score numbers (e.g. "55/100") inside individual
   finding descriptions — those scores are already displayed in the UI next to each
   category. Describe what the metric means for real users instead (e.g. "pages take
   over 4 seconds to become interactive on desktop connections").

4. design_ux — Visual design and user experience
   • CTA visibility and placement above the fold
   • Typography: font families and readability
   • Color usage and likely contrast from detected palette
   • Mobile-friendliness: viewport meta, responsive design signals
   • Content scannability: headings, bullets, paragraph length
   • Visual hierarchy guiding the eye toward key actions

5. trust_credibility — Trust signals and credibility
   • Social proof: testimonials, reviews, logos, case studies
   • Contact information visibility
   • Security: SSL certificate (use check_ssl_details for real expiry data)
   • Legal: privacy policy, terms of service links
   • Professional design quality
   • Domain credibility signals

6. accessibility — Inclusive design
   • Alt text coverage on images
   • Semantic heading structure
   • HTML lang attribute present
   • Viewport configuration
   • Keyboard-navigable patterns (button/link semantics)
   • Colour contrast signals from detected palette
   • ARIA attribute evidence
   • Use Lighthouse accessibility score when available

━━━ FINDINGS FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each finding must include:
  severity       "critical" | "warning" | "info"
  title          ≤8 words
  description    Specific, data-grounded observation (cite actual page titles,
                 word counts, link counts, image counts, SSL issuer, etc. — never
                 generic boilerplate). Do NOT repeat Lighthouse score numbers here;
                 those are already shown in the UI.
  recommendation Concrete, actionable next step

If any tool returns check_failed or status "check_failed", do NOT invent a finding
for that check. Either skip it or note "could not be verified automatically".

━━━ PRIORITY FIXES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
List the top 5 highest-impact improvements across all categories, ranked by
impact ÷ effort ratio.
  rank     1–5
  category one of the six category keys
  title    Short action headline
  impact   "high" | "medium" | "low"
  effort   "quick" (< 1 h) | "medium" (1 day) | "redesign" (major rework)

━━━ RESPONSE FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond with ONLY valid JSON — no markdown, no code fences, no explanation text.

{
  "overall_score": <integer 0-100, weighted average across all categories × 10>,
  "summary": "<2-3 sentence executive summary citing this site's specific strengths and weaknesses>",
  "categories": {
    "copy_messaging":    { "score": <0-10>, "findings": [ { "severity": "...", "title": "...", "description": "...", "recommendation": "..." } ] },
    "seo_health":        { "score": <0-10>, "findings": [ ... ] },
    "performance":       { "score": <0-10>, "findings": [ ... ] },
    "design_ux":         { "score": <0-10>, "findings": [ ... ] },
    "trust_credibility": { "score": <0-10>, "findings": [ ... ] },
    "accessibility":     { "score": <0-10>, "findings": [ ... ] }
  },
  "priority_fixes": [
    { "rank": 1, "category": "...", "title": "...", "impact": "high|medium|low", "effort": "quick|medium|redesign" }
  ]
}
""".strip()


# ---------------------------------------------------------------------------
# Tool schemas (sent to Claude as available capabilities)
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "fetch_robots_txt",
        "description": (
            "Fetch the robots.txt file for the site's domain. "
            "Use this to check crawl directives, disallow rules, and sitemap references. "
            "Call this for every site to verify SEO crawlability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full website URL (scheme + domain). The tool constructs /robots.txt automatically.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "check_image_sizes",
        "description": (
            "Fetch HTTP headers for up to 10 image URLs and return their file sizes. "
            "Use this to identify oversized images that hurt performance. "
            "Pass image src URLs from the crawl data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absolute image URLs to check (max 10).",
                },
            },
            "required": ["image_urls"],
        },
    },
    {
        "name": "check_ssl_details",
        "description": (
            "Check the SSL/TLS certificate for an HTTPS URL: issuer, expiry date, "
            "days until expiry, and validity. Use this for trust/credibility analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The HTTPS URL to inspect the SSL certificate for.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "check_broken_links",
        "description": (
            "Check a list of URLs and identify which ones return 4xx or 5xx responses. "
            "Use this on a sample of internal or external links to find dead links "
            "that harm SEO and user experience."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "links": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absolute URLs to check for broken links (max 15).",
                },
            },
            "required": ["links"],
        },
    },
    {
        "name": "fetch_sitemap",
        "description": (
            "Fetch and parse the sitemap.xml (or sitemap_index.xml) for the site. "
            "Returns whether it exists, the URL count, and sample URLs. "
            "Use this for SEO completeness checks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full website URL (scheme + domain). The tool tries /sitemap.xml automatically.",
                },
            },
            "required": ["url"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def _make_origin(url: str) -> str:
    """Return scheme://netloc from a full URL."""
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _http_fetch_sync(
    url: str,
    method: str = "GET",
    timeout: float = _TOOL_HTTP_TIMEOUT,
    max_bytes: int = 50_000,
) -> tuple[int, str, dict[str, str]]:
    """Blocking HTTP fetch. Returns (status_code, body, headers).

    Status 0 means a connection/timeout failure (NOT a 404).
    Callers must treat status 0 as "check failed" rather than "not found".
    """
    try:
        req = urllib.request.Request(
            url,
            method=method,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SiteAuditBot/1.0)"},
        )
        # Do NOT pass a custom ssl context — let Python use its system default.
        # Passing ssl.create_default_context() here breaks HTTPS for many sites.
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(max_bytes).decode(errors="replace") if method == "GET" else ""
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, "", {}
    except Exception:
        # Connection refused, DNS failure, timeout, SSL error, etc.
        return 0, "", {}


async def _tool_fetch_robots_txt(url: str) -> dict[str, Any]:
    origin = _make_origin(url)
    robots_url = f"{origin}/robots.txt"
    try:
        status, body, _ = await asyncio.wait_for(
            asyncio.to_thread(_http_fetch_sync, robots_url),
            timeout=10.0,
        )
    except (asyncio.TimeoutError, Exception) as exc:
        return {
            "url": robots_url,
            "status": "check_failed",
            "error": "Connection timed out or failed — could not verify robots.txt",
        }

    if status == 200 and body:
        lines = [ln for ln in body.strip().splitlines() if ln.strip()]
        disallow_count = sum(1 for ln in lines if ln.lower().startswith("disallow"))
        return {
            "url": robots_url,
            "status": "found",
            "total_lines": len(lines),
            "disallow_rules": disallow_count,
            "preview": "\n".join(lines[:30]),
        }
    if status == 404:
        return {"url": robots_url, "status": "not_found"}
    if status == 0:
        # Connection failure, timeout, or SSL error — do NOT report as missing
        return {
            "url": robots_url,
            "status": "check_failed",
            "error": "Could not connect to server — robots.txt status unknown",
        }
    return {"url": robots_url, "status": "not_found", "http_status": status}


async def _tool_check_image_sizes(image_urls: list[str]) -> dict[str, Any]:
    urls = [u for u in image_urls if u and u.startswith("http")][:10]
    if not urls:
        return {"error": "No valid absolute image URLs provided"}

    async def _one(img_url: str) -> dict[str, Any]:
        status, _, headers = await asyncio.to_thread(
            _http_fetch_sync, img_url, "HEAD"
        )
        raw_size = headers.get("Content-Length") or headers.get("content-length")
        size_bytes = int(raw_size) if raw_size and raw_size.isdigit() else None
        return {
            "url": img_url[:100],
            "status": status,
            "size_bytes": size_bytes,
            "size_kb": round(size_bytes / 1024, 1) if size_bytes else None,
        }

    results: list[Any] = await asyncio.gather(*[_one(u) for u in urls], return_exceptions=True)
    clean = [
        r if isinstance(r, dict) else {"url": urls[i], "error": str(r)}
        for i, r in enumerate(results)
    ]
    total_kb = sum((r.get("size_kb") or 0) for r in clean if isinstance(r, dict))
    large = [r for r in clean if isinstance(r, dict) and (r.get("size_kb") or 0) > 100]
    return {
        "images_checked": len(clean),
        "total_size_kb": round(total_kb, 1),
        "large_images_over_100kb": len(large),
        "results": clean,
    }


def _ssl_details_sync(hostname: str, port: int = 443) -> dict[str, Any]:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                not_after: str = cert.get("notAfter", "")
                issuer_fields  = dict(x[0] for x in cert.get("issuer", []))
                subject_fields = dict(x[0] for x in cert.get("subject", []))

                days_left: int | None = None
                if not_after:
                    try:
                        # notAfter format: "Mar  1 00:00:00 2026 GMT" or "Mar 10 …"
                        # Remove " GMT" suffix before parsing to avoid %Z platform issues;
                        # collapse any double-space (single-digit day padding).
                        clean = not_after.replace(" GMT", "").replace("  ", " ").strip()
                        expiry_dt = datetime.strptime(clean, "%b %d %H:%M:%S %Y").replace(
                            tzinfo=timezone.utc
                        )
                        days_left = (expiry_dt - datetime.now(timezone.utc)).days
                    except ValueError:
                        pass  # leave days_left as None if parsing fails

                return {
                    "status": "verified",
                    "issuer": issuer_fields.get("organizationName", "Unknown"),
                    "common_name": subject_fields.get("commonName", hostname),
                    "expires": not_after,
                    "days_until_expiry": days_left,
                    "expiry_warning": days_left is not None and days_left < 30,
                }
    except ssl.SSLCertVerificationError as exc:
        return {"status": "invalid", "error": f"Certificate verification failed: {exc}"}
    except Exception as exc:
        return {
            "status": "check_failed",
            "error": f"Could not connect or read certificate: {exc}",
        }


async def _tool_check_ssl_details(url: str) -> dict[str, Any]:
    if not url.startswith("https://"):
        return {"status": "not_applicable", "error": "URL does not use HTTPS"}
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    port = parsed.port or 443
    if not hostname:
        return {"status": "check_failed", "error": "Could not parse hostname from URL"}
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_ssl_details_sync, hostname, port),
            timeout=12.0,
        )
        return result
    except asyncio.TimeoutError:
        return {"status": "check_failed", "error": "SSL check timed out"}


async def _tool_check_broken_links(links: list[str]) -> dict[str, Any]:
    # Cap at 20, filter to absolute URLs only, use HEAD with a 5-second timeout
    urls = [u for u in links if u and u.startswith("http")][:20]
    if not urls:
        return {"check_failed": True, "error": "No valid absolute URLs provided"}

    _PER_LINK_TIMEOUT = 5.0

    async def _one(link: str) -> dict[str, Any]:
        try:
            status, _, _ = await asyncio.wait_for(
                asyncio.to_thread(_http_fetch_sync, link, "HEAD", _PER_LINK_TIMEOUT),
                timeout=_PER_LINK_TIMEOUT + 1,
            )
        except asyncio.TimeoutError:
            return {"url": link[:120], "status": 0, "broken": False, "skipped": "timeout"}
        except Exception:
            return {"url": link[:120], "status": 0, "broken": False, "skipped": "error"}
        broken = 400 <= status < 600
        return {"url": link[:120], "status": status, "broken": broken}

    results: list[Any] = await asyncio.gather(*[_one(u) for u in urls], return_exceptions=True)
    clean = [
        r if isinstance(r, dict) else {"url": urls[i], "status": 0, "broken": False, "skipped": "exception"}
        for i, r in enumerate(results)
    ]
    broken = [r for r in clean if r.get("broken")]
    return {
        "checked": len(clean),
        "broken_count": len(broken),
        "broken_links": broken,
        "healthy_count": len([r for r in clean if not r.get("broken") and not r.get("skipped")]),
        "skipped_count": len([r for r in clean if r.get("skipped")]),
    }


def _sitemap_fetch_sync(sitemap_url: str) -> dict[str, Any]:
    status, body, _ = _http_fetch_sync(sitemap_url, max_bytes=200_000)
    if status != 200 or not body:
        return {"found": False, "url": sitemap_url, "status_code": status}
    try:
        root = ET.fromstring(body)
        # Normalise namespace-prefixed tags
        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        locs = [el.text for el in root.iter() if el.tag.split("}")[-1] == "loc" and el.text]
        if tag == "sitemapindex":
            return {
                "found": True,
                "url": sitemap_url,
                "type": "sitemap_index",
                "sitemap_count": len(locs),
                "sample_sitemaps": locs[:5],
            }
        return {
            "found": True,
            "url": sitemap_url,
            "type": "urlset",
            "url_count": len(locs),
            "sample_urls": locs[:10],
        }
    except ET.ParseError:
        return {
            "found": True,
            "url": sitemap_url,
            "parse_error": True,
            "preview": body[:200],
        }


async def _tool_fetch_sitemap(url: str) -> dict[str, Any]:
    origin = _make_origin(url)
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap/sitemap.xml"):
        result = await asyncio.to_thread(_sitemap_fetch_sync, f"{origin}{path}")
        if result.get("found"):
            return result
    return {
        "found": False,
        "tried": [f"{origin}/sitemap.xml", f"{origin}/sitemap_index.xml"],
    }


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


async def _execute_tool(name: str, tool_input: dict[str, Any], crawl_url: str) -> dict[str, Any]:
    """Route a tool call from Claude to the correct async implementation.

    Any exception is caught and returned as a structured ``check_failed`` dict
    so Claude knows the check didn't succeed and must NOT invent findings.
    """
    try:
        if name == "fetch_robots_txt":
            return await _tool_fetch_robots_txt(tool_input.get("url", crawl_url))
        if name == "check_image_sizes":
            return await _tool_check_image_sizes(tool_input.get("image_urls", []))
        if name == "check_ssl_details":
            return await _tool_check_ssl_details(tool_input.get("url", crawl_url))
        if name == "check_broken_links":
            return await _tool_check_broken_links(tool_input.get("links", []))
        if name == "fetch_sitemap":
            return await _tool_fetch_sitemap(tool_input.get("url", crawl_url))
        return {"check_failed": True, "error": f"Unknown tool: {name}"}
    except Exception as exc:
        logger.warning("[Agent] Tool '%s' raised an exception: %s", name, exc)
        return {
            "check_failed": True,
            "error": f"Tool execution failed: {exc}. Do not invent findings based on this.",
        }


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


async def analyze_website(
    crawl_data: dict[str, Any],
    lighthouse_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an agentic audit of the website.

    Parameters
    ----------
    crawl_data:
        Output of :func:`~app.services.crawler.crawl_website`.
    lighthouse_data:
        Output of :func:`~app.services.lighthouse.run_lighthouse`, or ``None``.

    Returns
    -------
    dict
        Full analysis result with ``overall_score``, ``summary``,
        ``categories``, and ``priority_fixes``.
    """
    service = _AnalyzerService()
    return await service.analyze(crawl_data=crawl_data, lighthouse_data=lighthouse_data)


async def run_analysis(
    crawl_data: dict[str, Any],
    lighthouse_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pipeline-facing wrapper for :func:`analyze_website`."""
    return await analyze_website(crawl_data, lighthouse_data)


# ---------------------------------------------------------------------------
# Agent service
# ---------------------------------------------------------------------------


class _AnalyzerService:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def analyze(
        self,
        crawl_data: dict[str, Any],
        lighthouse_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        crawl_url: str = crawl_data.get("url", "")
        user_message = _build_audit_context(crawl_data, lighthouse_data)

        # Run the agent loop
        raw_text = await self._agent_loop(user_message, crawl_url)
        result = _try_parse_json(raw_text)

        if result is None:
            logger.warning("[Agent] Could not parse final JSON — retrying with simple call")
            raw_text = await self._simple_call(user_message)
            result = _try_parse_json(raw_text)

        if result is None:
            logger.error("[Agent] All parse attempts exhausted — using fallback result")
            return _fallback_result()

        return result

    # ── Agent loop ────────────────────────────────────────────────────────────

    async def _agent_loop(self, initial_message: str, crawl_url: str) -> str:
        """Agentic loop: Claude analyses → calls tools → gets results → repeats.

        The loop runs for at most ``_MAX_TOOL_ROUNDS`` rounds of tool calling.
        After that we stop providing tools so Claude is forced to produce the
        final JSON report.
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": initial_message}]

        for round_num in range(1, _MAX_TOOL_ROUNDS + 2):  # +2: rounds 1…N plus final
            allow_tools = round_num <= _MAX_TOOL_ROUNDS
            response = await self._api_call(
                messages,
                tools=_TOOLS if allow_tools else [],
            )

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if not tool_uses or response.stop_reason == "end_turn":
                # Claude produced the final report
                logger.info(
                    "[Agent] Final report received after %d tool round(s)",
                    round_num - 1,
                )
                return text_blocks[0].text if text_blocks else ""

            # ── Claude wants to call tools ────────────────────────────────────
            tool_names = [t.name for t in tool_uses]
            logger.info(
                "[Agent] Round %d/%d — Claude called %d tool(s): %s",
                round_num, _MAX_TOOL_ROUNDS, len(tool_uses), tool_names,
            )

            # Execute all tool calls concurrently
            tool_results: list[Any] = await asyncio.gather(
                *[_execute_tool(t.name, t.input, crawl_url) for t in tool_uses],
                return_exceptions=True,
            )

            # Log a brief summary of each result
            for tool, result in zip(tool_uses, tool_results):
                logger.info(
                    "[Agent] Tool '%s' → %s",
                    tool.name,
                    _log_summary(result),
                )

            # Build tool_result content blocks for the next user message.
            # If this was the last permitted round, attach the "produce final
            # report" instruction in the same user turn so we don't send two
            # consecutive user messages.
            tool_result_content: list[dict[str, Any]] = []
            for tool, result in zip(tool_uses, tool_results):
                if isinstance(result, Exception):
                    result = {"error": str(result)}
                tool_result_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool.id,
                        "content": json.dumps(result, default=str),
                    }
                )

            if round_num == _MAX_TOOL_ROUNDS:
                logger.warning(
                    "[Agent] Maximum tool rounds (%d) reached — appending final-report instruction",
                    _MAX_TOOL_ROUNDS,
                )
                tool_result_content.append(
                    {
                        "type": "text",
                        "text": (
                            "You have now gathered all the information you need. "
                            "Produce the final JSON audit report immediately."
                        ),
                    }
                )

            # Append assistant turn (with tool_use blocks) and user turn (with results)
            messages.append(
                {"role": "assistant", "content": _serialize_content(response.content)}
            )
            messages.append({"role": "user", "content": tool_result_content})

        # Should be unreachable, but guard just in case
        return ""

    # ── API call with retry ───────────────────────────────────────────────────

    async def _api_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        """Call the Claude Messages API with exponential-backoff retry."""
        last_exc: Exception | None = None

        for attempt in range(_MAX_API_RETRIES + 1):
            if attempt > 0:
                delay = _RETRY_DELAY_S * attempt
                logger.info("Claude API retry %d/%d in %.1fs…", attempt, _MAX_API_RETRIES, delay)
                await asyncio.sleep(delay)

            try:
                kwargs: dict[str, Any] = {
                    "model": settings.claude_model,
                    "max_tokens": settings.claude_max_tokens,
                    "system": _SYSTEM_PROMPT,
                    "messages": messages,
                }
                if tools:
                    kwargs["tools"] = tools
                return await self._client.messages.create(**kwargs)

            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                logger.warning(
                    "Retryable Claude API error (attempt %d/%d): %s",
                    attempt + 1, _MAX_API_RETRIES + 1, exc,
                )

            except anthropic.APIError as exc:
                logger.error("Non-retryable Claude API error: %s", exc)
                raise

        assert last_exc is not None
        raise last_exc

    async def _simple_call(self, user_message: str) -> str:
        """Fallback: single call without tools (for JSON parse retry)."""
        response = await self._api_call(
            [{"role": "user", "content": user_message}],
            tools=[],
        )
        text_blocks = [b for b in response.content if b.type == "text"]
        return text_blocks[0].text if text_blocks else ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_content(content: Any) -> list[dict[str, Any]]:
    """Convert Anthropic SDK content blocks to plain dicts for message history."""
    result: list[dict[str, Any]] = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )
    return result


def _log_summary(result: Any) -> str:
    """One-line log-friendly summary of a tool result."""
    if isinstance(result, Exception):
        return f"exception: {result}"
    if not isinstance(result, dict):
        return repr(result)[:120]
    if "error" in result:
        return f"error — {result['error']}"
    if "broken_count" in result:
        return f"{result.get('checked', 0)} links checked, {result['broken_count']} broken"
    if "images_checked" in result:
        return f"{result['images_checked']} images, {result.get('total_size_kb', 0)} KB total, {result.get('large_images_over_100kb', 0)} large"
    if "found" in result:
        return f"found={result['found']}" + (f", url_count={result.get('url_count')}" if result.get("url_count") else "")
    if "valid" in result:
        return f"valid={result['valid']}, expires={result.get('expires', 'unknown')}, days_left={result.get('days_until_expiry')}"
    return str(result)[:120]


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_audit_context(
    crawl_data: dict[str, Any],
    lighthouse_data: dict[str, Any] | None,
) -> str:
    """Transform raw crawler + lighthouse dicts into a focused audit context."""
    meta      = crawl_data.get("metadata", {})
    content   = crawl_data.get("content",  {})
    technical = crawl_data.get("technical", {})
    design    = crawl_data.get("design",   {})
    cta       = crawl_data.get("cta",      {})

    all_links: list[dict] = content.get("links", [])
    external_links = [l for l in all_links if l.get("is_external")]
    link_summary = {
        "total": len(all_links),
        "external": len(external_links),
        "sample_texts": [l.get("text", "") for l in all_links[:12] if l.get("text")],
        "external_domains": list(
            {l["href"].split("/")[2] for l in external_links if l.get("href")}
        )[:8],
    }

    all_images: list[dict] = content.get("images", [])
    images_missing_alt = [i for i in all_images if not i.get("alt")]
    image_summary = {
        "total": len(all_images),
        "missing_alt_count": len(images_missing_alt),
        "alt_coverage_pct": (
            round((len(all_images) - len(images_missing_alt)) / len(all_images) * 100)
            if all_images else 100
        ),
        "sample": [
            {"src": i.get("src", "")[:80], "alt": i.get("alt", "")}
            for i in all_images[:6]
        ],
        # Pass first 10 src URLs so Claude can pass them to check_image_sizes
        "image_urls_for_size_check": [
            i.get("src", "") for i in all_images if i.get("src", "").startswith("http")
        ][:10],
    }

    crawl_context: dict[str, Any] = {
        "url": crawl_data.get("url"),
        "status_code": crawl_data.get("status_code"),
        "crawl_partial": crawl_data.get("partial", False),
        "crawl_error": crawl_data.get("error"),
        "metadata": {
            "title":                    meta.get("title"),
            "title_length":             len(meta.get("title") or ""),
            "meta_description":         meta.get("meta_description"),
            "meta_description_length":  len(meta.get("meta_description") or ""),
            "meta_keywords":            meta.get("meta_keywords"),
            "og_tags":                  meta.get("og_tags", {}),
            "canonical_url":            meta.get("canonical_url"),
            "has_favicon":              bool(meta.get("favicon_url")),
        },
        "content": {
            "h1_tags":          content.get("h1_tags", []),
            "h2_tags":          content.get("h2_tags", [])[:10],
            "h3_tags":          content.get("h3_tags", [])[:10],
            "heading_hierarchy": content.get("heading_hierarchy", [])[:20],
            "word_count":       content.get("word_count"),
            "content_sample":   content.get("paragraphs", [])[:4],
            "links":            link_summary,
            "images":           image_summary,
        },
        "technical": {
            "has_ssl":      technical.get("has_ssl"),
            "language":     technical.get("language"),
            "charset":      technical.get("charset"),
            "viewport_meta": technical.get("viewport_meta"),
        },
        "design": {
            "font_families":       design.get("font_families", []),
            "has_responsive_meta": design.get("has_responsive_meta"),
            "colors_detected_count": len(design.get("colors_used", [])),
            "colors_sample":       design.get("colors_used", [])[:20],
        },
        "cta": {
            "buttons":          cta.get("buttons", [])[:15],
            "cta_elements_count": len(cta.get("cta_elements", [])),
            "cta_elements":     cta.get("cta_elements", [])[:10],
        },
    }

    sections: list[str] = [
        "## Website Crawl Data",
        json.dumps(crawl_context, indent=2, default=str),
    ]

    if lighthouse_data and not lighthouse_data.get("error"):
        scores = lighthouse_data.get("scores", {})
        cwv    = lighthouse_data.get("core_web_vitals", {})
        stats  = lighthouse_data.get("page_stats", {})
        diag   = lighthouse_data.get("diagnostics", {})

        def fmt_score(v: float | None) -> str:
            return f"{round(v)}/100" if v is not None else "unavailable"

        labelled_scores = (
            f"Lighthouse Performance Score: {fmt_score(scores.get('performance_score'))}"
            f"  ← use this for the 'performance' category\n"
            f"Lighthouse Accessibility Score: {fmt_score(scores.get('accessibility_score'))}"
            f"  ← use this for the 'accessibility' category\n"
            f"Lighthouse SEO Score: {fmt_score(scores.get('seo_score'))}"
            f"  ← one signal in 'seo_health' (not the overall SEO score)\n"
            f"Lighthouse Best Practices Score: {fmt_score(scores.get('best_practices_score'))}"
            f"  ← one signal in 'trust_credibility'"
        )
        lh_context: dict[str, Any] = {
            "core_web_vitals": cwv,
            "page_stats":      stats,
            "diagnostics":     diag,
        }
        sections += [
            "",
            "## Lighthouse Data",
            "### Scores (always name the specific category when citing any score)",
            labelled_scores,
            "### Core Web Vitals, Page Stats, Diagnostics",
            json.dumps(lh_context, indent=2, default=str),
        ]
    else:
        sections += [
            "",
            "## Lighthouse Data",
            "Not available — evaluate performance from crawl data only.",
        ]

    sections.append(
        "\n\nYou have tools available. Call them if needed, then produce the JSON audit report."
    )
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    """Extract and parse a JSON object from *raw*. Returns None on failure."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse fallback also failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Fallback result
# ---------------------------------------------------------------------------


def _fallback_result() -> dict[str, Any]:
    """Return a minimal valid result when Claude's response cannot be parsed."""
    empty_category: dict[str, Any] = {"score": 0, "findings": []}
    return {
        "overall_score": 0,
        "summary": (
            "The AI analysis could not be completed. "
            "Please check your Anthropic API key and retry the audit."
        ),
        "categories": {key: dict(empty_category) for key in CATEGORY_KEYS},
        "priority_fixes": [],
        "error": "Analysis failed: could not parse Claude response after retries.",
    }
