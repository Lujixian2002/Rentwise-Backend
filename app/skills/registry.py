from __future__ import annotations

from app.skills.base import Skill
from app.skills.community_report_skill import CommunityReportSkill
from app.skills.community_search_skill import CommunitySearchSkill


class SkillRegistry:
    def __init__(self, skills: list[Skill]):
        self._skills = {skill.name: skill for skill in skills}

    def get(self, name: str) -> Skill:
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(f"Unknown skill: {name}")
        return skill

    def list(self) -> list[Skill]:
        return list(self._skills.values())


def default_skill_registry() -> SkillRegistry:
    return SkillRegistry(
        skills=[
            CommunitySearchSkill(),
            CommunityReportSkill(),
        ]
    )
