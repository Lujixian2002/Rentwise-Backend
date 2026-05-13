from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.schemas.insight import CommunityWebSource
from app.skills.base import Skill, SkillContext

_WEB_RESEARCH_SYSTEM_PROMPT = """You research renter-useful neighborhood information.
Search the web and return only a valid JSON object:
{"summary": "...", "sources": [{"url": "...", "title": "..."}]}

Rules:
1. Focus on stable public information.
2. Avoid exact prices, forecasts, rumors, or unsourced claims.
3. Keep summary to 2-4 sentences."""


class WebResearchResult(BaseModel):
    summary: str
    sources: list[CommunityWebSource] = Field(default_factory=list)


class WebResearchSkill(Skill):
    name = "web_research"
    description = (
        "Search external web sources for renter-useful community information "
        "and return a sourced summary."
    )

    async def run(
        self,
        payload: dict[str, Any],
        context: SkillContext,
    ) -> WebResearchResult:
        query = _optional_text(payload.get("query")) or ""
        if not query:
            return WebResearchResult(summary="No web research query was provided.")
        if not context.settings.openai_api_key:
            return WebResearchResult(summary="Web research requires an OpenAI API key.")

        client = AsyncOpenAI(
            api_key=context.settings.openai_api_key,
            timeout=context.settings.openai_web_search_timeout_sec,
        )
        if not hasattr(client, "responses"):
            return WebResearchResult(
                summary="Web research is unavailable with the installed OpenAI client."
            )

        try:
            response = await client.responses.create(
                model=context.settings.openai_web_search_model,
                input=[
                    {"role": "system", "content": _WEB_RESEARCH_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                tools=[{"type": "web_search"}],
                tool_choice="auto",
                include=["web_search_call.action.sources"],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "web_research_result",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "summary": {"type": "string"},
                                "sources": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "url": {"type": "string"},
                                            "title": {"type": ["string", "null"]},
                                        },
                                        "required": ["url", "title"],
                                        "additionalProperties": False,
                                    },
                                },
                            },
                            "required": ["summary", "sources"],
                            "additionalProperties": False,
                        },
                    }
                },
                max_output_tokens=700,
            )
            data = json.loads(_extract_response_text(response))
        except Exception:
            return WebResearchResult(summary="I could not complete the web search right now.")

        summary = _optional_text(data.get("summary")) or "No web summary was returned."
        sources = _extract_web_sources(response)
        if not sources and isinstance(data.get("sources"), list):
            sources = [
                CommunityWebSource(
                    url=item.get("url"),
                    title=_optional_text(item.get("title")),
                    domain=_extract_domain(item.get("url")),
                )
                for item in data["sources"]
                if isinstance(item, dict) and item.get("url")
            ]
        return WebResearchResult(summary=summary, sources=sources)


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text or text.lower() == "null":
        return None
    return text


def _extract_response_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    chunks = []
    for output_item in getattr(response, "output", []) or []:
        if getattr(output_item, "type", None) != "message":
            continue
        for content_item in getattr(output_item, "content", []) or []:
            text = getattr(content_item, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks)


def _extract_web_sources(response, limit: int = 6) -> list[CommunityWebSource]:
    seen = set()
    sources = []
    for output_item in getattr(response, "output", []) or []:
        if getattr(output_item, "type", None) != "web_search_call":
            continue
        action = getattr(output_item, "action", {}) or {}
        for source in _obj_get(action, "sources", []) or []:
            url = _obj_get(source, "url")
            if not isinstance(url, str) or not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                CommunityWebSource(
                    url=url,
                    domain=_extract_domain(url),
                    title=_optional_text(_obj_get(source, "title")),
                )
            )
            if len(sources) >= limit:
                return sources
    return sources


def _extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(url).netloc.strip().lower() or None


def _obj_get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
