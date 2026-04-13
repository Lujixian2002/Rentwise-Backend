from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class PreferenceWeights(BaseModel):
    safety: float | None = None
    transit: float | None = None
    convenience: float | None = None
    parking: float | None = None
    environment: float | None = None


class ChatResponse(BaseModel):
    reply: str
    weights: PreferenceWeights
    ready_to_recommend: bool
