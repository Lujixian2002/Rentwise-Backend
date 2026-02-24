from datetime import datetime

from pydantic import BaseModel, Field
from pydantic import model_validator


class CompareRequest(BaseModel):
    community_a_id: str | None = Field(default=None, min_length=1)
    community_b_id: str | None = Field(default=None, min_length=1)
    community_a_name: str | None = Field(default=None, min_length=1)
    community_b_name: str | None = Field(default=None, min_length=1)
    weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_community_identity(self):
        if not self.community_a_id and not self.community_a_name:
            raise ValueError("Provide community_a_id or community_a_name")
        if not self.community_b_id and not self.community_b_name:
            raise ValueError("Provide community_b_id or community_b_name")
        return self


class CompareResponse(BaseModel):
    comparison_id: str
    community_a_id: str
    community_b_id: str
    created_at: datetime | None = None
    status: str
    short_summary: str
    structured_diff: dict
    tradeoffs: dict
