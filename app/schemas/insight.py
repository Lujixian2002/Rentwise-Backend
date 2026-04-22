from pydantic import BaseModel, Field


class CommunityInsightRequest(BaseModel):
    max_reviews: int = Field(default=20, ge=0, le=50)
    include_web_info: bool = True


class DimensionCommentary(BaseModel):
    dimension: str
    commentary: str


class CommunityWebSource(BaseModel):
    url: str
    domain: str | None = None
    title: str | None = None


class CommunityWebInfo(BaseModel):
    summary: str
    highlights: list[str] = Field(default_factory=list)
    sources: list[CommunityWebSource] = Field(default_factory=list)


class CommunityInsightResponse(BaseModel):
    community_id: str
    name: str
    city: str | None = None
    state: str | None = None
    posts_analyzed: int
    dimensions: list[DimensionCommentary]
    overall_commentary: str
    community_web_info: CommunityWebInfo | None = None
