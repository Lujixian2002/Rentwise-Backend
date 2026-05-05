from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings


class SkillContext(BaseModel):
    db: Session
    settings: Settings

    model_config = {"arbitrary_types_allowed": True}


class Skill(ABC):
    name: str
    description: str

    @abstractmethod
    async def run(self, payload: dict[str, Any], context: SkillContext):
        ...
