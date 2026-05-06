from __future__ import annotations

from typing import Any

from app.schemas.agent import CommunitySearchResponse
from app.skills.base import Skill, SkillContext
from app.workflows.community_search import run_community_search_workflow


class CommunitySearchSkill(Skill):
    name = "community_search"
    description = (
        "Search the local community database; if missing, discover the community, "
        "fetch five dimension metrics, plan retries, score dimensions, and return a trace."
    )

    async def run(
        self,
        payload: dict[str, Any],
        context: SkillContext,
    ) -> CommunitySearchResponse:
        return await run_community_search_workflow(
            db=context.db,
            settings=context.settings,
            community_name=str(payload.get("community_name") or ""),
            city=_optional_str(payload.get("city")),
            state=_optional_str(payload.get("state")),
        )


def _optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
