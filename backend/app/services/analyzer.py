"""Claude-powered website audit analyzer.

Sends crawl + Lighthouse data to the Anthropic API and returns a rich,
structured JSON audit report with per-category scores and actionable findings.

Public API
----------
analyze_website(crawl_data, lighthouse_data)  → professional report
run_analysis(crawl_data, lighthouse_data)     → compat wrapper for pipeline
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

_MAX_API_RETRIES: int = 2          # total extra attempts after the first
_RETRY_DELAY_S: float = 1.5        # base delay; multiplied by attempt number
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
    "copy_messaging": "Copy & Messaging",
    "seo_health": "SEO Health",
    "performance": "Performance",
    "design_ux": "Design & UX",
    "trust_credibility": "Trust & Credibility",
    "accessibility": "Accessibility",
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are a senior website conversion-optimisation and UX expert with 15 years of
experience auditing SaaS, e-commerce, and marketing websites. You have deep expertise
in copywriting, SEO, Core Web Vitals, accessibility, and conversion rate optimisation.

You will receive structured data extracted from a website crawl and optional Lighthouse
performance metrics. Analyse this data and produce a comprehensive audit report.

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

3. performance — Speed and technical efficiency
   Use Lighthouse data when available. Thresholds:
   • LCP: < 2.5 s Good, 2.5–4 s Needs Work, > 4 s Poor
   • TBT: < 200 ms Good, 200–600 ms Needs Work, > 600 ms Poor
   • CLS: < 0.1 Good, 0.1–0.25 Needs Work, > 0.25 Poor
   • FCP: < 1.8 s Good, 1.8–3 s Needs Work, > 3 s Poor
   Also evaluate: page size, request count, render-blocking resources, unused JS/CSS.

4. design_ux — Visual design and user experience
   • CTA visibility and placement above the fold
   • Typography: font families and readability
   • Color usage and likely contrast from detected palette
   • Mobile-friendliness: viewport meta, responsive design signals
   • Content scannability: headings, bullets, paragraph length
   • Visual hierarchy guiding the eye toward key actions

5. trust_credibility — Trust signals and credibility
   • Social proof: testimonials, reviews, logos, case studies in content/headings
   • Contact information visibility
   • Security: SSL certificate, trust badge signals
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
  description    Specific, data-grounded observation (cite actual titles, scores,
                 counts from the data — never generic boilerplate)
  recommendation Concrete, actionable next step

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
# Public functions
# ---------------------------------------------------------------------------


async def analyze_website(
    crawl_data: dict[str, Any],
    lighthouse_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a professional audit of the website.

    Parameters
    ----------
    crawl_data:
        Output of :func:`~app.services.crawler.crawl_website`.
    lighthouse_data:
        Output of :func:`~app.services.lighthouse.run_lighthouse`, or ``None``
        if Lighthouse was skipped / failed.

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
# Internal service class
# ---------------------------------------------------------------------------


class _AnalyzerService:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def analyze(
        self,
        crawl_data: dict[str, Any],
        lighthouse_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build the user message, call Claude, parse and return results."""
        user_message = _build_audit_context(crawl_data, lighthouse_data)

        raw_text = await self._call_claude(user_message)
        result = _try_parse_json(raw_text)

        if result is None:
            logger.warning("Claude returned invalid JSON on first attempt; retrying.")
            raw_text = await self._call_claude(user_message)
            result = _try_parse_json(raw_text)

        if result is None:
            logger.error("Claude returned unparseable JSON after retry; using fallback.")
            return _fallback_result()

        return result

    async def _call_claude(self, user: str) -> str:
        """Call the Claude API with exponential-backoff retry on transient errors."""
        last_exc: Exception | None = None

        for attempt in range(_MAX_API_RETRIES + 1):
            if attempt > 0:
                delay = _RETRY_DELAY_S * attempt
                logger.info("Claude API retry %d/%d in %.1fs…", attempt, _MAX_API_RETRIES, delay)
                await asyncio.sleep(delay)

            try:
                message = await self._client.messages.create(
                    model=settings.claude_model,
                    max_tokens=settings.claude_max_tokens,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user}],
                )
                return message.content[0].text

            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                logger.warning(
                    "Retryable Claude API error (attempt %d/%d): %s",
                    attempt + 1,
                    _MAX_API_RETRIES + 1,
                    exc,
                )

            except anthropic.APIError as exc:
                logger.error("Non-retryable Claude API error: %s", exc)
                raise

        assert last_exc is not None
        raise last_exc


