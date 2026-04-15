from pydantic import BaseModel, Field


class CommunityInsightRequest(BaseModel):
    max_reviews: int = Field(default=20, ge=0, le=50)


class DimensionCommentary(BaseModel):
    dimension: str
    commentary: str


class CommunityInsightResponse(BaseModel):
    community_id: str
    name: str
    city: str | None = None
    state: str | None = None
    posts_analyzed: int
    dimensions: list[DimensionCommentary]
    overall_commentary: str
