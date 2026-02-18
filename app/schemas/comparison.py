from datetime import datetime

from pydantic import BaseModel, Field


class CompareRequest(BaseModel):
    community_a_id: str = Field(min_length=1)
    community_b_id: str = Field(min_length=1)
    weights: dict[str, float] = Field(default_factory=dict)


class CompareResponse(BaseModel):
    comparison_id: str
    community_a_id: str
    community_b_id: str
    created_at: datetime | None = None
    status: str
    short_summary: str
    structured_diff: dict
    tradeoffs: dict