# ---------------------------------------------------------------------------
# Context builder — shapes raw service data into a focused Claude prompt
# ---------------------------------------------------------------------------


def _build_audit_context(
    crawl_data: dict[str, Any],
    lighthouse_data: dict[str, Any] | None,
) -> str:
    """Transform raw crawler + lighthouse dicts into a focused audit context.

    Strips binary data (screenshots), truncates large lists, and adds
    computed summaries so the prompt stays compact and signal-rich.
    """
    meta = crawl_data.get("metadata", {})
    content = crawl_data.get("content", {})
    technical = crawl_data.get("technical", {})
    design = crawl_data.get("design", {})
    cta = crawl_data.get("cta", {})

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
    }

    crawl_context: dict[str, Any] = {
        "url": crawl_data.get("url"),
        "status_code": crawl_data.get("status_code"),
        "crawl_error": crawl_data.get("error"),
        "metadata": {
            "title": meta.get("title"),
            "title_length": len(meta.get("title") or ""),
            "meta_description": meta.get("meta_description"),
            "meta_description_length": len(meta.get("meta_description") or ""),
            "meta_keywords": meta.get("meta_keywords"),
            "og_tags": meta.get("og_tags", {}),
            "canonical_url": meta.get("canonical_url"),
            "has_favicon": bool(meta.get("favicon_url")),
        },
        "content": {
            "h1_tags": content.get("h1_tags", []),
            "h2_tags": content.get("h2_tags", [])[:10],
            "h3_tags": content.get("h3_tags", [])[:10],
            "heading_hierarchy": content.get("heading_hierarchy", [])[:20],
            "word_count": content.get("word_count"),
            "content_sample": content.get("paragraphs", [])[:4],
            "links": link_summary,
            "images": image_summary,
        },
        "technical": {
            "has_ssl": technical.get("has_ssl"),
            "language": technical.get("language"),
            "charset": technical.get("charset"),
            "viewport_meta": technical.get("viewport_meta"),
        },
        "design": {
            "font_families": design.get("font_families", []),
            "has_responsive_meta": design.get("has_responsive_meta"),
            "colors_detected_count": len(design.get("colors_used", [])),
            "colors_sample": design.get("colors_used", [])[:20],
        },
        "cta": {
            "buttons": cta.get("buttons", [])[:15],
            "cta_elements_count": len(cta.get("cta_elements", [])),
            "cta_elements": cta.get("cta_elements", [])[:10],
        },
    }

    sections: list[str] = [
        "## Website Crawl Data",
        json.dumps(crawl_context, indent=2, default=str),
    ]

    if lighthouse_data and not lighthouse_data.get("error"):
        lh_context: dict[str, Any] = {
            "scores": lighthouse_data.get("scores", {}),
            "core_web_vitals": lighthouse_data.get("core_web_vitals", {}),
            "page_stats": lighthouse_data.get("page_stats", {}),
            "diagnostics": lighthouse_data.get("diagnostics", {}),
        }
        sections += ["", "## Lighthouse Performance Data", json.dumps(lh_context, indent=2, default=str)]
    else:
        sections += ["", "## Lighthouse Performance Data", "Not available — evaluate performance from crawl data only."]

    sections.append("\n\nAnalyse the website using the data above and return your JSON audit report.")
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
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError as exc:
            logger.debug("JSON parse fallback also failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Fallback result (when all retries and parse attempts are exhausted)
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
