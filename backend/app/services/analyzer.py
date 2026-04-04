"""Claude API integration for AI-powered audit analysis."""

import json
import logging

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM_PROMPT = """
You are an expert website auditor and SEO/UX consultant. Given structured data
about a website crawl and optional Lighthouse performance scores, produce a
comprehensive audit report.

Respond ONLY with a valid JSON object matching this exact structure:
{
  "summary": "<2-4 sentence executive summary>",
  "categories": [
    {
      "category": "<name>",
      "score": <0.0-1.0>,
      "label": "<Good|Needs Improvement|Poor>",
      "details": {
        "findings": ["<finding1>", "<finding2>"],
        "recommendations": ["<rec1>", "<rec2>"]
      }
    }
  ]
}

Categories to evaluate:
- SEO: titles, meta descriptions, headings, canonical tags, robots directives
- Content Quality: word counts, duplicate content signals, heading hierarchy
- Accessibility: images missing alt text, heading structure, semantic HTML signals
- Performance: page load times, Lighthouse performance score if available
- Technical Health: broken links, HTTP status codes, redirect chains
""".strip()


class AnalyzerService:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def analyze(
        self,
        crawl_data: dict,
        lighthouse_data: dict | None = None,
    ) -> dict:
        """
        Send crawl (and optionally Lighthouse) data to Claude and return a
        structured analysis dict containing a summary and per-category scores.
        """
        user_content = self._build_user_message(crawl_data, lighthouse_data)

        message = await self._client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        raw_text = message.content[0].text
        return self._parse_response(raw_text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_user_message(
        self,
        crawl_data: dict,
        lighthouse_data: dict | None,
    ) -> str:
        sections: list[str] = [
            "## Crawl Data",
            json.dumps(crawl_data, indent=2, default=str),
        ]
        if lighthouse_data:
            sections += [
                "\n## Lighthouse Data",
                json.dumps(lighthouse_data, indent=2, default=str),
            ]
        sections.append("\nPlease analyse the website and return your JSON report.")
        return "\n".join(sections)

    def _parse_response(self, raw: str) -> dict:
        """
        Extract and parse the JSON block from Claude's response.
        Falls back to a minimal error structure if parsing fails.
        """
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse Claude response: %s\nRaw: %s", exc, raw)
            return {
                "summary": "Analysis could not be parsed.",
                "categories": [],
            }


async def run_analysis(crawl_data: dict, lighthouse_data: dict | None = None) -> dict:
    service = AnalyzerService()
    return await service.analyze(crawl_data, lighthouse_data)
