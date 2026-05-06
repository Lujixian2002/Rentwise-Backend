from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.community import CommunityResponse
from app.schemas.insight import CommunityWebSource


class CommunityIntakeRequest(BaseModel):
    community_name: str = Field(..., min_length=1)


class CommunityIntakeResponse(BaseModel):
    intent: Literal["community_intake"] = "community_intake"
    status: Literal["found", "not_found"]
    query: str
    normalized_query: str
    matched_community_id: str | None = None
    community: CommunityResponse | None = None
    next_step: Literal["use_existing_data", "needs_disco"]


class CommunityDiscoveryRequest(BaseModel):
    community_name: str = Field(..., min_length=1)
    city: str | None = None
    state: str | None = None


class DiscoveredCommunityProfile(BaseModel):
    name: str
    city: str | None = None
    state: str | None = None
    display_name: str | None = None
    center_lat: float | None = None
    center_lng: float | None = None


class DimensionEstimate(BaseModel):
    dimension: Literal["safety", "transit", "convenience", "parking", "environment"]
    score_0_100: float | None = Field(default=None, ge=0, le=100)
    summary: str
    confidence: Literal["high", "medium", "low"]
    data_origin: Literal["api", "web_search", "fallback"] = "api"


class AgentToolCall(BaseModel):
    name: str
    status: Literal["success", "failed", "skipped"]
    detail: str | None = None


class AgentDecision(BaseModel):
    dimension: Literal["safety", "transit", "convenience", "parking", "environment"]
    action: Literal["accept", "retry", "fail"]
    reason: str


class AgentTraceStep(BaseModel):
    step: str
    status: Literal["success", "partial", "failed", "skipped"]
    message: str
    detail: dict | None = None


class CommunityDiscoveryResponse(BaseModel):
    intent: Literal["community_discovery"] = "community_discovery"
    status: Literal["discovered", "partial"]
    query: str
    normalized_query: str
    is_provisional: bool = True
    source: Literal["api", "web_search", "geocoding", "fallback"]
    profile: DiscoveredCommunityProfile
    summary: str
    dimensions: list[DimensionEstimate] = Field(default_factory=list)
    overall_confidence: Literal["high", "medium", "low"]
    missing_fields: list[str] = Field(default_factory=list)
    sources: list[CommunityWebSource] = Field(default_factory=list)
    matched_community_id: str | None = None
    tool_calls: list[AgentToolCall] = Field(default_factory=list)
    agent_decisions: list[AgentDecision] = Field(default_factory=list)
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)


class CommunitySearchRequest(BaseModel):
    community_name: str = Field(..., min_length=1)
    city: str | None = None
    state: str | None = None


class CommunitySearchResponse(BaseModel):
    intent: Literal["community_search"] = "community_search"
    status: Literal["found", "discovered", "partial"]
    source: Literal["database", "discovery"]
    next_step: Literal["use_existing_data", "review_discovery_result"]
    query: str
    matched_community_id: str | None = None
    intake: CommunityIntakeResponse
    discovery: CommunityDiscoveryResponse | None = None
    community: CommunityResponse | None = None
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)


class CommunityReportRequest(BaseModel):
    community_id: str = Field(..., min_length=1)
    user_preferences: dict[str, float] | None = None


class CommunityReportSection(BaseModel):
    type: Literal[
        "overview",
        "fit",
        "dimensions",
        "risk_alerts",
        "viewing_checklist",
        "sources",
    ]
    title: str
    content: str | None = None
    items: list[str] = Field(default_factory=list)


class CommunityReportLocation(BaseModel):
    name: str
    city: str | None = None
    state: str | None = None
    center_lat: float | None = None
    center_lng: float | None = None


class CommunityReportMetricSnapshot(BaseModel):
    median_rent: float | None = None
    commute_minutes: float | None = None
    grocery_density_per_km2: float | None = None
    crime_rate_per_100k: float | None = None
    rent_trend_12m_pct: float | None = None
    noise_avg_db: float | None = None
    night_activity_index: float | None = None
    parking_lot_density_per_km2: float | None = None
    parking_capacity_per_km2: float | None = None
    poi_demand_density_per_km2: float | None = None
    overall_confidence: float | None = None


class CommunityReportDimension(BaseModel):
    dimension: Literal["safety", "transit", "convenience", "parking", "environment"]
    score_0_100: float | None = None
    summary: str | None = None
    data_origin: str | None = None


class CommunityReportReviewSource(BaseModel):
    platform: str | None = None
    author_name: str | None = None
    body_text: str
    posted_at: str | None = None
    source_url: str | None = None


class CommunityReportResponse(BaseModel):
    intent: Literal["community_report"] = "community_report"
    community_id: str
    title: str
    summary: str
    location: CommunityReportLocation
    metrics: CommunityReportMetricSnapshot
    dimensions: list[CommunityReportDimension] = Field(default_factory=list)
    reviews: list[CommunityReportReviewSource] = Field(default_factory=list)
    user_preferences: dict[str, float] = Field(default_factory=dict)
    sections: list[CommunityReportSection] = Field(default_factory=list)
    html_fragment: str | None = None
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
