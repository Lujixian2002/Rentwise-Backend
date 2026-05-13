from __future__ import annotations

from typing import Any

from app.schemas.chat import ChatMessage, ChatResponse
from app.services.chat_service import get_chat_response
from app.skills.base import Skill, SkillContext


class PreferenceExtractionSkill(Skill):
    name = "preference_extraction"
    description = (
        "Extract renter preference weights from chat messages using the existing "
        "preference-weighting chat logic."
    )

    async def run(
        self,
        payload: dict[str, Any],
        context: SkillContext,
    ) -> ChatResponse:
        messages = _normalize_messages(payload.get("messages"))
        return await get_chat_response(messages, context.settings)


def _normalize_messages(value) -> list[ChatMessage]:
    messages = []
    for item in value or []:
        if isinstance(item, ChatMessage):
            messages.append(item)
            continue
        if isinstance(item, dict):
            messages.append(ChatMessage.model_validate(item))
    return messages
