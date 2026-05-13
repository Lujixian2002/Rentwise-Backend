from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.chat_agent import run_agent_chat
from app.core.config import Settings
from app.schemas.agent import AgentChatResponse, CommunityReportResponse, CommunitySearchResponse
from app.schemas.chat import ChatMessage
from app.skills.base import SkillContext
from app.skills.registry import SkillRegistry, default_skill_registry


class RentWiseAgent:
    """Orchestrates RentWise workflows and project tools."""

    name = "rentwise_agent"

    def __init__(
        self,
        db: Session,
        settings: Settings,
        skill_registry: SkillRegistry | None = None,
    ):
        self.db = db
        self.settings = settings
        self.context = SkillContext(db=db, settings=settings)
        self.skill_registry = skill_registry or default_skill_registry()

    async def search_community(
        self,
        community_name: str,
        city: str | None = None,
        state: str | None = None,
    ) -> CommunitySearchResponse:
        skill = self.skill_registry.get("community_search")
        result = await skill.run(
            payload={
                "community_name": community_name,
                "city": city,
                "state": state,
            },
            context=self.context,
        )
        return result

    async def generate_community_report(
        self,
        community_id: str,
        user_preferences: dict[str, float] | None = None,
    ) -> CommunityReportResponse:
        skill = self.skill_registry.get("community_report")
        result = await skill.run(
            payload={
                "community_id": community_id,
                "user_preferences": user_preferences or {},
            },
            context=self.context,
        )
        return result

    async def chat(self, messages: list[ChatMessage]) -> AgentChatResponse:
        return await run_agent_chat(self, messages)
